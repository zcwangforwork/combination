"""
sec_filter — 保密密级过滤的唯一收口模块（2026-09-28 新增）

依据《combination 保密数据权限受控 RAG 详细技术方案》§5：
本模块是全项目**唯一**的密级过滤条件构造点。所有检索（向量 / BM25 / 直查）
的密级过滤条件必须经 build_sec_where() 构造，任何调用方不得自行拼接、
也不存在任何"跳过密级过滤"的检索出口。

━━━━━━━━━━━━━━━━━━ 红线声明（与现有代码习惯划清界限）━━━━━━━━━━━━━━━━━━
1. 【不回退】密级过滤永远不因"结果太少"而放宽。现有 vector_store.py 中
   "doc_type 过滤无结果 → 忽略过滤重查"的回退模式**严禁**复制到密级过滤——
   doc_type 回退重查时再次发起的 coll.query 仍必须携带密级 where
   （回退的只是 doc_type，不是密级）。
2. 【Fail-closed】任何信息缺失一律按最严格处理：
   - 无用户上下文           → 只放行 public 级（sec_level ≤ 0）
   - 用户密级值非法/越界     → 按 0 处理并记审计告警
   - chunk 无 sec_level     → 不被 $lte 匹配 → 对所有人不可见（倒逼回填）
3. 本模块不提供"不过滤"选项；mode=off 仅为整体灰度回滚通道（§7），
   由全局开关控制，单个调用方无法选择退出。

模式（SEC_FILTER_MODE，env + 运行时可经管理端覆盖）：
  off     — 回退上线前行为（紧急回滚通道；切换需 ADMIN + 留痕）
  shadow  — 过滤照常计算但不生效；denied_count / max_hit_level 照常入审计
  enforce — 过滤生效 + L3 拦截生效
"""
import os
import re
import time
import json
import contextvars
import datetime
from typing import Optional

# ── 密级模型（§2.1）：数值越大越敏感；判定只看数值，标签仅作展示 ──
SEC_LEVEL_LABELS = {0: "公开", 1: "内部", 2: "秘密", 3: "机密"}
SEC_LEVEL_IDS = {0: "public", 1: "internal", 2: "confidential", 3: "secret"}
SEC_MAX_LEVEL = 3


def normalize_sec_level(value, *, strict: bool = False) -> Optional[int]:
    """密级值归一化：合法返回 0..3 的 int；非法返回 None。

    strict=True 时 bool 显式排除（True 会被 isinstance(int) 误判为 1）。
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        lvl = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= lvl <= SEC_MAX_LEVEL:
        return lvl
    return None


def sec_label(level: int) -> str:
    """密级数值 → 中文标签（展示用，不参与判定）"""
    return SEC_LEVEL_LABELS.get(level, "未标注")


# ── 配置项（§14.1），env 读取，缺省与方案一致 ──

def cfg_mode() -> str:
    m = (os.environ.get("SEC_FILTER_MODE", "shadow") or "shadow").strip().lower()
    return m if m in ("off", "shadow", "enforce") else "shadow"


def cfg_default_level() -> int:
    """SEC_DEFAULT_LEVEL：未标注 chunk 的等效密级（脚本批量入库缺省）"""
    return normalize_sec_level(os.environ.get("SEC_DEFAULT_LEVEL", 3)) or 3


def cfg_upload_default() -> str:
    """SEC_UPLOAD_DEFAULT：上传默认密级策略 uploader（上传者密级）/ max（=3）"""
    v = (os.environ.get("SEC_UPLOAD_DEFAULT", "uploader") or "uploader").strip().lower()
    return v if v in ("uploader", "max") else "uploader"


def cfg_overfetch() -> int:
    """SEC_OVERFETCH：超额召回倍数（n_results 上限 50）"""
    try:
        n = int(os.environ.get("SEC_OVERFETCH", "3"))
    except ValueError:
        n = 3
    return max(1, min(n, 10))


def overfetch_n(top_k: int) -> int:
    """top_k × OVERFETCH，封顶 50（Chroma n_results 上限约束）"""
    return min(max(top_k * cfg_overfetch(), top_k), 50)


# ── 模式开关：env 为启动缺省，运行时覆盖仅经管理端（留痕） ──
_mode_override: Optional[str] = None
_mode_overridden_by: Optional[str] = None


def get_mode() -> str:
    """当前生效模式：运行时覆盖 > 环境变量缺省（重启后回到 env 值）"""
    return _mode_override or cfg_mode()


def set_mode_override(mode: str, operator: str) -> str:
    """运行时切换模式（仅管理端调用；调用方负责鉴权与审计留痕）"""
    global _mode_override, _mode_overridden_by
    m = (mode or "").strip().lower()
    if m not in ("off", "shadow", "enforce"):
        raise ValueError(f"非法模式: {mode}（合法值 off/shadow/enforce）")
    _mode_override = m
    _mode_overridden_by = operator
    return get_mode()


def mode_overridden_by() -> Optional[str]:
    return _mode_overridden_by if _mode_override else None


# ── 用户密级解析（§5.1）：JWT claim → 查 PG 用户表（带缓存）→ 0 ──

_user_level_cache: dict = {}          # username → (level, cached_at)
_user_cache_lock = None               # 惰性创建（线程锁）


def _cache_ttl() -> float:
    try:
        return float(os.environ.get("SEC_USER_CACHE_TTL", "300"))
    except ValueError:
        return 300.0


def lookup_user_sec_level(username: str) -> Optional[int]:
    """查 PostgreSQL t_user.sec_level（同步 psycopg3，TTL 缓存）。

    供 JWT 无 sec_level claim 的兼容期旧 token 回退使用；
    查不到 / 连接失败 → None（调用方再回退 0，fail-closed）。
    PG 连接参数复用 PGSQL_* 环境变量（与 pgsql_client.py 一致）。
    """
    global _user_cache_lock
    if _user_cache_lock is None:
        import threading
        _user_cache_lock = threading.Lock()

    now = time.time()
    with _user_cache_lock:
        hit = _user_level_cache.get(username)
        if hit and now - hit[1] < _cache_ttl():
            return hit[0]

    level: Optional[int] = None
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.environ.get("PGSQL_HOST", "localhost"),
            port=int(os.environ.get("PGSQL_PORT", "5432")),
            dbname=os.environ.get("PGSQL_DATABASE", "postgres"),
            user=os.environ.get("PGSQL_USER", "postgres"),
            password=os.environ.get("PGSQL_PASSWORD", ""),
            connect_timeout=3,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT sec_level FROM t_user WHERE username = %s", (username,))
                row = cur.fetchone()
                if row is not None:
                    level = normalize_sec_level(row[0])
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — 连不上库按"查不到"处理（fail-closed）
        print(f"[sec_filter] 查询用户密级失败({username}): {e}")
        level = None

    with _user_cache_lock:
        _user_level_cache[username] = (level, now)
    return level


def invalidate_user_level_cache(username: str = None) -> None:
    """密级变更后清缓存（立即生效通道，见 §12 R2）"""
    with _user_cache_lock:
        if username:
            _user_level_cache.pop(username, None)
        else:
            _user_level_cache.clear()


def resolve_identity_sec_level(username: str, claim) -> int:
    """验签后解析用户密级：claim → 查库 → 0；非法值记审计告警（§2.4 矩阵）"""
    lvl = normalize_sec_level(claim)
    if lvl is not None:
        return lvl
    if claim is not None:  # 有值但非法 → 异常身份从严 + 告警
        _warn_anomalous("jwt_sec_level_invalid", username, repr(claim))
    lvl = lookup_user_sec_level(username)
    if lvl is None:
        _warn_anomalous("user_sec_level_missing", username, "回退按 0(public)")
        return 0
    return lvl


# ── 过滤条件构造（§5.2 唯一出口）──

def build_sec_where(user_level) -> Optional[dict]:
    """构造 ChromaDB where 过滤：{sec_level: {$lte: 用户密级}}。

    本函数**永不返回"无过滤"**：
    - 无用户上下文 / 密级非法 → {$lte: 0}（fail-closed）
    - 仅 mode=off 时返回 None（全局回滚通道，非调用方可选）
    """
    if get_mode() == "off":
        return None
    lvl = normalize_sec_level(user_level)
    if lvl is None:
        ctx = _current_user_ctx()
        if ctx:
            _warn_anomalous("user_sec_level_invalid", ctx[0], repr(user_level))
        lvl = 0
    return {"sec_level": {"$lte": lvl}}


def effective_query_where() -> Optional[dict]:
    """检索调用方实际注入 coll.query 的 where：

    - enforce：返回密级过滤 where（主防线生效）
    - shadow ：返回 None（不实际过滤，denied 由候选复核计算并标记）
    - off    ：返回 None（回退上线前行为）
    build_sec_where() 保持为纯构造器（测试 / 收口审计用）。
    """
    if get_mode() != "enforce":
        return None
    return build_sec_where(current_user_sec_level())


def combine_where(extra) -> Optional[dict]:
    """把密级过滤条件并入调用方既有 where（如 source_file $in 限定）。

    - enforce：返回 [extra, sec] 的 $and 组合（extra 为 None 时仅返回 sec）
    - shadow/off：原样返回 extra（密级不实际过滤）
    检索调用方不得绕过本函数自行拼接密级条件（收口原则 §5.2）。
    """
    sec = effective_query_where()
    if sec is None:
        return extra
    if extra is None:
        return sec
    return {"$and": [extra, sec]}


def current_user_sec_level() -> int:
    """从 kb_scope 上下文取当前用户密级（无上下文/非法 → 0，fail-closed）"""
    lvl = None
    ctx = _current_user_ctx()
    if ctx and len(ctx) >= 3:
        lvl = normalize_sec_level(ctx[2])
    if lvl is None:
        if ctx and len(ctx) >= 3 and ctx[2] is not None:
            _warn_anomalous("user_sec_level_invalid", ctx[0], repr(ctx[2]))
        return 0
    return lvl


def _current_user_ctx():
    try:
        from app.services import kb_scope
        return kb_scope.get_kb_user()
    except Exception:  # noqa: BLE001
        return None


# ── 候选复核（§5.4，BM25 / shadow 模式共用）──

def chunk_sec_level(meta: dict) -> Optional[int]:
    """chunk metadata 的密级值；缺失/非法返回 None（按不可见处理）"""
    if not meta:
        return None
    return normalize_sec_level(meta.get("sec_level"))


def candidate_visible(meta: dict, user_level) -> bool:
    """逐条密级复核：chunk.sec_level ≤ user.sec_level 才可见。

    无 sec_level metadata / 值非法 → 按 3(secret) 处理（§2.4 fail-closed 矩阵），
    即仅对最高密级用户可见；用户密级缺失/非法 → 按 0 处理。
    """
    u = normalize_sec_level(user_level)
    u = 0 if u is None else u
    lvl = chunk_sec_level(meta)
    if lvl is None:
        lvl = SEC_MAX_LEVEL  # §2.4：chunk 密级缺失/非法 → 按 3(secret) 处理
    return lvl <= u


# ── denied 登记簿（ContextVar，随请求/后台任务传播，供审计与 L3 使用）──

_denied_chunks: contextvars.ContextVar = contextvars.ContextVar(
    "sec_denied_chunks", default=None)


def _denied_list() -> list:
    v = _denied_chunks.get()
    if v is None:
        v = []
        _denied_chunks.set(v)
    return v


def note_denied(text: str, meta: dict, collection: str = "") -> None:
    """登记一个被密级过滤排除的候选 chunk（shadow 标记 / enforce 剔除均登记）"""
    lvl = chunk_sec_level(meta)
    _denied_list().append({
        "text": (text or "")[:2000],
        "source_file": (meta or {}).get("source_file", ""),
        "sec_level": SEC_MAX_LEVEL if lvl is None else lvl,
        "sec_label": sec_label(lvl) if lvl is not None else "未标注",
        "collection": collection,
    })


# ── 批量复核 / 探针（VectorStore 主链路与 agent_tools 直查旁路共用，§5.6）──

def mark_denied_batch(documents: list, metadatas: list, collection: str,
                      user_level) -> None:
    """对一组查询结果逐条密级复核，不可见者登记 denied（不剔除，调用方决定）。"""
    for doc, meta in zip(documents or [], metadatas or []):
        if not candidate_visible(meta, user_level):
            note_denied(doc, meta, collection)


def probe_denied(coll, query_embedding, n_fetch: int, collection: str,
                 user_level) -> None:
    """enforce 模式探针：同规模无 where 查询，仅为 denied 统计与 L3 兜底样本
    （§5.5）。失败静默（探针不影响主检索）。"""
    try:
        probe = coll.query(
            query_embeddings=[query_embedding],
            n_results=n_fetch,
            include=["documents", "metadatas"],
        )
        if probe.get("ids") and probe["ids"][0]:
            mark_denied_batch(probe["documents"][0], probe["metadatas"][0],
                              collection, user_level)
    except Exception as e:  # noqa: BLE001 — 探针失败不影响主检索
        print(f"[sec_filter] 探针失败({collection}): {e}")


def drain_denied() -> list:
    """取走并清空当前上下文累计的 denied 集合（L3 检测对象）"""
    v = _denied_list()
    _denied_chunks.set([])
    return v


def peek_denied() -> list:
    return list(_denied_list())


# ── 检索审计（每次 retrieve 收口时调用一次；异步落盘不阻塞主链路）──

def audit_retrieval(*, query: str, scope_summary: str, results: list,
                    extra_denied: int = 0) -> None:
    """汇总一次检索的审计数据并投递到 sec_audit 异步写队列。

    results 为本次最终返回的 chunk 列表（dict，含 metadata 或平铺字段）；
    denied 数据取 note_denied 累计值 + extra_denied（向量路径探针计数）。
    """
    try:
        from app.services import sec_audit
    except Exception:  # noqa: BLE001
        return
    ctx = _current_user_ctx()
    username = ctx[0] if ctx else "(anonymous)"
    denied = peek_denied()
    max_hit = 0
    for r in results or []:
        lvl = chunk_sec_level(r.get("meta") or r) if isinstance(r, dict) else None
        if lvl is not None and lvl > max_hit:
            max_hit = lvl
    scope_repr = re.sub(r"\s+", " ", (query or ""))[:80]
    import hashlib
    digest = hashlib.sha256((query or "").encode("utf-8")).hexdigest()[:16]
    sec_audit.enqueue_retrieval_audit({
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "username": username,
        "sec_level_at_query": current_user_sec_level(),
        "query_digest": digest,
        "query_preview": scope_repr,
        "scope_summary": scope_summary[:200],
        "max_hit_level": max_hit,
        "returned_count": len(results or []),
        "denied_count": len(denied) + extra_denied,
        "leak_blocked": 0,
        "mode": get_mode(),
        "denied_files": sorted({d["source_file"] for d in denied if d["source_file"]}),
    })


# ── 入库打标（§4.1 / §4.2 统一收口：禁止各入口自行拼密级 metadata）──

def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def resolve_ingest_sec_level(explicit=None) -> tuple:
    """入库时密级判定（优先级：显式指定 > 页面上传默认=上传者密级 > 脚本缺省=3）。

    Returns:
        (sec_level: int, sec_source: str)  # sec_source ∈ manual / inherit
    """
    lvl = normalize_sec_level(explicit)
    if lvl is not None:
        return lvl, "manual"
    # 兜底默认：登录上传 → 上传者密级；脚本（无上下文）→ SEC_DEFAULT_LEVEL(3)
    if cfg_upload_default() == "max":
        return cfg_default_level(), "inherit"
    ctx = _current_user_ctx()
    if ctx and len(ctx) >= 3:
        u = normalize_sec_level(ctx[2])
        if u is not None:
            return u, "inherit"
    return cfg_default_level(), "inherit"


def check_upload_sec_level_permission(explicit, is_admin: bool) -> None:
    """防投毒（§4.1）：普通用户不得把文件标成高于自己密级的等级。

    显式指定且高于本人密级且非 ADMIN → 抛 ValueError（由路由层转 403/400）。
    """
    lvl = normalize_sec_level(explicit)
    if lvl is None:
        return
    if is_admin:
        return
    ctx = _current_user_ctx()
    if not ctx:
        return  # 无上下文（脚本路径）不适用本规则（脚本缺省恒为 3，倒逼管理员精标）
    u = normalize_sec_level(ctx[2]) if len(ctx) >= 3 else None
    if u is None or lvl > u:
        raise ValueError(
            f"无权标注密级 {sec_label(lvl)}（高于本人密级"
            f"{sec_label(u) if u is not None else '未知'}）")


def stamp_sec_meta(meta: dict, sec_level=None, sec_source: str = None,
                   acl_version: str = None) -> dict:
    """向 chunk metadata 注入五个密级字段（§3.1，全部标量）。

    显式 sec_level 缺省时按 resolve_ingest_sec_level 判定；
    本函数是唯一的密级 metadata 构造点（收口原则）。
    """
    lvl, src = resolve_ingest_sec_level(sec_level)
    if sec_source in ("manual", "cover", "inherit"):
        src = sec_source
    meta.update({
        "sec_level": lvl,
        "sec_label": sec_label(lvl),
        "sec_source": src,
        "acl_version": acl_version or f"live-{datetime.date.today().strftime('%Y%m%d')}",
        "sec_updated_at": _now_iso(),
    })
    return meta


# ── 异常数据告警（§2.4 / §8.1：sec_level 非法等场景留痕）──

def _warn_anomalous(scene: str, subject: str, detail: str) -> None:
    print(f"[sec_filter][WARN] 异常数据告警 scene={scene} subject={subject} detail={detail}")
    try:
        from app.services import sec_audit
        sec_audit.enqueue_admin_audit({
            "ts": _now_iso(),
            "operator": "(system)",
            "action": "anomaly_warning",
            "target": f"{scene}:{subject}",
            "detail": detail,
        })
    except Exception:  # noqa: BLE001
        pass
