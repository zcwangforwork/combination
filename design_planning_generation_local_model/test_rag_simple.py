"""
简单测试 RAG 检索功能
"""
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from app.services.rag.vector_store import VectorStore

print("=" * 70)
print("测试 RAG 知识库检索")
print("=" * 70)

# 检查知识库
vs = VectorStore(collection_name="all")
count = vs.count()
sources = vs.get_sources()

print(f"\n知识库状态:")
print(f"  - 总 chunks: {count}")
print(f"  - 来源文件: {len(sources)} 个")

if count == 0:
    print("\n知识库为空，需要先建立知识库！")
    sys.exit(1)

print("\n前 10 个来源文件:")
for s in sources[:10]:
    print(f"  - {s}")

# 测试检索
print("\n" + "=" * 70)
print("测试检索...")
print("=" * 70)

test_queries = [
    "风险管理报告",
    "设计输入",
    "产品技术要求",
    "SOP 作业指导书",
]

for query in test_queries:
    print(f"\n查询: '{query}'")
    results = vs.retrieve_hybrid(query=query, top_k=3)
    print(f"  找到 {len(results)} 个相关片段")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] 相似度: {r['similarity']:.3f} | {r['source_file']}")
        preview = r['text'][:100].replace('\n', ' ')
        print(f"      预览: {preview}...")

print("\n" + "=" * 70)
print("RAG 知识库工作正常！")
print("=" * 70)
