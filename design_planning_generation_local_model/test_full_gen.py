"""测试完整分章节生成"""
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from app.services.minimax import MiniMaxService

svc = MiniMaxService()

print("=== Testing full document generation (6 chapters) ===", flush=True)

try:
    result = svc._generate_by_chapters(
        doc_type='risk_management_report',
        product_name='测试血糖仪',
        product_type='有源医疗器械',
        product_params='测量范围：1.1-33.3mmol/L'
    )

    print(f"Document generated: {len(result)} chars total", flush=True)

    # 保存到文件
    with open("full_document.txt", "w", encoding="utf-8") as f:
        f.write(result)
    print("Saved to full_document.txt", flush=True)

    # 简单验证结构
    lines = result.split("\n")
    chapter_count = sum(1 for l in lines if l.startswith("## 第"))
    print(f"Found {chapter_count} chapters in document", flush=True)

except Exception as e:
    print(f"Error: {e}", flush=True)
    import traceback
    traceback.print_exc()