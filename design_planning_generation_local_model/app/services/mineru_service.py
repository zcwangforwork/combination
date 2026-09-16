"""
MinerU Document Parsing Service

使用本地部署的 MinerU2.5-Pro-2605-1.2B 视觉语言模型解析文档，
通过 mineru_vl_utils.MinerUClient 调用，无需网络，无 API 配额限制。
设置 USE_MINERU=true 启用。

设计要点：
- opt-in 启用：通过环境变量 USE_MINERU=true 开启；未开启时返回空列表，
  调用方自动回退到本地解析器（python-docx / pdfplumber / tesseract 等）。
- 接口兼容：extract_text_with_mineru 返回 List[Tuple[section_title, paragraph_text]]，
  与 app/services/rag/ingest.py 中现有 extract_text_from_* 系列函数签名一致。
- 子进程隔离：实际解析在独立子进程中执行（mineru_runner.py），
  避免 torch/transformers 的 GPU 占用和 C 扩展冲突影响主服务进程。
- Markdown → 段落：# / ## / ### 标题作为 section_title，其余非空行作为段落正文，
  保留 Markdown 表格、代码块原样。
"""
import os
from pathlib import Path
from typing import List, Tuple

# 默认本地模型路径
DEFAULT_LOCAL_MODEL_PATH = r"E:\model\MinerU2.5-Pro-2605-1.2B"


# MinerU 启用开关
def is_mineru_enabled() -> bool:
    """判断是否启用 MinerU 解析路径"""
    return os.environ.get("USE_MINERU", "").lower() in ("1", "true", "yes", "on")


def get_local_model_path() -> str:
    """获取本地模型路径"""
    return os.environ.get("MINERU_LOCAL_MODEL_PATH", DEFAULT_LOCAL_MODEL_PATH)


def get_mineru_timeout() -> int:
    """获取单文件解析超时秒数"""
    try:
        return max(60, int(os.environ.get("MINERU_TIMEOUT", "1200")))
    except ValueError:
        return 1200


# MinerU 本地模型支持的扩展名
# PDF/Office 文档先转图片，再用视觉模型解析；图片直接解析
MINERU_LOCAL_FORMATS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp",
}


def mineru_supported_formats() -> set:
    """返回当前配置下 MinerU 支持的扩展名集合"""
    if not is_mineru_enabled():
        return set()
    return MINERU_LOCAL_FORMATS


def is_mineru_sdk_available() -> bool:
    """检测本地 MinerU 模型是否可用

    检查模型目录是否存在 + mineru_vl_utils/transformers/fitz 可导入。
    结果做进程内缓存避免重复开销。
    """
    global _SDK_AVAILABLE_CACHE
    if _SDK_AVAILABLE_CACHE is not None:
        return _SDK_AVAILABLE_CACHE

    _SDK_AVAILABLE_CACHE = _check_local_availability()

    if not _SDK_AVAILABLE_CACHE:
        print("[MinerU] 本地解析后端不可用，将回退本地解析器")
    return _SDK_AVAILABLE_CACHE


def _check_local_availability() -> bool:
    """检查本地模式依赖：模型目录 + mineru_vl_utils + transformers + fitz"""
    model_path = get_local_model_path()
    if not os.path.isdir(model_path):
        print(f"[MinerU] 本地模型目录不存在: {model_path}")
        return False

    # 检查模型文件（至少要有 config.json 和 model.safetensors）
    config_file = os.path.join(model_path, "config.json")
    if not os.path.isfile(config_file):
        print(f"[MinerU] 模型目录缺少 config.json: {model_path}")
        return False

    # 检查 Python 依赖（直接导入，本地模式无段错误风险）
    try:
        import mineru_vl_utils  # noqa: F401
        import transformers  # noqa: F401
        import fitz  # noqa: F401  PyMuPDF
    except ImportError as e:
        print(f"[MinerU] 本地模式缺少依赖: {e}")
        return False

    return True


_SDK_AVAILABLE_CACHE: bool = None


def _decode_subprocess_output(data: bytes) -> str:
    """解码子进程 stdout/stderr 输出。

    Windows 下子进程默认用 cp936/GBK 编码，直接用 utf-8 解码中文会乱码，
    导致 MinerU 子进程失败时真实错误信息无法显示。
    依次尝试 utf-8 → cp936 → gbk → gb18030 → latin1，首个成功为准；
    全部失败则用 utf-8 + errors='replace' 兜底，保证不抛异常。
    """
    if not data:
        return ""
    for encoding in ("utf-8", "cp936", "gbk", "gb18030", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _markdown_to_paragraphs(markdown: str) -> List[Tuple[str, str]]:
    """
    将 MinerU 返回的 Markdown 文本切分为段落列表。

    规则：
    - # / ## / ### / #### 等标题行 → 更新 current_section，不作为段落输出
    - 空行 → 段落分隔（不输出）
    - 其余非空行 → 作为 (current_section, line) 输出
    - Markdown 表格行（| ... |）按表格整体合并为一个段落，section_title=表格前最近的标题
    - 代码块（``` ... ```）整体作为一个段落保留

    Args:
        markdown: MinerU 输出的 Markdown 字符串

    Returns:
        [(section_title, paragraph_text), ...]
    """
    if not markdown or not markdown.strip():
        return []

    paragraphs: List[Tuple[str, str]] = []
    current_section = ""
    table_buffer: List[str] = []
    code_buffer: List[str] = []
    in_code_block = False

    def flush_table():
        nonlocal table_buffer
        if table_buffer:
            table_text = "\n".join(table_buffer)
            paragraphs.append((current_section or "表格", table_text))
            table_buffer = []

    def flush_code():
        nonlocal code_buffer
        if code_buffer:
            code_text = "\n".join(code_buffer)
            paragraphs.append((current_section or "代码块", code_text))
            code_buffer = []

    for raw_line in markdown.split("\n"):
        line = raw_line.rstrip()

        # 代码块处理（``` 包裹）
        if line.strip().startswith("```"):
            if in_code_block:
                code_buffer.append(line)
                flush_code()
                in_code_block = False
            else:
                flush_table()
                in_code_block = True
                code_buffer.append(line)
            continue

        if in_code_block:
            code_buffer.append(raw_line)
            continue

        stripped = line.strip()
        if not stripped:
            # 空行：先冲刷表格，保留段落分隔语义
            flush_table()
            continue

        # 标题行
        if stripped.startswith("#"):
            # 先冲刷掉缓存的表格
            flush_table()
            # 去除前导 # 和空白
            title = stripped.lstrip("#").strip()
            if title:
                current_section = title
            continue

        # Markdown 表格行（| ... |）
        if stripped.startswith("|") and stripped.endswith("|"):
            table_buffer.append(stripped)
            continue
        else:
            # 非表格行：先冲刷已缓存的表格
            flush_table()

            paragraphs.append((current_section, stripped))

    # 收尾
    flush_table()
    flush_code()

    return paragraphs


def extract_text_with_mineru(
    file_path: str,
    timeout: int = None,
) -> List[Tuple[str, str]]:
    """
    使用本地 MinerU 模型解析文档并返回段落列表。

    通过 mineru_runner.py 子进程加载本地 MinerU2.5-Pro 模型解析。
    任何失败（模型缺失、GPU OOM、推理错误）均返回空列表，
    调用方应回退到本地解析器。

    Args:
        file_path: 本地文件路径
        timeout: 单文件超时秒数

    Returns:
        [(section_title, paragraph_text), ...] 列表；
        失败时返回空列表，调用方应回退到本地解析器。
    """
    if not is_mineru_enabled():
        return []

    if not is_mineru_sdk_available():
        return []

    if not os.path.isfile(file_path):
        print(f"[MinerU] 文件不存在: {file_path}")
        return []

    resolved_timeout = timeout or get_mineru_timeout()

    # 文件扩展名校验
    ext = Path(file_path).suffix.lower()
    if ext not in mineru_supported_formats():
        print(f"[MinerU] 不支持的扩展名 {ext}")
        return []

    filename = os.path.basename(file_path)
    print(f"[MinerU] 开始解析: {filename}")

    # 通过子进程调用 MinerU，避免模型加载的 GPU 占用和 C 扩展冲突影响主服务
    import subprocess
    import sys
    import json as _json

    runner_path = os.path.join(os.path.dirname(__file__), "mineru_runner.py")
    cmd = [sys.executable, runner_path, file_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=resolved_timeout + 60,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        print(f"[MinerU] 子进程超时 ({filename})")
        return []
    except Exception as e:
        print(f"[MinerU] 子进程调用失败 ({filename}): {e}")
        return []

    if result.returncode < 0:
        print(f"[MinerU] 子进程崩溃 (signal={-result.returncode}, {filename})，回退本地解析器")
        return []

    if result.returncode != 0:
        stderr_msg = _decode_subprocess_output(result.stderr)[-500:]
        # runner 协议：失败时 stdout 也输出 JSON {"status":"error","message":"...","traceback":"..."}
        # 必须读取 stdout 才能拿到真实错误详情（stderr 只有日志，没有 traceback）
        stdout_msg = _decode_subprocess_output(result.stdout)
        error_detail = ""
        try:
            err_data = _json.loads(stdout_msg)
            if isinstance(err_data, dict) and err_data.get("status") == "error":
                error_detail = err_data.get("message", "")
                tb = err_data.get("traceback")
                if tb:
                    error_detail += f"\n--- traceback ---\n{tb}"
        except _json.JSONDecodeError:
            # stdout 不是 JSON（可能是 import 阶段崩溃，无输出）
            if stdout_msg.strip():
                error_detail = f"(stdout 非JSON) {stdout_msg[-500:]}"
        print(f"[MinerU] 子进程退出码 {result.returncode} ({filename}):")
        if error_detail:
            print(f"  [错误详情] {error_detail}")
        if stderr_msg:
            print(f"  [stderr] {stderr_msg}")
        return []

    try:
        stdout_text = _decode_subprocess_output(result.stdout)
        data = _json.loads(stdout_text)
    except (_json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[MinerU] JSON 解析失败 ({filename}): {e}")
        return []

    if data.get("status") != "ok":
        print(f"[MinerU] 解析失败 ({filename}): {data.get('message', 'unknown')}")
        return []

    paragraphs = [(p[0], p[1]) for p in data.get("paragraphs", [])]
    markdown_len = len(data.get("markdown", ""))
    print(f"[MinerU] 解析完成: {filename} → {len(paragraphs)} 段落, {markdown_len} 字符")
    return paragraphs


def is_file_supported_by_mineru(file_path: str) -> bool:
    """判断给定文件是否可被当前 MinerU 配置解析"""
    if not is_mineru_enabled() or not is_mineru_sdk_available():
        return False
    ext = Path(file_path).suffix.lower()
    return ext in mineru_supported_formats()
