"""
QMS Document Generator - FastAPI Application
医疗器械质量体系文档生成工具
"""

# 必须在任何 import torch / pyarrow / sentence_transformers 之前设置，
# 避免 torch 与 pyarrow 的 Intel OpenMP DLL 冲突（Windows access violation）
import os as _os
_os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# psycopg（langgraph-checkpoint-postgres 的底层驱动）在 Windows 下要求 SelectorEventLoop，
# 默认的 ProactorEventLoop 无法跑 async 连接。必须在事件循环创建前（模块导入期）设置。
import sys as _sys
import asyncio as _asyncio
if _sys.platform == "win32":
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import router

# [COMBINATION-PORT] 跨源 CORS: 允许体系文档管理系统前端(:3000)访问本服务。
# 显式 origin 列表（不用 "*" + credentials 组合）；方法/请求头放开发内网所需范围
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时初始化Agent"""
    # 启动时初始化Agent
    try:
        from app.services.agent_engine import init_agent
        await init_agent()
        print("[main] Agent initialized successfully")
    except Exception as e:
        print(f"[main] Agent initialization failed (non-fatal): {e}")
        print("[main] Agent endpoints will return errors until fixed")

    yield

    # 关闭时清理
    try:
        from app.services.agent_state import close_checkpointer
        await close_checkpointer()
        print("[main] Checkpointer closed")
    except Exception:
        pass

    # 关闭 OpenViking 服务
    try:
        from app.services.openviking_client import close_openviking
        await close_openviking()
        print("[main] OpenViking service closed")
    except Exception:
        pass

    # 关闭 PostgreSQL 长期记忆存储
    try:
        from app.services.agent_memory import close_memory_store
        await close_memory_store()
        print("[main] Long-term memory store closed")
    except Exception:
        pass

    # 关闭 PostgreSQL 连接池
    try:
        from app.services.pgsql_client import close_pool
        await close_pool()
        print("[main] PostgreSQL pool closed")
    except Exception:
        pass


app = FastAPI(
    title="QMS Document Generator",
    description="医疗器械质量体系文档生成工具 - 基于AI自动生成符合法规的质量体系文档",
    version="2.0.0",
    lifespan=lifespan,
)

# [COMBINATION-PORT] CORS: 体系文档管理系统 SPA (http-server :3000) 跨源访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# [COMBINATION-PORT] 静态资源挂载：token-relay.js（review/kb 新标签页的 JWT 凭证
# 中转脚本，用户隔离配套——凭证经 URL #jwt= 片段传入，页内转存 sessionStorage）
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root():
    """根路径重定向到 Agent 对话页面（旧版表单模式已隐藏，页面文件与 API 保留）"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/agent", status_code=302)


@app.get("/agent")
async def agent_page():
    """返回Agent对话页面 (新版聊天模式)"""
    return FileResponse("app/static/agent.html")


@app.get("/agent/review/{project_id}")
async def agent_review_page(project_id: str):
    """返回Agent文档审阅页面"""
    return FileResponse("app/static/review.html")


@app.get("/kb")
async def kb_page():
    """返回知识库独立页面（文件管理 + 知识库检索问答）"""
    return FileResponse("app/static/kb.html")


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "agent": "enabled"}


if __name__ == "__main__":
    import uvicorn
    import socket

    def _try_bind(host: str, port: int) -> bool:
        """检查端口是否可用"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            s.close()
            return True
        except OSError:
            return False

    port = 8002
    if not _try_bind("0.0.0.0", port):
        print(f"[main] Port {port} is occupied, trying 8003...")
        port = 8003
        if not _try_bind("0.0.0.0", port):
            print(f"[main] Port {port} also occupied, trying 8004...")
            port = 8004

    print(f"[main] Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
