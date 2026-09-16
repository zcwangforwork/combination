"""
重新构建完整知识库 - 摄入所有参考文档
"""
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.rag.ingest import (
    ingest_all,
    get_supported_files,
    VectorStore
)


def main():
    print("=" * 70)
    print("重新构建医疗器械文档知识库")
    print("=" * 70)

    # 第一步：检查现有数据
    print("\n[1/4] 检查现有知识库...")
    vs = VectorStore(collection_name="all")
    existing_count = vs.count()
    existing_sources = vs.get_sources()
    print(f"  现有chunk数量: {existing_count}")
    print(f"  现有来源文件: {len(existing_sources)}个")

    # 第二步：发现所有支持的文档
    print("\n[2/4] 扫描所有参考文档...")
    source_dir = project_root / "develop_documents"

    if not source_dir.exists():
        print(f"  错误: 找不到目录 {source_dir}")
        return

    supported_files = get_supported_files(str(source_dir))

    print(f"\n发现 {len(supported_files)} 个支持的文档:")
    print("-" * 70)

    # 统计按目录分组
    from collections import defaultdict
    files_by_dir = defaultdict(list)
    for f in supported_files:
        p = Path(f)
        relative_p = p.relative_to(source_dir)
        parent_dir = relative_p.parts[0] if len(relative_p.parts) > 1 else "根目录"
        files_by_dir[parent_dir].append(p.name)

    for dir_name, files in sorted(files_by_dir.items()):
        print(f"\n[{dir_name}] ({len(files)}个):")
        for f in files[:5]:
            print(f"   - {f}")
        if len(files) > 5:
            print(f"   ... 还有 {len(files)-5} 个文件")

    print("\n" + "-" * 70)

    # 第三步：确认重建（跳过确认，直接开始）
    print("\n[3/4] 开始重新构建知识库...")
    print("  这可能需要几分钟时间，请耐心等待...\n")

    try:
        result = ingest_all(
            source_dir=str(source_dir),
            collection_name="all",
            rebuild=True
        )

        print("\n" + "=" * 70)
        print("知识库重建成功！")
        print("=" * 70)
        print(f"  总文件数: {result['total_files']}")
        print(f"  处理文档: {result['processed_docs']}")
        print(f"  生成Chunk: {result['total_chunks']}")
        print(f"  向量库总量: {result['vector_store_count']}")

        # 显示来源文件
        final_vs = VectorStore(collection_name="all")
        final_sources = final_vs.get_sources()
        print(f"\n  知识库包含来源: {len(final_sources)} 个文件")

    except Exception as e:
        print(f"\n重建过程中出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
