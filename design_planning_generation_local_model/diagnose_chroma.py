"""
诊断 ChromaDB 知识库问题
"""
import sys
import os
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import chromadb
from chromadb.config import Settings

print("=" * 70)
print("ChromaDB 知识库诊断")
print("=" * 70)

# ChromaDB 持久化目录
base_dir = project_root / "chroma_db"
print(f"\n数据目录: {base_dir}")

# 初始化客户端
client = chromadb.PersistentClient(
    path=str(base_dir),
    settings=Settings(anonymized_telemetry=False)
)

# 列出所有 collections
collections = client.list_collections()
print(f"\n找到 {len(collections)} 个 collection(s):")
print("-" * 70)

all_data = []

for col in collections:
    print(f"\n  Collection: {col.name}")
    print(f"  - ID: {col.id}")
    print(f"  - 元数据: {col.metadata}")

    try:
        count = col.count()
        print(f"  - Chunk 数量: {count}")

        if count > 0:
            # 获取所有数据
            data = col.get(include=["documents", "metadatas", "embeddings"])
            all_data.append({
                'name': col.name,
                'count': count,
                'data': data
            })

            # 显示一些示例
            print(f"\n  - 示例数据 (前3个):")
            for i in range(min(3, count)):
                meta = data['metadatas'][i] if data['metadatas'] else {}
                doc = data['documents'][i] if data['documents'] else ""
                source = meta.get('source_file', 'unknown') if meta else 'unknown'
                print(f"    [{i+1}] {source}")
                preview = doc[:80].replace('\n', ' ') if doc else "(empty)"
                print(f"        {preview}...")

    except Exception as e:
        print(f"  - 错误: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 70)

# 如果发现有数据的 collection，尝试迁移
if all_data:
    print(f"\n发现 {len(all_data)} 个有数据的 collection！")

    # 找出数据最多的那个
    all_data.sort(key=lambda x: x['count'], reverse=True)
    best = all_data[0]
    print(f"\n数据最多的 collection: {best['name']} ({best['count']} chunks)")

    # 检查是否是我们需要的
    target_name = "qms_doc_all"

    if best['name'] != target_name and best['count'] > 0:
        print(f"\n是否要将数据迁移到 '{target_name}'? (y/n)")
        # 自动执行迁移
        print("\n开始自动迁移...")

        # 删除目标 collection（如果存在）
        try:
            client.delete_collection(target_name)
            print(f"  - 已删除旧的 {target_name}")
        except:
            pass

        # 创建新的 collection
        target_col = client.create_collection(
            name=target_name,
            metadata={'description': 'QMS 医疗器械文档参考库'}
        )

        # 复制数据
        src_data = best['data']

        # 批量添加（每次100个）
        batch_size = 100
        total = best['count']

        for i in range(0, total, batch_size):
            end_idx = min(i + batch_size, total)
            print(f"  - 正在添加: {i+1}-{end_idx} / {total}")

            ids_batch = src_data['ids'][i:end_idx]
            docs_batch = src_data['documents'][i:end_idx] if src_data['documents'] else None
            metas_batch = src_data['metadatas'][i:end_idx] if src_data['metadatas'] else None
            embeds_batch = src_data['embeddings'][i:end_idx] if src_data['embeddings'] else None

            target_col.add(
                ids=ids_batch,
                documents=docs_batch,
                metadatas=metas_batch,
                embeddings=embeds_batch
            )

        print(f"\n迁移完成！新 collection 中有 {target_col.count()} 个 chunks")

print("\n" + "=" * 70)
print("诊断完成！")
print("=" * 70)
