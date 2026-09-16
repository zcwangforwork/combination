"""
便捷脚本：摄入医械标准库到知识库
"""

import os
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.rag.ingest import ingest_all, ingest_files, get_supported_files


def main():
    print("=" * 60)
    print("医械标准库知识库摄入工具")
    print("=" * 60)

    # 医械标准库目录
    std_dir = project_root / "医械标准库"

    if not std_dir.exists():
        print(f"\n目录不存在: {std_dir}")
        return

    print(f"\n处理目录: {std_dir}")

    # 获取支持的文件
    files = get_supported_files(str(std_dir))
    if not files:
        print(f"  没有找到支持的文件")
        return

    print(f"  发现 {len(files)} 个文件")

    # 按子目录分类统计
    subdir_counts = {}
    for f in files:
        rel_path = os.path.relpath(f, std_dir)
        subdir = rel_path.split(os.sep)[0] if os.sep in rel_path else "."
        subdir_counts[subdir] = subdir_counts.get(subdir, 0) + 1

    print("\n各子目录文件数:")
    for subdir, count in sorted(subdir_counts.items()):
        print(f"  {subdir}: {count}")

    # 确认
    print("\n" + "=" * 60)
    confirm = input("是否继续摄入这些文件到向量库？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        return

    print("\n开始摄入...\n")

    # 执行摄入 - 按 doc_type 为 standard（医疗器械标准）
    result = ingest_files(
        file_paths=files,
        collection_name="all",
        force_doc_type="standard"
    )

    print("\n" + "=" * 60)
    print("摄入完成!")
    print(f"  处理文档: {result['processed_docs']}/{result['total_files']}")
    print(f"  生成Chunks: {result['total_chunks']}")
    print(f"  向量库总量: {result['vector_store_count']}")


if __name__ == "__main__":
    main()
