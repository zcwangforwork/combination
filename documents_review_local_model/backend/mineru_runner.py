"""
MinerU 子进程执行器

在独立子进程中执行 MinerU 本地模型解析，避免模型加载的 GPU 显存占用和
C 扩展冲突影响主服务进程。即使此子进程崩溃，主服务仍能正常运行
并回退到本地解析器。

调用方式：
    python -m mineru_runner <file_path>
    或
    python mineru_runner.py <file_path>

环境变量：
    MINERU_LOCAL_MODEL_PATH: 本地模型目录
    KMP_DUPLICATE_LIB_OK: 必须为 TRUE（避免 torch/pyarrow OpenMP 冲突）

输出协议（JSON 到 stdout，日志到 stderr）：
    成功：{"status": "ok", "markdown": "...", "paragraphs": [["section", "text"], ...]}
    失败：{"status": "error", "message": "..."}

移植自 design_planning_generation_local_model 项目：
- project_root 由 parent.parent.parent 调整为 parent（backend/ 即项目根）
- import 路径 `from app.services.mineru_local` 调整为 `from mineru_local`
"""
import os
import sys
import json
from pathlib import Path

# 子进程独立启动时 sys.path[0] 是 backend/ 目录，本身就在搜索路径中，
# 但仍注入项目根目录到 sys.path 以兼容从其他位置启动的场景。
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 必须在任何 torch/transformers 相关 import 之前设置
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


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
        from mineru_local import extract_text_with_local_mineru
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
