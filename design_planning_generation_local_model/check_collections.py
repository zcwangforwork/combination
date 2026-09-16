"""
检查 ChromaDB 中的所有 collections
"""
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import chromadb
from chromadb.config import Settings

print("=" * 70)
print("检查 ChromaDB 知识库")
print("=" * 70)

# ChromaDB 持久化目录
base_dir = project_root / "chroma_db"
print(f"\n数据目录: {base_dir}")

if not base_dir.exists():
    print("目录不存在！")
    sys.exit(1)

# 初始化客户端
client = chromadb.PersistentClient(
    path=str(base_dir),
    settings=Settings(anonymized_telemetry=False)
)

# 列出所有 collections
collections = client.list_collections()
print(f"\n找到 {len(collections)} 个 collection:")
print("-" * 70)

for col in collections:
    print(f"\n  Collection: {col.name}")
    print(f"  - ID: {col.id}")
    print(f"  - 元数据: {col.metadata}")
    try:
        count = col.count()
        print(f"  - Chunk 数量: {count}")

        # 获取一些元数据看看
        data = col.get(limit=5, include=["metadatas"])
        if data and data['metadatas']:
            print(f"  - 示例来源:")
            sources = set()
            for m in data['metadatas']:
                if m and 'source_file' in m:
                    sources.add(m['source_file'])
            for s in list(sources)[:5]:
                print(f"    * {s}")
    except Exception as e:
        print(f"  - 错误: {e}")

print("\n" + "=" * 70)
