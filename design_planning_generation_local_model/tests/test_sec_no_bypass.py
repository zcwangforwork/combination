"""旁路封堵静态守卫（方案 §5.2 唯一收口 / §5.6 旁路封堵）

用 AST 扫描全部线上代码（app/ + 项目根脚本）中对 Chroma collection 的
`.query(` 调用，要求每一个都必须：
  a) 携带 `where=` 关键字参数（经 sec_filter 收口构造），或
  b) 采用 `**query_kwargs` 风格且同一窗口内存在 `["where"]` 赋值，或
  c) 位于下方白名单（新增白名单条目必须写明理由）。

这是防止未来新检索出口"忘带密级过滤"的静态绊线（tripwire）：
任何新增 `.query(` 调用若不含密级 where，本测试立即失败。
"""
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 有意豁免清单（相对路径，POSIX 风格）。新增条目必须附理由注释。
WHITELIST = {
    # probe_denied：enforce 模式探针，有意无 where（§5.5，仅取 denied 统计与 L3 样本）
    "app/services/rag/sec_filter.py",
    # 以下为离线建库/诊断脚本，查询独立离线库，不在线上检索链路（回填由 backfill 覆盖）
    "ocr_supplement_ingest.py",
    "build_insulin_pump_kb.py",
    "build_kb_local.py",
}

SCAN_GLOBS = ["app/**/*.py", "*.py"]


def _iter_py_files():
    seen = set()
    for pat in SCAN_GLOBS:
        for p in PROJECT_ROOT.glob(pat):
            if not p.is_file():
                continue
            rel = p.relative_to(PROJECT_ROOT).as_posix()
            if rel in seen or rel.startswith("temp/"):
                continue
            seen.add(rel)
            yield p, rel


def _query_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "query":
                yield node


def test_every_chroma_query_carries_sec_where():
    violations = []
    checked = 0
    for path, rel in _iter_py_files():
        if rel in WHITELIST:
            continue
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        lines = src.splitlines()
        for call in _query_calls(tree):
            checked += 1
            if any(kw.arg == "where" for kw in call.keywords):
                continue
            # **kwargs 风格：向上 30 行窗口内应有 ["where"]=... 注入
            start = max(0, (call.lineno or 1) - 30)
            end = call.end_lineno or call.lineno
            window = "\n".join(lines[start:end])
            if "**" in window and '"where"' in window:
                continue
            violations.append(f"{rel}:{call.lineno}")

    # 白名单文件已被跳过，线上应收口数 = vector_store(3) + agent_tools(3) + routes(1)
    assert checked >= 7, (
        f"扫描到的 .query( 调用数异常（{checked} < 7），静态守卫可能失效，"
        "请检查扫描范围")
    assert not violations, (
        "发现未携带密级 where 的 .query( 调用（L1 旁路，违反 §5.2 唯一收口）：\n  "
        + "\n  ".join(violations)
        + "\n请经 sec_filter.effective_query_where()/combine_where() 构造 where，"
          "或在 WHITELIST 中附理由豁免")


def test_retrieval_modules_reference_sec_collectors():
    """语义锚点：关键检索模块必须引用 sec_filter 收口函数（防重构后静默脱钩）"""
    anchors = {
        "app/services/rag/vector_store.py": "effective_query_where",
        "app/services/agent_tools.py": "effective_query_where",
        "app/api/routes.py": "combine_where",
    }
    for rel, needle in anchors.items():
        path = PROJECT_ROOT / rel
        assert path.exists(), f"锚点文件缺失: {rel}"
        assert needle in path.read_text(encoding="utf-8"), (
            f"{rel} 不再引用 sec_filter.{needle} —— 检索主链路可能绕过密级收口")
