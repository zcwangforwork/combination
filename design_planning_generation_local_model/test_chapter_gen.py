"""测试分章节生成"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

print(f"API Key loaded: {bool(os.getenv('MINIMAX_API_KEY'))}", flush=True)

from app.services.minimax import MiniMaxService, DOC_CHAPTERS

svc = MiniMaxService()
print(f"MiniMaxService initialized, use_rag: {svc.use_rag}", flush=True)

# 查看章节定义
chapters = DOC_CHAPTERS.get("risk_management_report", [])
print(f"Chapters for risk_management_report: {len(chapters)}", flush=True)
for ch in chapters:
    print(f"  - {ch}", flush=True)

# 尝试只生成第一章
print("\n=== Testing first chapter only ===", flush=True)
try:
    # 构建第一章的prompt
    template = svc._get_prompt_template("risk_management_report")
    chapter_name = chapters[0]["name"]
    prompt = template.format(
        product_name="测试血糖仪",
        product_type="有源医疗器械",
        product_params="测量范围：1.1-33.3mmol/L",
        chapter=chapter_name
    )
    print(f"Prompt for chapter 1:\n{prompt[:200]}...", flush=True)

    # 调用API
    print("Calling API...", flush=True)
    result = svc._call_api(prompt)
    print(f"API returned {len(result)} chars", flush=True)
    print(f"First 500 chars:\n{result[:500]}", flush=True)
except Exception as e:
    print(f"Error: {e}", flush=True)
    import traceback
    traceback.print_exc()