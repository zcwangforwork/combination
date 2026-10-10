# -*- coding: utf-8 -*-
"""
evals/run_eval.py — 检索层确定性评测（Phase 0 Step 0.2）

对 golden_dataset.json 的每条查询，分别对三个检索入口打分：
  retrieve            纯向量单路
  retrieve_hybrid     向量+BM25 混合（融合后）
  rerank              retrieve_and_rerank 两阶段（GPU，可 --skip-rerank）

指标（不依赖 LLM 评判，可重复）：
  Recall@5/10/15  命中 relevant_chunk_ids 任一条的查询比例（召回）
  MRR@10          首个相关结果排名倒数的均值（排序）
  NDCG@10         二值相关度的位置折损加权（排序质量）
  P95延迟 / 空结果率

用法:
    cd <project_root>
    python evals/run_eval.py [--skip-rerank] [--dataset evals/golden_dataset.json]

报告落 evals/reports/eval_YYYYMMDD_HHMMSS.json（含参数快照）。
变更必跑：任何检索参数/融合逻辑/模型改动，跑本脚本并在变更记录中附对比。
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 评测环境固定为上线前行为（off）：无密级 where、无审计落盘，保证可重复且不污染审计库
os.environ["SEC_FILTER_MODE"] = "off"

DATASET = Path(__file__).parent / "golden_dataset.json"
REPORTS = Path(__file__).parent / "reports"
TOP_KS = (5, 10, 15)


def rank_metrics(ranked_ids: list[str], gold: set[str]):
    """单条查询的 Recall@K / RR / DCG 系列（二值相关度）"""
    out = {}
    for k in TOP_KS:
        topk = ranked_ids[:k]
        out[f"recall@{k}"] = 1.0 if gold & set(topk) else 0.0
    rr = 0.0
    for rank, cid in enumerate(ranked_ids[:10], start=1):
        if cid in gold:
            rr = 1.0 / rank
            break
    out["rr@10"] = rr
    import math
    dcg = 0.0
    for rank, cid in enumerate(ranked_ids[:10], start=1):
        if cid in gold:
            dcg += 1.0 / math.log2(rank + 1)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), 10) + 1))
    out["ndcg@10"] = dcg / idcg if idcg > 0 else 0.0
    return out


def result_ids(results: list[dict]) -> list[str]:
    """结果列表 → chunk_id 序列（按返回顺序）。无 chunk_id 的结果按文本键生成稳定伪 id。"""
    out = []
    for r in results:
        cid = r.get("chunk_id")
        if not cid:
            cid = "text::" + (r.get("text") or "")[:120]
        out.append(cid)
    return out


def run_entry(name: str, fn, queries: list[str], gold_list: list[set]):
    per_query = []
    for q, gold in zip(queries, gold_list):
        t0 = time.time()
        try:
            results = fn(q)
            err = None
        except Exception as e:
            results, err = [], str(e)[:200]
        latency = time.time() - t0
        ids = result_ids(results or [])
        m = rank_metrics(ids, gold) if gold else {}
        m["latency"] = round(latency, 3)
        m["n_results"] = len(results or [])
        m["error"] = err
        per_query.append(m)
    agg = {}
    for k in [f"recall@{n}" for n in TOP_KS] + ["rr@10", "ndcg@10"]:
        vals = [pq.get(k, 0.0) for pq in per_query]
        agg[k] = round(sum(vals) / len(vals), 4) if vals else 0.0
    lat = [pq["latency"] for pq in per_query]
    lat.sort()
    agg["p95_latency_sec"] = round(lat[max(0, int(len(lat) * 0.95) - 1)], 2) if lat else 0.0
    agg["mean_latency_sec"] = round(statistics.mean(lat), 2) if lat else 0.0
    agg["empty_rate"] = round(sum(1 for pq in per_query if pq["n_results"] == 0) / len(per_query), 4)
    agg["error_count"] = sum(1 for pq in per_query if pq["error"])
    print(f"\n[{name}] " + "  ".join(f"{k}={v}" for k, v in agg.items()))
    return {"aggregate": agg, "per_query": per_query}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--skip-rerank", action="store_true", help="跳过 GPU 精排入口")
    ap.add_argument("--top-k", type=int, default=15, help="各入口返回条数")
    args = ap.parse_args()

    data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    queries = [d["query"] for d in data]
    gold_list = [set(d["relevant_chunk_ids"]) for d in data]
    n_reviewed = sum(1 for d in data if d.get("reviewed"))
    print(f"[eval] {len(queries)} 条查询（{n_reviewed} 条已人工审核）top_k={args.top_k}")

    from app.services.rag.vector_store import VectorStore
    store = VectorStore()

    report = {
        "meta": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "dataset": str(args.dataset),
            "n_queries": len(queries),
            "n_reviewed": n_reviewed,
            "top_k": args.top_k,
            "skip_rerank": args.skip_rerank,
            "sec_filter_mode": "off(评测固定)",
        },
        "queries": queries,
        "entries": {},
    }

    report["entries"]["retrieve"] = run_entry(
        "retrieve",
        lambda q: store.retrieve(query=q, top_k=args.top_k),
        queries, gold_list)

    report["entries"]["hybrid"] = run_entry(
        "hybrid",
        lambda q: store.retrieve_hybrid(query=q, top_k=args.top_k),
        queries, gold_list)

    if not args.skip_rerank:
        # 两阶段：粗召回 candidate_pool=50（与 search_kb 线上一致）
        report["entries"]["rerank"] = run_entry(
            "rerank",
            lambda q: store.retrieve_and_rerank(query=q, top_k=args.top_k,
                                                candidate_pool_size=50),
            queries, gold_list)

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[eval] 报告 → {out}")


if __name__ == "__main__":
    main()
