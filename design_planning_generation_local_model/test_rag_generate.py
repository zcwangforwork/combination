"""Test RAG document generation"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.services.minimax import MiniMaxService

# Test RAG initialization
print("Testing MiniMaxService with RAG...")
service = MiniMaxService(use_rag=True)
print(f"  use_rag: {service.use_rag}")

# Test retrieval
print("\nTesting vector retrieval...")
from app.services.rag.vector_store import VectorStore
vs = VectorStore()
chunks = vs.retrieve(
    query="胰岛素泵 有源医疗器械 Bluetooth 闭环控制",
    doc_type="risk_management_report",
    top_k=2,
    similarity_threshold=0.3
)
print(f"  Retrieved {len(chunks)} chunks")
for i, c in enumerate(chunks, 1):
    print(f"  {i}. [{c['similarity']:.3f}] {c['source_file']}: {c['text'][:60]}...")

# Test RAG prompt building
print("\nTesting RAG prompt building...")
from app.services.rag.rag_prompt import build_rag_prompt_from_base
template = "产品：{product_name}，类型：{product_type}\n\n请生成风险管理文档的内容"
enhanced = build_rag_prompt_from_base(
    base_prompt=template,
    doc_type="risk_management_report",
    product_name="胰岛素泵",
    product_type="有源医疗器械",
    product_params="Bluetooth 闭环控制",
    retrieved_chunks=chunks
)
print(f"  Original prompt length: {len(template)}")
print(f"  Enhanced prompt length: {len(enhanced)}")

print("\nRAG pipeline test complete!")