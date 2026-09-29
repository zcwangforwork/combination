"""
存量密级回填脚本（方案 §4.3，2026-09-28 新增）

用法:
    python tools/backfill_sec_level.py --acl-version 20260928a [--level 3] [--sec-source inherit] [--dry-run]

功能:
    为 ChromaDB 中缺少密级字段的存量 chunk 回填 sec_level 五字段。
    缺省回填为 3（机密）——先全量保守、后批量精标降级（fail-closed 起步）。

特性（由 sec_admin.backfill_all_collections 提供）:
    - 幂等：已带本 acl_version 标记的 chunk 自动跳过，重跑无副作用
    - 断点续传：进度文件记录各 collection 处理 offset，中断后重跑续传
    - dry-run：只统计待回填数量，不落库
"""
import sys
import json
import argparse
from pathlib import Path

# 添加项目根目录（tools/ 的上一级）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.sec_admin import backfill_all_collections


def main():
    parser = argparse.ArgumentParser(description="存量 chunk 密级回填工具")
    parser.add_argument(
        "--acl-version",
        required=True,
        help="ACL 批次版本号（如 20260928a）；幂等标记 + 断点文件均按此命名"
    )
    parser.add_argument(
        "--level",
        type=int,
        default=3,
        choices=[0, 1, 2, 3],
        help="回填密级 0-3（缺省 3=机密，保守起步）"
    )
    parser.add_argument(
        "--sec-source",
        default="inherit",
        choices=["manual", "cover", "inherit"],
        help="密级来源标记（缺省 inherit=批量继承）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只统计待回填数量，不实际写入"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("存量密级回填工具")
    print("=" * 70)
    print(f"  acl_version : {args.acl_version}")
    print(f"  level       : {args.level}")
    print(f"  sec_source  : {args.sec_source}")
    print(f"  dry_run     : {args.dry_run}")
    print()

    try:
        stats = backfill_all_collections(
            acl_version=args.acl_version,
            level=args.level,
            sec_source=args.sec_source,
            operator="(script:backfill_sec_level)",
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"\n[失败] 回填执行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 70)
    print("回填完成!" if not args.dry_run else "回填预览完成 (dry-run，未写入)!")
    print("=" * 70)
    print(f"  扫描 chunk 总数: {stats['total_scanned']}")
    print(f"  {'待回填' if args.dry_run else '已回填'} chunk 数: {stats['total_updated']}")
    print(f"  回填密级: {args.level}")
    for coll_name, info in stats["collections"].items():
        if "error" in info:
            print(f"  [{coll_name}] 出错: {info['error']}")
        else:
            print(f"  [{coll_name}] chunks={info['chunks']} "
                  f"updated={info['updated']} resumed_from={info['resumed_from']}")

    if args.dry_run:
        print("\n确认无误后去掉 --dry-run 重新执行即可正式回填。")


if __name__ == "__main__":
    main()
