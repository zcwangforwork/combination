"""
法规结构化摄入工具（方案模块三）：把法规原文按 章/条 拆条摄入
qms_doc_regulations collection，供检索层按条款级召回 + 挂靠提示词引用。

框架说明（数据红线）：
- 本脚本只做「结构化摄入框架」，不内置任何法规原文。107号公告等法规文本
  必须由 RA 人员从官方渠道获取后放入源目录，经双人两源核对后再摄入。
- 源文件为纯文本/Markdown：以「第X章」为章边界、「第X条」为条边界拆条；
  无章/条标记的行按上下文归入最近的章/条。
- 结构化元数据标签（来源类型/公告号/章条/施行状态/新旧映射/doc_type关联）
  写入 chunk 正文标签头（BM25+向量两路可见）与 section_title（检索元数据）。

用法:
    python ingest_regulation.py <源文件或目录> \
        --title "医疗器械生产质量管理规范" \
        --announce "2025年第107号" \
        --source-type 公告 \
        --status 现行 \
        [--replaces "2014年第64号"] \
        [--doc-types design_development_plan,design_input] \
        [--sec-level 1]

摄入后自动维护 app/data/doc_registry.json（cn_norm_lint R01 数据源）：
登记 公告号 与正文中出现的内部文件编号。
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.rag.vector_store import VectorStore

# 章/条标题识别（中文数字 + 阿拉伯数字两种编号体系）
_CHAPTER_RE = re.compile(r"^\s*第[一二三四五六七八九十百\d]+章.*$")
_ARTICLE_RE = re.compile(r"^\s*第[一二三四五六七八九十百\d]+条")
_ARTICLE_ID_RE = re.compile(r"第[一二三四五六七八九十百\d]+条")
_REGISTRY_PATH = project_root / "app" / "data" / "doc_registry.json"


def _load_registry() -> dict:
    if _REGISTRY_PATH.exists():
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"documents": []}


def _save_registry(reg: dict) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def _registry_add(reg: dict, number: str) -> bool:
    """登记文件/公告编号（去重）。返回是否新增。"""
    docs = reg.setdefault("documents", [])
    if isinstance(docs, list) and not any(d.get("number") == number for d in docs if isinstance(d, dict)):
        docs.append({"number": number})
        return True
    return False


def parse_regulation(path: Path) -> list[dict]:
    """把法规源文件按 章/条 拆为结构化条目。

    Returns:
        [{"chapter": "第六章 设计开发", "article": "第三十条",
          "text": "第三十条 ……"}, ...]
        无「第X条」标记时整章/整文件作为单条目（article 为空）。
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip() for ln in f.readlines()]

    articles: list[dict] = []
    chapter = ""
    cur_article_no = ""
    buf: list[str] = []

    def _flush():
        text = "\n".join(buf).strip()
        if text:
            articles.append({"chapter": chapter, "article": cur_article_no, "text": text})
        buf.clear()

    for ln in lines:
        if _CHAPTER_RE.match(ln):
            _flush()
            chapter = ln.strip()
            cur_article_no = ""
            continue
        m = _ARTICLE_RE.match(ln)
        if m:
            _flush()
            cur_article_no = _ARTICLE_ID_RE.search(ln).group(0)
            buf.append(ln.strip())
            continue
        if ln.strip():
            buf.append(ln.strip())
    _flush()
    return articles


def build_tag_header(args) -> str:
    """chunk 正文标签头：结构化元数据（BM25+向量两路可见）。"""
    parts = [f"【{args.title}", args.announce, args.source_type, args.status]
    if args.replaces:
        parts.append(f"替代{args.replaces}")
    header = "｜".join(p for p in parts if p) + "】"
    if args.doc_types:
        header += f"[关联文档类型: {','.join(args.doc_types)}]"
    return header


def ingest_regulation_file(path: Path, vector_store: VectorStore, args) -> int:
    """摄入单个法规文件。Returns: chunk 数。"""
    articles = parse_regulation(path)
    if not articles:
        print(f"  跳过: {path.name}（空文件或无可识别内容）")
        return 0

    header = build_tag_header(args)
    source_file = os.path.basename(path)
    # 法规库批次版本（审计标记：数据双源核对轮次，见方案 REG_DB_VERSION）
    reg_db_version = os.getenv("REG_DB_VERSION", "v0")
    chunks = []
    for i, art in enumerate(articles):
        loc = " / ".join(x for x in (art["chapter"], art["article"]) if x)
        text = f"{header}{('｜' + loc) if loc else ''}\n\n{art['text']}"
        chunks.append({
            "chunk_id": f"reg::{source_file}::{i}",
            "text": text,
            "doc_type": "regulation",
            "source_file": source_file,
            "section_title": loc or "全文",
            "chunk_index": i,
            "original_filename": source_file,
        })
    # [SEC] 密级五字段由 add_chunks 收口打标
    vector_store.add_chunks(chunks, sec_level=args.sec_level,
                            acl_version=f"reg:{reg_db_version}:{args.announce or args.title}")
    print(f"  [OK] {source_file}: {len(chunks)} 条 (章/条拆分, collection=regulations)")
    return len(chunks)


def collect_source_files(target: str) -> list[Path]:
    p = Path(target)
    if p.is_dir():
        return sorted(x for x in p.iterdir()
                      if x.suffix.lower() in (".txt", ".md"))
    return [p] if p.suffix.lower() in (".txt", ".md") else []


def main():
    parser = argparse.ArgumentParser(description="法规结构化摄入（方案模块三）")
    parser.add_argument("target", help="法规源文件或目录（txt/md，官方原文）")
    parser.add_argument("--title", required=True, help="法规名称（如 医疗器械生产质量管理规范）")
    parser.add_argument("--announce", default="", help="公告号（如 2025年第107号）")
    parser.add_argument("--source-type", default="公告", dest="source_type",
                        help="来源类型（公告/通告/标准等）")
    parser.add_argument("--status", default="现行", help="施行状态（现行/废止/被替代）")
    parser.add_argument("--replaces", default="", help="替代的旧公告号（新旧映射）")
    parser.add_argument("--doc-types", default="", dest="doc_types",
                        help="关联文档类型（逗号分隔 doc_types.py 键名，供挂靠提示词）")
    parser.add_argument("--sec-level", type=int, default=1, dest="sec_level",
                        help="[SEC] 批次密级 0-3（法规公开文本缺省 1=内部）")
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    args = parser.parse_args()
    args.doc_types = [x.strip() for x in args.doc_types.split(",") if x.strip()]

    files = collect_source_files(args.target)
    if not files:
        print(f"未找到可摄入的 txt/md 源文件: {args.target}")
        return

    print("=" * 60)
    print("法规结构化摄入工具（方案模块三）")
    print("=" * 60)
    print(f"  法规: {args.title} {args.announce}")
    print(f"  状态: {args.source_type} / {args.status}"
          + (f" / 替代 {args.replaces}" if args.replaces else ""))
    print(f"  密级: {args.sec_level}（0公开/1内部/2秘密/3机密）")
    print(f"  源文件: {len(files)} 个")
    print("\n⚠️ 数据红线：请确认源文件为官方渠道原文且已经双人两源核对。")

    if not args.yes:
        confirm = input("是否继续摄入到 qms_doc_regulations？(y/n): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    # collection=regulations → 实际名 qms_doc_regulations（检索侧已加入 QUERY_COLLECTIONS）
    vector_store = VectorStore(collection_name="regulations")
    total = sum(ingest_regulation_file(f, vector_store, args) for f in files)
    VectorStore.invalidate_bm25_cache()

    # 维护 doc_registry.json（R01 数据源）：登记公告号 + 正文出现的内部文件编号
    reg = _load_registry()
    added = []
    if args.announce and _registry_add(reg, args.announce):
        added.append(args.announce)
    if args.replaces and _registry_add(reg, args.replaces):
        added.append(args.replaces)
    if added:
        _save_registry(reg)
        print(f"\ndoc_registry.json 登记: {'、'.join(added)}")

    print("\n摄入完成!")
    print(f"  条款条目: {total} 条")
    print(f"  collection 总量: {vector_store.count()}")


if __name__ == "__main__":
    main()
