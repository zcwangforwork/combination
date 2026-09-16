"""
启动 QMS 文档生成服务
"""
import sys
import os
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

print("=" * 70)
print("QMS 医疗器械文档生成服务")
print("=" * 70)

# 检查环境变量
api_key = os.getenv("MINIMAX_API_KEY", "")
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:122b")
print(f"\nAPI Key 状态: {'已配置' if api_key else '未配置'}")
print(f"Ollama URL: {ollama_url}")
print(f"Ollama Model: {ollama_model}")

# 检查 ChromaDB
from app.services.rag.vector_store import VectorStore
try:
    vs = VectorStore(collection_name="all")
    count = vs.count()
    print(f"RAG 知识库: {count} chunks")
except Exception as e:
    print(f"RAG 知识库: 检查失败 - {e}")

print("\n" + "=" * 70)
print("启动服务...")
print("=" * 70)
print("\n服务地址: http://localhost:8001")
print("按 Ctrl+C 停止服务\n")

# 启动服务
import uvicorn
uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=8001,
    reload=True
)
