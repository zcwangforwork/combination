"""
文档审核 Agent - 启动脚本（combination 移植新增）

与原 backend/main.py 底部的 uvicorn.run 入口等价，差异:
  - 端口 8000 固定 → 8012→8013→8014 依次回退（避开文档写作 Agent 的 8002-8004，
    前端 js/agent-review.js 按同一次序探测）
  - 从项目根目录启动时自动 chdir 到 backend/（main.py 为平铺模块导入，
    且 checkpoints/ 向量库等均按 CWD=backend 解析）
"""
import os
import socket
import sys

# main.py 顶部自行 load_dotenv()（读取 backend/.env），此处无需重复

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

if __name__ == "__main__":
    import uvicorn
    import main  # noqa: E402  (backend/main.py，平铺导入需 CWD+sys.path 就绪)

    def _try_bind(host: str, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            s.close()
            return True
        except OSError:
            return False

    port = 8012
    if not _try_bind("0.0.0.0", port):
        print(f"Port {port} is occupied, trying 8013...")
        port = 8013
        if not _try_bind("0.0.0.0", port):
            print(f"Port {port} also occupied, trying 8014...")
            port = 8014

    print(f"Starting document-review server on port {port}")
    uvicorn.run(
        main.app,
        host="0.0.0.0",
        port=port,
        workers=1,               # 强制单worker，避免多进程各加载一份HNSW索引
        limit_concurrency=20,    # 限制并发连接数（浏览器需多连接加载页面资源）
        timeout_keep_alive=10,   # 缩短keep-alive，减少空闲连接内存占用
    )
