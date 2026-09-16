"""
测试脚本 - 验证项目结构和依赖
"""

import os
import sys

# 切换到项目目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试依赖导入"""
    print("Testing imports...")
    try:
        import fastapi
        print("  - fastapi: OK")
    except ImportError as e:
        print(f"  - fastapi: FAILED - {e}")

    try:
        import uvicorn
        print("  - uvicorn: OK")
    except ImportError as e:
        print(f"  - uvicorn: FAILED - {e}")

    try:
        import docx
        print("  - python-docx: OK")
    except ImportError as e:
        print(f"  - python-docx: FAILED - {e}")

    try:
        import requests
        print("  - requests: OK")
    except ImportError as e:
        print(f"  - requests: FAILED - {e}")

    try:
        import pydantic
        print("  - pydantic: OK")
    except ImportError as e:
        print(f"  - pydantic: FAILED - {e}")

def test_project_structure():
    """测试项目结构"""
    print("\nTesting project structure...")

    required_files = [
        "app/main.py",
        "app/api/routes.py",
        "app/services/generator.py",
        "app/services/minimax.py",
        "app/services/template.py",
        "app/static/index.html",
        "run.py",
        "requirements.txt"
    ]

    for f in required_files:
        if os.path.exists(f):
            print(f"  - {f}: OK")
        else:
            print(f"  - {f}: MISSING")

def test_api():
    """测试API启动"""
    print("\nTesting API...")

    # 检查环境变量
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if api_key:
        print(f"  - MINIMAX_API_KEY: Set ({api_key[:4]}...)")
    else:
        print("  - MINIMAX_API_KEY: Not set (will use fallback)")

if __name__ == "__main__":
    test_imports()
    test_project_structure()
    test_api()
    print("\nTest completed.")
