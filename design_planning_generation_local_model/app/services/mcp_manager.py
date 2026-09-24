"""MCP (Model Context Protocol) 服务管理 — 配置持久化 + 工具加载 + 状态查询。

用户在配置中登记外部 MCP 服务器（stdio / streamable_http / sse）后，Agent 启动时
（agent_engine.init_agent）自动发现其工具并合入 PHASE1_TOOLS 绑定给 LLM，对话中
LLM 即可按需调用外部能力（网络搜索、文件系统、数据库、企业内部服务等）；
配置变更后经 agent_engine.reload_mcp_tools() 热重载并重建编译图，无需重启服务。

依赖：langchain-mcp-adapters（MultiServerMCPClient，LangGraph 自定义图的标准
MCP 适配层；将 MCP 服务器的工具适配为 LangChain BaseTool）。

配置文件: app/data/mcp_servers.json（与技能库 skill_library 相同的 JSON 持久化模式）
{
  "<服务器名>": {
    "transport": "stdio" | "streamable_http" | "sse",   # 可省略（有 url→streamable_http，有 command→stdio）
    "command": "python",              # stdio 必填
    "args": ["server.py"],            # stdio 可选
    "cwd": "",                        # stdio 可选
    "env": {},                        # stdio 可选
    "url": "http://host:port/mcp",    # streamable_http / sse 必填
    "headers": {},                    # http/sse 可选（如 {"Authorization": "Bearer ..."}）
    "enabled": true,
    "description": ""
  }
}

安全：stdio 服务器 = 可在宿主机执行任意命令。管理端点仅 ADMIN 可用（routes.py /api/mcp/*）。

Windows 已知限制：本服务 uvicorn 使用 SelectorEventLoop（main.py 设置，psycopg
异步驱动必需），asyncio 子进程 API 在 Windows 的该事件循环下不可用 → stdio 传输
在服务进程内无法拉起子进程（加载时转为明确错误信息，不影响其他服务器）；
Windows 部署请为 MCP 服务器使用 streamable_http / sse 传输。stdio 在 Linux/macOS 正常。
"""
import asyncio
import json
import os
import re

_SERVERS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "mcp_servers.json")

_VALID_TRANSPORTS = ("stdio", "streamable_http", "sse")
# 管理元数据，构建连接配置时剥离：
#   search_priority=true 标记该服务器为「联网搜索优先通道」——其工具在对话搜索
#   请求中优先于内置 web_search（提示词路由 + 代码兜底都据此选择），失败回退内置。
_META_FIELDS = ("enabled", "description", "search_priority")
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")
_LOAD_TIMEOUT_SECONDS = 30  # 单服务器工具发现超时（宕机服务器不拖垮整体加载）

# 模块级缓存（load_mcp_tools 写入；engine/路由同步读取）
_MCP_TOOLS: list = []        # 当前已加载的 MCP 工具（LangChain BaseTool）
_TOOL_SERVER: dict = {}      # tool_name -> server_name
_SERVER_STATUS: dict = {}    # server_name -> {"status": "ok|error|disabled", "tools": n, "message": str}


# ── 配置持久化 ──

def _load_config() -> dict:
    try:
        with open(_SERVERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_SERVERS_FILE), exist_ok=True)
    with open(_SERVERS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── 配置校验与 CRUD ──

def validate_server_config(cfg: dict) -> str | None:
    """校验服务器连接配置。返回错误信息；合法返回 None。"""
    if not isinstance(cfg, dict):
        return "配置必须是对象"
    transport = (cfg.get("transport") or "").strip()
    if transport and transport not in _VALID_TRANSPORTS:
        return f"transport 必须是 {'/'.join(_VALID_TRANSPORTS)} 之一"
    if not transport:
        # 未显式指定时按字段推断
        if (cfg.get("url") or "").strip():
            transport = "streamable_http"
        elif (cfg.get("command") or "").strip():
            transport = "stdio"
        else:
            return "必须提供 url（http/sse 传输）或 command（stdio 传输）"
    if transport == "stdio":
        if not (cfg.get("command") or "").strip():
            return "stdio 传输必须提供 command"
    else:
        url = (cfg.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return "url 必须以 http:// 或 https:// 开头"
    if "args" in cfg and not isinstance(cfg.get("args"), list):
        return "args 必须是数组"
    if "env" in cfg and not isinstance(cfg.get("env"), dict):
        return "env 必须是对象"
    if "headers" in cfg and not isinstance(cfg.get("headers"), dict):
        return "headers 必须是对象"
    return None


def list_servers() -> list:
    """全部服务器配置（含运行状态与已加载工具数）。"""
    cfg = _load_config()
    out = []
    for name, scfg in cfg.items():
        item = {"name": name, **scfg}
        item["runtime"] = _SERVER_STATUS.get(name, {"status": "not_loaded", "tools": 0, "message": ""})
        out.append(item)
    return out


def get_server(name: str) -> dict | None:
    return _load_config().get(name)


def add_server(name: str, cfg: dict) -> dict:
    """新增服务器配置。名称/配置非法或重名时抛 ValueError。"""
    name = (name or "").strip()
    if not _SERVER_NAME_RE.match(name):
        raise ValueError("服务器名只能含字母/数字/下划线/中划线，1-50 字符")
    err = validate_server_config(cfg)
    if err:
        raise ValueError(err)
    all_cfg = _load_config()
    if name in all_cfg:
        raise ValueError(f"服务器「{name}」已存在")
    server = {k: v for k, v in cfg.items() if v is not None}
    server.setdefault("enabled", True)
    all_cfg[name] = server
    _save_config(all_cfg)
    return {"name": name, **server}


def update_server(name: str, cfg: dict) -> dict | None:
    """更新服务器配置（整体替换连接字段，保留未传的 enabled/description）。未找到返回 None。"""
    all_cfg = _load_config()
    if name not in all_cfg:
        return None
    err = validate_server_config(cfg)
    if err:
        raise ValueError(err)
    old = all_cfg[name]
    server = {k: v for k, v in cfg.items() if v is not None}
    server.setdefault("enabled", old.get("enabled", True))
    server.setdefault("description", old.get("description", ""))
    all_cfg[name] = server
    _save_config(all_cfg)
    return {"name": name, **server}


def delete_server(name: str) -> bool:
    all_cfg = _load_config()
    if name not in all_cfg:
        return False
    del all_cfg[name]
    _save_config(all_cfg)
    _SERVER_STATUS.pop(name, None)
    return True


# ── 工具加载 ──

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env_str(s: str, missing: set) -> str:
    """展开字符串中的 ${VAR} 环境变量引用；未设置的变量名记入 missing 并替换为空串。

    用途：headers/url/env 中的密钥引用 .env（如 "Bearer ${DASHSCOPE_API_KEY}"），
    避免 API Key 明文落入 mcp_servers.json 配置文件。
    """
    def _sub(m):
        name = m.group(1)
        val = os.environ.get(name)
        if not val:  # 未设置或为空串都视为缺失（.env 中留空占位等同未配置）
            missing.add(name)
            return ""
        return val
    return _ENV_VAR_RE.sub(_sub, s)


def _expand_env(obj, missing: set):
    """递归展开 dict/list/str 中的 ${VAR} 引用。"""
    if isinstance(obj, str):
        return _expand_env_str(obj, missing)
    if isinstance(obj, dict):
        return {k: _expand_env(v, missing) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v, missing) for v in obj]
    return obj


def _build_connection(scfg: dict) -> tuple:
    """从存储配置构建 MultiServerMCPClient 连接字典（剥离管理元数据，补默认 transport，
    展开 ${VAR} 环境变量引用）。

    Returns:
        (conn_dict, missing_env_vars: set)——missing 非空时调用方应跳过该服务器
        （密钥未配置，连接必然 401，直接给出明确状态而非浪费网络调用）。
    """
    conn = {k: v for k, v in scfg.items() if k not in _META_FIELDS and v not in (None, "", {}, [])}
    if not conn.get("transport"):
        conn["transport"] = "streamable_http" if conn.get("url") else "stdio"
    missing: set = set()
    conn = _expand_env(conn, missing)
    return conn, missing


def _root_error_message(e: BaseException) -> str:
    """展开 ExceptionGroup 提取根因错误（mcp/anyio 的 TaskGroup 会把真实错误包一层，
    直接 str(e) 只显示 "unhandled errors in a TaskGroup"，对排查毫无帮助）。

    401/403 等鉴权错误附明确提示，用户看日志即可定位到 key 问题。
    """
    msgs: list = []

    def walk(exc):
        subs = getattr(exc, "exceptions", None) or []
        if subs:
            for s in subs:
                walk(s)
        else:
            msg = f"{type(exc).__name__}: {str(exc)[:200]}"
            if "401" in msg or "Unauthorized" in msg or "InvalidApiKey" in msg:
                msg += "（API Key 无效——检查服务器配置 headers 引用的环境变量，如 DASHSCOPE_API_KEY 是否为平台有效的通用 API Key）"
            msgs.append(msg)

    walk(e)
    return " | ".join(msgs[:3]) or f"{type(e).__name__}: {str(e)[:200]}"


async def load_mcp_tools(exclude_names: set = None) -> list:
    """连接全部启用的服务器并发现工具（逐服务器容错隔离 + 超时保护）。

    单个服务器连不上/超时只记录状态并跳过，不影响其他服务器与 Agent 启动。
    与 exclude_names（内置工具名）冲突的 MCP 工具跳过——内置工具优先，防止外部
    服务器顶替核心工具（如 build_docx）。

    Args:
        exclude_names: 需要跳过的工具名集合（通常传当前 PHASE1_TOOLS 的名称集）

    Returns:
        加载到的 BaseTool 列表（同时更新模块缓存 _MCP_TOOLS/_TOOL_SERVER/_SERVER_STATUS）
    """
    global _MCP_TOOLS, _TOOL_SERVER, _SERVER_STATUS
    exclude_names = exclude_names or set()
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as e:
        print(f"[mcp_manager] langchain-mcp-adapters 未安装，跳过 MCP 工具加载: {e}")
        _SERVER_STATUS = {n: {"status": "error", "tools": 0, "message": "依赖未安装"}
                          for n in _load_config()}
        _MCP_TOOLS, _TOOL_SERVER = [], {}
        return []

    all_cfg = _load_config()
    tools, tool_server, status = [], {}, {}
    for name, scfg in all_cfg.items():
        if not scfg.get("enabled", True):
            status[name] = {"status": "disabled", "tools": 0, "message": ""}
            continue
        conn, missing_env = _build_connection(scfg)
        if missing_env:
            # 密钥/环境变量未配置：连接必然失败，直接给出明确状态（不浪费网络调用）
            msg = f"环境变量未设置: {', '.join(sorted(missing_env))}（请在 .env 中配置后重载）"
            status[name] = {"status": "error", "tools": 0, "message": msg}
            print(f"[mcp_manager] 服务器 {name} 跳过: {msg}")
            continue
        try:
            client = MultiServerMCPClient({name: conn})
            server_tools = await asyncio.wait_for(client.get_tools(), timeout=_LOAD_TIMEOUT_SECONDS)
        except NotImplementedError:
            # Windows + SelectorEventLoop 下 asyncio 子进程不可用（stdio 传输）
            msg = ("stdio 传输在 Windows+SelectorEventLoop 下不可用，"
                   "请改用 streamable_http/sse 传输或为服务器加 HTTP 网关")
            status[name] = {"status": "error", "tools": 0, "message": msg}
            print(f"[mcp_manager] 服务器 {name}: {msg}")
            continue
        except Exception as e:
            msg = _root_error_message(e)
            status[name] = {"status": "error", "tools": 0, "message": msg}
            print(f"[mcp_manager] 服务器 {name} 连接/工具发现失败: {msg}")
            continue
        kept = []
        for t in server_tools:
            if t.name in exclude_names:
                print(f"[mcp_manager] 工具名「{t.name}」与内置工具冲突，跳过（server={name}）")
                continue
            if t.name in tool_server:
                print(f"[mcp_manager] 工具名「{t.name}」重复，跳过（server={name}，已由 {tool_server[t.name]} 提供）")
                continue
            tool_server[t.name] = name
            kept.append(t)
        tools.extend(kept)
        status[name] = {"status": "ok", "tools": len(kept), "message": ""}
        print(f"[mcp_manager] 服务器 {name}: 发现 {len(server_tools)} 个工具，注入 {len(kept)} 个")

    _MCP_TOOLS, _TOOL_SERVER, _SERVER_STATUS = tools, tool_server, status
    return tools


def get_mcp_tools() -> list:
    """当前已加载的 MCP 工具（同步访问器，供 engine 绑定/同步）。"""
    return list(_MCP_TOOLS)


def get_tool_server(tool_name: str) -> str:
    """工具名 → 所属 MCP 服务器名；非 MCP 工具返回空串。
    供流式事件（tool_start/tool_end）标注外部工具来源，前端据此定向展示。"""
    return _TOOL_SERVER.get(tool_name, "")


def get_priority_search_tools() -> list:
    """「联网搜索优先通道」服务器的已加载工具：[{name, server, description}]。

    配置了 search_priority=true 且启用、且工具已成功加载的服务器才入选。
    消费方：agent_prompt（提示词搜索优先级规则）、agent_engine（实时问题兜底
    强制选工具时优先千问等商业搜索 API，失败由 LLM 按提示词回退 web_search）。
    """
    cfg = _load_config()
    prio_servers = {
        name for name, scfg in cfg.items()
        if scfg.get("search_priority") and scfg.get("enabled", True)
    }
    if not prio_servers:
        return []
    return [t for t in list_loaded_tools() if t.get("server") in prio_servers]


def list_loaded_tools() -> list:
    """已加载工具的元信息列表：[{name, server, description}]。"""
    return [
        {
            "name": t.name,
            "server": _TOOL_SERVER.get(t.name, ""),
            "description": (t.description or "")[:200],
        }
        for t in _MCP_TOOLS
    ]


def get_server_status() -> dict:
    """各服务器最近一次加载的状态。"""
    return dict(_SERVER_STATUS)
