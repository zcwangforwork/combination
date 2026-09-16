"""
RAG Service - 检索增强生成模块

将 develop_documents 中的参考文档向量化存储，
生成时通过语义检索注入相关段落作为上下文。
"""

from app.services.rag.vector_store import VectorStore
from app.services.rag.embedder import Embedder
from app.services.rag.reranker import Reranker
from app.services.rag.rag_prompt import build_rag_prompt

__all__ = ["VectorStore", "Embedder", "Reranker", "build_rag_prompt"]
