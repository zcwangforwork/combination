"""
Conversation Service - 数字员工会话管理
管理文档生成后的交互式修订对话，支持多轮反馈和版本追踪
会话自动持久化到磁盘，服务器重启后自动恢复。
"""

import uuid
import time
import json
import os
import threading
from typing import Optional, List, Dict
from pathlib import Path


# 会话持久化目录
SESSION_DIR = Path(__file__).parent.parent.parent / "sessions"
SESSION_EXPIRE_SECONDS = 3600  # 会话过期时间：1小时


class ConversationSession:
    """单个会话，追踪一次文档生成及其后续修订"""

    def __init__(
        self,
        session_id: str,
        doc_type: str,
        product_name: str,
        product_type: str,
        product_params: str = "",
        doc_content: str = ""
    ):
        self.session_id = session_id
        self.doc_type = doc_type
        self.product_name = product_name
        self.product_type = product_type
        self.product_params = product_params
        self.current_content = doc_content  # 当前文档内容（Markdown）
        self.history: List[Dict] = []  # 对话历史 [{role, content, timestamp}]
        self.versions: List[Dict] = []  # 版本快照 [{version, content, feedback, timestamp}]
        self.version_count = 0
        self.created_at = time.time()
        self.updated_at = time.time()

    def add_feedback(self, feedback: str) -> str:
        """添加用户反馈，触发版本保存"""
        version_snapshot = {
            "version": self.version_count,
            "content": self.current_content,
            "feedback": feedback,
            "timestamp": time.time()
        }
        self.versions.append(version_snapshot)
        self.version_count += 1

        self.history.append({
            "role": "user",
            "content": feedback,
            "timestamp": time.time()
        })
        self.updated_at = time.time()
        return f"v{self.version_count}"

    def update_content(self, new_content: str):
        """更新文档内容（修订后）"""
        self.current_content = new_content
        self.history.append({
            "role": "assistant",
            "content": f"文档已根据反馈更新（版本 v{self.version_count}）",
            "timestamp": time.time()
        })
        self.updated_at = time.time()

    def is_expired(self) -> bool:
        """检查会话是否过期"""
        return (time.time() - self.updated_at) > SESSION_EXPIRE_SECONDS

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "doc_type": self.doc_type,
            "product_name": self.product_name,
            "product_type": self.product_type,
            "product_params": self.product_params,
            "current_content": self.current_content,
            "history": self.history,
            "versions": self.versions,
            "version_count": self.version_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationSession":
        """从字典恢复会话"""
        session = cls(
            session_id=data["session_id"],
            doc_type=data["doc_type"],
            product_name=data["product_name"],
            product_type=data["product_type"],
            product_params=data.get("product_params", ""),
            doc_content=data.get("current_content", "")
        )
        session.history = data.get("history", [])
        session.versions = data.get("versions", [])
        session.version_count = data.get("version_count", 0)
        session.created_at = data.get("created_at", time.time())
        session.updated_at = data.get("updated_at", time.time())
        return session


class ConversationManager:
    """会话管理器 — 内存 + 文件持久化存储"""

    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.Lock()
        os.makedirs(str(SESSION_DIR), exist_ok=True)
        self._load_all()

    def _session_path(self, session_id: str) -> str:
        return str(SESSION_DIR / f"{session_id}.json")

    def _save_session(self, session: ConversationSession):
        """持久化单个会话到磁盘"""
        try:
            data = session.to_dict()
            data["versions"] = session.versions
            with open(self._session_path(session.session_id), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 持久化失败不影响内存操作

    def _load_all(self):
        """启动时从磁盘恢复所有未过期会话"""
        if not SESSION_DIR.exists():
            return
        for fpath in SESSION_DIR.glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session = ConversationSession.from_dict(data)
                if session.is_expired():
                    os.remove(fpath)  # 清理过期会话文件
                    continue
                self._sessions[session.session_id] = session
            except Exception:
                pass

    def _cleanup_expired(self):
        """清理过期会话"""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            self.remove_session(sid)

    def create_session(
        self,
        doc_type: str,
        product_name: str,
        product_type: str,
        product_params: str = "",
        doc_content: str = ""
    ) -> str:
        """创建新会话，返回 session_id"""
        with self._lock:
            self._cleanup_expired()
            session_id = str(uuid.uuid4())[:8]
            session = ConversationSession(
                session_id=session_id,
                doc_type=doc_type,
                product_name=product_name,
                product_type=product_type,
                product_params=product_params,
                doc_content=doc_content
            )
            self._sessions[session_id] = session
            self._save_session(session)
            return session_id

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """获取会话，自动清理过期"""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self.remove_session(session_id)
            return None
        return session

    def add_feedback(self, session_id: str, feedback: str) -> Optional[str]:
        """记录用户反馈，返回版本标签"""
        session = self.get_session(session_id)
        if not session:
            return None
        result = session.add_feedback(feedback)
        self._save_session(session)
        return result

    def update_content(self, session_id: str, new_content: str):
        """更新会话的文档内容"""
        session = self.get_session(session_id)
        if session:
            session.update_content(new_content)
            self._save_session(session)

    def set_version_diff(self, session_id: str, diff_data: dict):
        """将差异数据写入最新版本快照"""
        session = self.get_session(session_id)
        if session and session.versions:
            session.versions[-1]['diff_data'] = diff_data
            self._save_session(session)

    def remove_session(self, session_id: str):
        """移除会话（内存+磁盘）"""
        self._sessions.pop(session_id, None)
        try:
            fpath = self._session_path(session_id)
            if os.path.exists(fpath):
                os.remove(fpath)
        except Exception:
            pass


# 全局单例
conversation_manager = ConversationManager()
