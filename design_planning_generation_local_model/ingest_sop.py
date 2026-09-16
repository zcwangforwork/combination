"""
便捷脚本：摄入作业指导书到知识库
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
    print("作业指导书知识库摄入工具")
    print("=" * 60)

    # 作业指导书目录
    sop_dirs = [
        project_root / "develop_documents" / "作业指导书",
        project_root / "downloads" / "web" / "sop",
        project_root / "develop_documents_02",
    ]

    for sop_dir in sop_dirs:
        if not sop_dir.exists():
            print(f"\n目录不存在: {sop_dir}")
            continue

        print(f"\n处理目录: {sop_dir}")

        # 获取支持的文件
        files = get_supported_files(str(sop_dir))
        if not files:
            print(f"  没有找到支持的文件")
            continue

        print(f"  发现 {len(files)} 个文件:")
        for f in files[:10]:
            print(f"    - {os.path.basename(f)}")
        if len(files) > 10:
            print(f"    ... 还有 {len(files) - 10} 个")

        # 确认
        confirm = input("\n是否继续摄入这些文件？(y/n): ").strip().lower()
        if confirm != 'y':
            continue

        # 执行摄入
        result = ingest_files(
            file_paths=files,
            collection_name="all",
            force_doc_type="sop"
        )

        print(f"\n摄入结果:")
        print(f"  处理文档: {result['processed_docs']}/{result['total_files']}")
        print(f"  生成Chunks: {result['total_chunks']}")
        print(f"  向量库总量: {result['vector_store_count']}")

    print("\n" + "=" * 60)
    print("完成！")


if __name__ == "__main__":
    main()
