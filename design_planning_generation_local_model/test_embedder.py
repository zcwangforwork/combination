"""
测试 embedder 和 API 连接
"""
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 先加载 .env
from dotenv import load_dotenv
load_dotenv()

import os
print("=" * 70)
print("测试 Embedder 和 API 连接")
print("=" * 70)

# 检查环境变量
api_key = os.getenv("MINIMAX_API_KEY", "")
print(f"\nAPI Key (from env): {'已设置' if api_key else '未设置'}")
if api_key:
    print(f"API Key 前缀: {api_key[:30]}...")

# 测试 embedder
print("\n" + "=" * 70)
print("初始化 Embedder...")
print("=" * 70)

from app.services.rag.embedder import Embedder

try:
    embedder = Embedder()
    print("[OK] Embedder 初始化成功")

    # 测试单条文本
    print("\n测试单条文本向量化...")
    test_text = "这是一个测试文本，用于验证向量化 API 是否正常工作。"
    embedding = embedder.encode_single(test_text)
    print(f"[OK] 向量化成功！向量维度: {len(embedding)}")
    print(f"    前5个值: {embedding[:5]}")

    # 测试批量
    print("\n测试批量向量化...")
    texts = [
        "风险管理报告",
        "设计输入要求",
        "产品技术要求",
        "SOP 作业指导书",
    ]
    embeddings = embedder.encode(texts)
    print(f"[OK] 批量向量化成功！共 {len(embeddings)} 个向量")

    print("\n" + "=" * 70)
    print("✓ 所有测试通过！")
    print("=" * 70)

except Exception as e:
    print(f"\n[错误] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
