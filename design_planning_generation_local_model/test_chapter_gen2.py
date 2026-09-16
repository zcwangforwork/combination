"""测试分章节生成 - 直接保存结果"""
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from app.services.minimax import MiniMaxService, DOC_CHAPTERS

svc = MiniMaxService()

# 尝试只生成第一章
print("=== Testing first chapter only ===")
try:
    template = svc._get_prompt_template("risk_management_report")
    chapters = DOC_CHAPTERS["risk_management_report"]
    chapter_name = chapters[0]["name"]
    prompt = template.format(
        product_name="测试血糖仪",
        product_type="有源医疗器械",
        product_params="测量范围：1.1-33.3mmol/L",
        chapter=chapter_name
    )

    print(f"Calling API for chapter: {chapter_name}...")
    result = svc._call_api(prompt)
    print(f"API returned {len(result)} chars")

    # 保存到文件
    with open("chapter1_result.txt", "w", encoding="utf-8") as f:
        f.write(result)
    print("Saved to chapter1_result.txt")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()