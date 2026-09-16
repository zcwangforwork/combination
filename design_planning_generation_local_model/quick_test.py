"""
快速测试核心功能
"""
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

print("=" * 70)
print("快速测试")
print("=" * 70)

# 1. 测试 MiniMaxService
print("\n[1] 测试 MiniMaxService...")
try:
    from app.services.minimax import MiniMaxService
    service = MiniMaxService(use_rag=False)  # 不使用 RAG
    print("    [OK] MiniMaxService 初始化成功")
    print(f"    use_rag: {service.use_rag}")
except Exception as e:
    print(f"    [失败] {e}")
    sys.exit(1)

# 2. 测试 API 调用
print("\n[2] 测试简单 API 调用...")
try:
    result = service._call_api("请用一句话介绍你自己。")
    print("    [OK] API 调用成功")
    print(f"    结果长度: {len(result)} 字符")
    print(f"    前100字符: {result[:100]}...")
except Exception as e:
    print(f"    [失败] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. 测试生成
print("\n[3] 测试文档生成...")
try:
    content = service.generate_content(
        doc_type="risk_management_report",
        product_name="测试血糖仪",
        product_type="有源医疗器械",
        product_params="血糖检测，Bluetooth 数据传输",
        chapter_mode=True
    )
    print("    [OK] 文档生成成功")
    print(f"    内容长度: {len(content)} 字符")
    print(f"    前200字符:\n{content[:200]}...")
except Exception as e:
    print(f"    [失败] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ 所有核心功能测试通过！")
print("=" * 70)
print("\n现在可以启动服务了:")
print("  python run.py")
print("\n然后访问: http://localhost:8001")
