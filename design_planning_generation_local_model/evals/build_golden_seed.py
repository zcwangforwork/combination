# -*- coding: utf-8 -*-
"""
evals/build_golden_seed.py — golden dataset 种子构建器（半自动，Phase 0 Step 0.1）

从 test_rerank_ab.py 的 7 条真实测试查询出发扩充到 12 条，用**确定性标记匹配**
（标准号 + 关键词 同时命中）对主库 insulin_pump_kb 全量 chunk 做 auto-label，
产出 evals/golden_dataset.json。所有条目 reviewed=false —— **必须人工审核后
才可作为正式基线**（人工审核时把 reviewed 改 true / 修正 relevant_chunk_ids）。

用法:
    cd <project_root>
    python evals/build_golden_seed.py

只读操作：直接 PersistentClient 打开 chroma_db_insulin_pump，不导入 app 代码、
不写库。后续扩充（80-150 条）按方案用 MiniMax 从 chunks 生成"用户会怎么问"
再加人工审核，本脚本只负责种子。
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CHROMA_DIR = PROJECT_ROOT / "chroma_db_insulin_pump"
COLLECTION = "insulin_pump_kb"
OUT = Path(__file__).parent / "golden_dataset.json"

# 每条：查询 + 标记规则。std=标准号（归一化子串），kw=关键词（归一化子串），
# 命中条件：norm(chunk) 含任一 std **且** 含任一 kw；非标准查询只用 kw（至少 1 个）。
SEED = [
    # ── 精确标准号查询（来自 test_rerank_ab.py 的 7 条）──
    {"query": "ISO 14971 风险管理 危害判定", "std": ["14971"], "kw": ["风险", "危害"],
     "query_type": "standard_no", "notes": "精确标准号"},
    {"query": "GB 9706.1 电气安全 漏电流限值", "std": ["9706.1"], "kw": ["漏电流", "电气安全"],
     "query_type": "standard_no", "notes": "精确标准号+参数限值"},
    {"query": "YY/T 0316 风险可接受准则", "std": ["0316"], "kw": ["可接受", "风险"],
     "query_type": "standard_no", "notes": "精确标准号"},
    # ── 模糊语义查询 ──
    {"query": "胰岛素泵 软件确认 测试方法", "std": [], "kw": ["软件确认", "软件验证", "软件测试"],
     "query_type": "semantic", "notes": "模糊语义"},
    {"query": "贴敷式 输注精度 性能要求", "std": [], "kw": ["输注精度", "输注准确"],
     "query_type": "semantic", "notes": "模糊语义"},
    # ── 混合查询（来自 test_rerank_ab.py）──
    {"query": "可用性工程 IEC 62366 形成性评估", "std": ["62366"], "kw": ["形成", "可用性"],
     "query_type": "mixed", "notes": "中英混合"},
    {"query": "生物相容性 ISO 10993 细胞毒性试验", "std": ["10993"], "kw": ["细胞毒性", "生物相容"],
     "query_type": "mixed", "notes": "中英混合"},
    # ── 扩充条目（本次新增）──
    {"query": "GB/T 42061 质量管理体系 文件控制", "std": ["42061"], "kw": ["文件控制", "质量管理体系"],
     "query_type": "standard_no", "notes": "QMS 体系标准"},
    {"query": "GB/T 42062 风险管理计划", "std": ["42062"], "kw": ["风险管理计划", "风险管理"],
     "query_type": "standard_no", "notes": "风险管理计划文档"},
    {"query": "IEC 62304 软件安全分类", "std": ["62304"], "kw": ["软件", "安全"],
     "query_type": "mixed", "notes": "软件生命周期等级"},
    {"query": "报警系统 IEC 60601-1-8", "std": ["60601"], "kw": ["报警", "警报"],
     "query_type": "mixed", "notes": "报警标准"},
    {"query": "电磁兼容 YY 9706.102", "std": ["9706.102"], "kw": ["电磁兼容", "emc"],
     "query_type": "standard_no", "notes": "EMC 标准"},
]


def norm(s: str) -> str:
    """归一化：小写、去空白/斜杠/破折号（标准号变体不变匹配的基础）"""
    return re.sub(r"[\s/\-—–_·]", "", (s or "").lower())


def main():
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))
    coll = client.get_collection(name=COLLECTION)
    n = coll.count()
    print(f"[golden-seed] collection '{COLLECTION}' 共 {n} chunks")

    # 全量拉取（9622 条，一次性读入内存做确定性匹配）
    data = coll.get(include=["documents", "metadatas"])
    ids, docs, metas = data["ids"], data["documents"], data["metadatas"]

    dataset = []
    for item in SEED:
        ndocs = [norm(d) for d in docs]
        scored = []
        for i, nd in enumerate(ndocs):
            std_hit = any(m in nd for m in item["std"]) if item["std"] else True
            kw_hit = any(m in nd for m in item["kw"])
            if std_hit and kw_hit:
                # 相关性排序依据：命中的标记总数（粗排，供人工审核参考）
                score = sum(1 for m in item["std"] + item["kw"] if m in nd)
                scored.append((score, i))
        scored.sort(key=lambda t: -t[0])
        top = scored[:6]  # 每条查询最多 6 个 gold chunk
        entry = {
            "query": item["query"],
            "relevant_chunk_ids": [ids[i] for _, i in top],
            "relevant_source_files": sorted({(metas[i] or {}).get("source_file", "")
                                             for _, i in top}),
            "query_type": item["query_type"],
            "notes": item["notes"],
            "auto_label_rule": {"std": item["std"], "kw": item["kw"]},
            "reviewed": False,  # 人工审核后置 true
        }
        dataset.append(entry)
        print(f"  [{len(top):>2}] {item['query']}  ← {entry['relevant_source_files'][:3]}")

    OUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[golden-seed] 写出 {len(dataset)} 条 → {OUT}")
    print("[golden-seed] 提醒：全部 reviewed=false，正式基线前需人工逐条审核")


if __name__ == "__main__":
    main()
