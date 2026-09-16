"""
RAG 两阶段检索 A/B 对比测试

对比 baseline (retrieve_hybrid) 与 with-rerank (retrieve_and_rerank) 的：
1. 检索结果差异（Top-K 内容对比）
2. 延迟差异
3. 精排分数分布

用法:
    cd <project_root>
    python -m tests.test_rerank_ab

输出:
    rerank_ab_results.json — 详细对比结果，供人工评估
"""

import json
import os
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 测试查询集 — 覆盖三类典型场景
TEST_QUERIES = [
    # 精确标准查询
    "ISO 14971 风险管理 危害判定",
    "GB 9706.1 电气安全 漏电流限值",
    "YY/T 0316 风险可接受准则",
    # 模糊语义查询
    "胰岛素泵 软件确认 测试方法",
    "贴敷式 输注精度 性能要求",
    # 混合查询（中文+标准号）
    "可用性工程 IEC 62366 形成性评估",
    "生物相容性 ISO 10993 细胞毒性试验",
]


def benchmark(top_k: int = 5, candidate_pool: int = 30):
    """对每个测试查询对比 baseline vs rerank"""
    from app.services.rag.vector_store import VectorStore

    store = VectorStore()
    results = {"baseline": [], "rerank": []}

    for query in TEST_QUERIES:
        print(f"\n[Query] {query}")

        # ── Baseline: 单阶段混合检索 ──
        t0 = time.time()
        try:
            baseline = store.retrieve_hybrid(
                query=query,
                top_k=top_k,
                vector_weight=0.85,
            )
            t_baseline = time.time() - t0
        except Exception as e:
            baseline = []
            t_baseline = time.time() - t0
            print(f"  baseline ERROR: {e}")

        # ── With Rerank: 两阶段检索 ──
        t0 = time.time()
        try:
            reranked = store.retrieve_and_rerank(
                query=query,
                top_k=top_k,
                candidate_pool_size=candidate_pool,
                vector_weight=0.85,
            )
            t_rerank = time.time() - t0
        except Exception as e:
            reranked = []
            t_rerank = time.time() - t0
            print(f"  rerank ERROR: {e}")

        # 记录结果
        results["baseline"].append({
            "query": query,
            "results": [
                {
                    "source": r.get("source_file", "")[:60],
                    "preview": r.get("text", "")[:80],
                    "similarity": round(r.get("similarity", 0), 4),
                }
                for r in baseline
            ],
            "latency_sec": round(t_baseline, 2),
        })
        results["rerank"].append({
            "query": query,
            "results": [
                {
                    "source": r.get("source_file", "")[:60],
                    "preview": r.get("text", "")[:80],
                    "rerank_score": round(r.get("rerank_score", 0), 4),
                }
                for r in reranked
            ],
            "latency_sec": round(t_rerank, 2),
        })

        print(f"  baseline: {len(baseline)} results, {t_baseline:.1f}s")
        print(f"  rerank:   {len(reranked)} results, {t_rerank:.1f}s")

    # 保存详细结果
    out_path = PROJECT_ROOT / "rerank_ab_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[Output] 详细结果已保存至: {out_path}")

    # 打印对比摘要
    avg_baseline = sum(r["latency_sec"] for r in results["baseline"]) / len(TEST_QUERIES)
    avg_rerank = sum(r["latency_sec"] for r in results["rerank"]) / len(TEST_QUERIES)

    # 计算Top-K重合率（衡量排序变化）
    overlap_counts = []
    for i, query in enumerate(TEST_QUERIES):
        base_set = {r["preview"] for r in results["baseline"][i]["results"]}
        rerank_set = {r["preview"] for r in results["rerank"][i]["results"]}
        overlap = len(base_set & rerank_set) if base_set else 0
        overlap_counts.append(overlap)

    print(f"\n{'='*60}")
    print(f"A/B 对比摘要 (top_k={top_k}, candidate_pool={candidate_pool})")
    print(f"{'='*60}")
    print(f"平均延迟:  baseline={avg_baseline:.2f}s  rerank={avg_rerank:.2f}s  Δ=+{avg_rerank-avg_baseline:.2f}s")
    print(f"Top-K重合率: 平均 {sum(overlap_counts)/len(overlap_counts):.1f}/{top_k} "
          f"(重合越低，排序变化越大)")
    print(f"{'='*60}")
    print(f"\n提示: 请人工评估 rerank_ab_results.json 中各查询的 Top-K 结果相关性，")
    print(f"     对比 baseline 与 rerank 的检索质量。")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--pool", type=int, default=30)
    args = parser.parse_args()
    benchmark(top_k=args.top_k, candidate_pool=args.pool)
