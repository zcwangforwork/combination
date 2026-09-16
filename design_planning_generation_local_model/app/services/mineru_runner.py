"""
MinerU 子进程执行器

在独立子进程中执行 MinerU 本地模型解析，避免模型加载的 GPU 显存占用和
C 扩展冲突影响主服务进程。即使此子进程崩溃，主服务仍能正常运行
并回退到本地解析器。

调用方式：
    python -m app.services.mineru_runner <file_path>

环境变量：
    MINERU_LOCAL_MODEL_PATH: 本地模型目录
    KMP_DUPLICATE_LIB_OK: 必须为 TRUE（避免 torch/pyarrow OpenMP 冲突）

输出协议（JSON 到 stdout，日志到 stderr）：
    成功：{"status": "ok", "markdown": "...", "paragraphs": [["section", "text"], ...]}
    失败：{"status": "error", "message": "..."}
"""
import os
import sys
import json
from pathlib import Path

# 子进程独立启动时 sys.path[0] 是 app/services/ 目录，不含项目根，
# 导致 `from app.services.mineru_local import ...` 找不到 app 包。
# 手动注入项目根目录到 sys.path（与 app/services/rag/ingest.py 一致的做法）。
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 必须在任何 torch/transformers 相关 import 之前设置
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Windows 子进程 stdout/stderr 默认 cp936/gbk 编码，无法输出 ₹/✓ 等非 GBK 字符，
# 会导致 print(json.dumps(..., ensure_ascii=False)) 抛 UnicodeEncodeError 子进程退出码 1，
# 父进程收到空输出回退本地解析器。强制 utf-8 编码，errors="replace" 保证不会因编码再次崩溃。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    # Python<3.7 或 stdout 已被替换时 fallback：用 TextIOWrapper 包一层
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "缺少文件路径参数"}))
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.isfile(file_path):
        print(json.dumps({"status": "error", "message": f"文件不存在: {file_path}"}))
        sys.exit(1)

    filename = os.path.basename(file_path)

    markdown = _run_local(file_path, filename)

    if markdown is None:
        # 错误已在 _run_local 中以 JSON 输出，这里直接退出
        sys.exit(1)

    paragraphs = _markdown_to_paragraphs(markdown)
    print(f"[MinerU-Runner] 完成: {filename} → {len(paragraphs)} 段落", file=sys.stderr)

    result = {
        "status": "ok",
        "markdown": markdown,
        "paragraphs": paragraphs,
        "filename": filename,
    }
    print(json.dumps(result, ensure_ascii=False))


def _run_local(file_path: str, filename: str):
    """本地模型模式"""
    print(f"[MinerU-Runner] 开始本地解析: {filename}", file=sys.stderr)
    try:
        from app.services.mineru_local import extract_text_with_local_mineru
        return extract_text_with_local_mineru(file_path)
    except FileNotFoundError as e:
        print(json.dumps({"status": "error", "message": f"模型文件未找到: {e}"}))
        return None
    except Exception as e:
        import traceback
        tb = traceback.format_exc()[-500:]
        print(json.dumps({"status": "error", "message": f"本地解析失败: {e}", "traceback": tb}))
        return None


def _markdown_to_paragraphs(markdown: str) -> list:
    """将 Markdown 切分为段落列表 [(section_title, text), ...]"""
    if not markdown or not markdown.strip():
        return []

    paragraphs = []
    current_section = ""
    table_buffer = []
    code_buffer = []
    in_code_block = False

    def flush_table():
        nonlocal table_buffer
        if table_buffer:
            paragraphs.append((current_section or "表格", "\n".join(table_buffer)))
            table_buffer = []

    def flush_code():
        nonlocal code_buffer
        if code_buffer:
            paragraphs.append((current_section or "代码块", "\n".join(code_buffer)))
            code_buffer = []

    for raw_line in markdown.split("\n"):
        line = raw_line.rstrip()

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
            flush_table()
            continue

        if stripped.startswith("#"):
            flush_table()
            title = stripped.lstrip("#").strip()
            if title:
                current_section = title
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_buffer.append(stripped)
            continue
        else:
            flush_table()
            paragraphs.append((current_section, stripped))

    flush_table()
    flush_code()
    return paragraphs


if __name__ == "__main__":
    main()
