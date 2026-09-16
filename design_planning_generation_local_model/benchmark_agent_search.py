"""
benchmark_agent_search.py — 真实调用 Agent SDK 搜索并统计耗时

测试场景：
  1. 单次搜索：测单个章节的耗时
  2. 串行多次：测 5 个章节顺序执行总耗时
  3. 并行 6 路：测 6 路并发耗时（旧默认）
  4. 并行 12 路：测 12 路并发耗时（新默认）

输出：每个用例的耗时表 + 加速比
"""
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# 加载 .env
project_root = Path(__file__).parent
load_dotenv(project_root / ".env")
sys.path.insert(0, str(project_root))

from app.services.agent_search import SyncAgentSearchService


# 测试用章节集合（覆盖常见生成场景）
TEST_CHAPTERS = [
    ("概述",       "胰岛素泵", "贴敷式，闭环控制", "risk_management_report"),
    ("风险分析",   "胰岛素泵", "贴敷式，闭环控制", "risk_management_report"),
    ("风险评估",   "胰岛素泵", "贴敷式，闭环控制", "risk_management_report"),
    ("风险控制",   "胰岛素泵", "贴敷式，闭环控制", "risk_management_report"),
    ("设计输入",   "胰岛素泵", "贴敷式，闭环控制", "design_input"),
    ("设计输出",   "胰岛素泵", "贴敷式，闭环控制", "design_output"),
    ("操作步骤",   "胰岛素泵", "贴敷式，闭环控制", "sop"),
    ("使用方法",   "胰岛素泵", "贴敷式，闭环控制", "ifu"),
    ("性能指标",   "胰岛素泵", "贴敷式，闭环控制", "product_tech_requirements"),
    ("电磁兼容",   "胰岛素泵", "贴敷式，闭环控制", "design_verification"),
    ("生物相容性", "胰岛素泵", "贴敷式，闭环控制", "design_verification"),
    ("无菌包装",   "胰岛素泵", "贴敷式，闭环控制", "design_output"),
]


def _do_search(svc, item):
    """单次搜索：返回 (chapter_name, elapsed_seconds, char_count, error_or_none)"""
    ch_name, prod_type, prod_params, doc_type = item
    t0 = time.time()
    try:
        text, _ = svc.search_regulations(
            chapter_name=ch_name,
            product_type=prod_type,
            product_params=prod_params,
            doc_type=doc_type,
        )
        return ch_name, time.time() - t0, len(text or ""), None
    except Exception as e:
        return ch_name, time.time() - t0, 0, str(e)


def case_single(svc):
    print("\n" + "=" * 80)
    print("用例 1: 单次搜索（1 个章节）")
    print("=" * 80)
    item = TEST_CHAPTERS[0]
    name, elapsed, chars, err = _do_search(svc, item)
    print(f"  章节: {name}")
    print(f"  耗时: {elapsed:.2f}s")
    print(f"  字符: {chars}")
    print(f"  错误: {err or '无'}")
    return elapsed


def case_serial(svc, n=5):
    print("\n" + "=" * 80)
    print(f"用例 2: 串行 {n} 次搜索")
    print("=" * 80)
    t0 = time.time()
    rows = []
    for i, item in enumerate(TEST_CHAPTERS[:n], 1):
        name, elapsed, chars, err = _do_search(svc, item)
        rows.append((name, elapsed, chars, err))
        print(f"  [{i}/{n}] {name:<10} {elapsed:>7.2f}s  chars={chars:<6} err={err or '-'}")
    total = time.time() - t0
    print(f"  -- 串行总耗时: {total:.2f}s")
    print(f"  -- 平均每次:   {total/n:.2f}s")
    return total, rows


def case_parallel(svc, workers, n=12):
    print("\n" + "=" * 80)
    print(f"用例: 并行 {workers} 路 × {n} 次搜索")
    print("=" * 80)
    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_do_search, svc, item): item[0] for item in TEST_CHAPTERS[:n]}
        for fut in as_completed(futures):
            name, elapsed, chars, err = fut.result()
            rows.append((name, elapsed, chars, err))
            print(f"  ✓ {name:<10} {elapsed:>7.2f}s  chars={chars:<6} err={err or '-'}")
    total = time.time() - t0
    sum_elapsed = sum(r[1] for r in rows)
    print(f"  -- 并行墙钟耗时: {total:.2f}s")
    print(f"  -- 单次累计耗时: {sum_elapsed:.2f}s")
    print(f"  -- 实际并发系数: {sum_elapsed/total:.2f}x")
    return total, rows


def main():
    print("=" * 80)
    print("Agent SDK 搜索性能 Benchmark")
    print("=" * 80)
    print(f"ANTHROPIC_API_KEY: {'已设置' if os.environ.get('ANTHROPIC_API_KEY') else '未设置'}")

    svc = SyncAgentSearchService()
    print(f"Service available: {svc.available}")
    if not svc.available:
        print("\n[ERROR] Agent SDK 不可用，跳过测试")
        print("  - 检查 ANTHROPIC_API_KEY 是否设置")
        print("  - 检查 claude-agent-sdk 是否已 pip install")
        sys.exit(1)

    results = {}

    # 用例 1: 单次
    results["single"] = case_single(svc)

    # 用例 2: 串行 5 次
    serial_total, _ = case_serial(svc, n=5)
    results["serial_5"] = serial_total

    # 用例 3: 并行 6 路 × 12 次（旧默认）
    p6_total, _ = case_parallel(svc, workers=6, n=12)
    results["parallel_6"] = p6_total

    # 用例 4: 并行 12 路 × 12 次（新默认）
    p12_total, _ = case_parallel(svc, workers=12, n=12)
    results["parallel_12"] = p12_total

    # 汇总
    print("\n" + "=" * 80)
    print("汇总")
    print("=" * 80)
    print(f"  单次搜索:                  {results['single']:>7.2f}s")
    print(f"  串行 5 次:                 {results['serial_5']:>7.2f}s  (平均 {results['serial_5']/5:.2f}s)")
    print(f"  并行 6 路 × 12 次:         {results['parallel_6']:>7.2f}s")
    print(f"  并行 12 路 × 12 次:        {results['parallel_12']:>7.2f}s")
    print("-" * 80)
    if results['parallel_6'] > 0:
        speedup = results['parallel_6'] / results['parallel_12']
        print(f"  12路 vs 6路 加速比:        {speedup:.2f}x")
    print("=" * 80)


if __name__ == "__main__":
    main()
