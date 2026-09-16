"""
QMS Document Generator - 启动脚本
"""

import uvicorn
import os
import sys

# 加载 .env 文件中的环境变量
from dotenv import load_dotenv
load_dotenv()

# 确保工作目录正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 打印环境变量检查（调试用）
print(f"Python: {sys.version}")
print(f"Ollama Model: {os.getenv('OLLAMA_MODEL', 'qwen3.5:122b')}")
print(f"Ollama URL: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11435')}")

if __name__ == "__main__":
    import socket

    def _try_bind(host: str, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            s.close()
            return True
        except OSError:
            return False

    port = 8002
    if not _try_bind("0.0.0.0", port):
        print(f"Port {port} is occupied, trying 8003...")
        port = 8003
        if not _try_bind("0.0.0.0", port):
            print(f"Port {port} also occupied, trying 8004...")
            port = 8004

    print(f"Starting server on port {port}")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
