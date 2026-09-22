"""用户技能库 — 将常用指导命令/生成规则沉淀为可复用的技能。

JSON 文件持久化（app/data/user_skills.json），跨项目/跨会话共享（用户级库）。
技能结构: {"id", "name", "content", "description", "created_at", "updated_at"}
"""
import json
import os
import time
import uuid
from typing import Optional

_SKILLS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "user_skills.json")


def _load() -> list:
    try:
        with open(_SKILLS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(skills: list) -> None:
    os.makedirs(os.path.dirname(_SKILLS_FILE), exist_ok=True)
    with open(_SKILLS_FILE, "w", encoding="utf-8") as f:
        json.dump(skills, f, ensure_ascii=False, indent=2)


def list_skills() -> list:
    """全部技能（按创建时间倒序，新的在前）。"""
    return sorted(_load(), key=lambda s: s.get("created_at", 0), reverse=True)


def create_skill(name: str, content: str, description: str = "") -> dict:
    """新增技能。name/content 必填；返回新建的技能 dict。"""
    name = (name or "").strip()
    content = (content or "").strip()
    if not name or not content:
        raise ValueError("技能名称与内容不能为空")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    skill = {
        "id": uuid.uuid4().hex[:12],
        "name": name[:60],
        "content": content[:5000],
        "description": (description or "").strip()[:200],
        "created_at": now,
        "updated_at": now,
    }
    skills = _load()
    skills.append(skill)
    _save(skills)
    return skill


def update_skill(skill_id: str, name: str = None, content: str = None,
                 description: str = None) -> Optional[dict]:
    """更新技能（只改传入的非空字段）。未找到返回 None。"""
    skills = _load()
    for s in skills:
        if s.get("id") == skill_id:
            if name is not None and name.strip():
                s["name"] = name.strip()[:60]
            if content is not None and content.strip():
                s["content"] = content.strip()[:5000]
            if description is not None:
                s["description"] = description.strip()[:200]
            s["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _save(skills)
            return s
    return None


def delete_skill(skill_id: str) -> bool:
    """删除技能。返回是否确实删除。"""
    skills = _load()
    remain = [s for s in skills if s.get("id") != skill_id]
    if len(remain) == len(skills):
        return False
    _save(remain)
    return True


# ── RAG 检索：技能向量化，文档写作时按相关度自动召回并注入提示词 ──
# 内存索引（技能文件 mtime/数量变化时惰性重建）；服务重启后首次检索时自动重建。
# 技能量级小（几十条），无需 ChromaDB 持久化；embedding 复用 Ollama 嵌入服务。
import threading

_INDEX_LOCK = threading.Lock()
_SKILL_INDEX = {"mtime": 0.0, "count": -1, "embeddings": [], "skills": []}
_EMBEDDER = None
# 冷却机制：索引构建/检索失败（如 Ollama 未启动）后暂停重试，
# 避免每次章节生成都阻塞在嵌入 API 的 3 次重试超时上
_FAIL_COOLDOWN_UNTIL = 0.0
_SEARCH_COOLDOWN_SECONDS = 60


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from app.services.rag.embedder import Embedder
        _EMBEDDER = Embedder()
    return _EMBEDDER


def _skill_text(s: dict) -> str:
    """技能的向量化/检索文本：名称+正文（description 为管理元数据，不参与语义匹配）。"""
    return f"{s.get('name', '')}：{s.get('content', '')}"


def _ensure_index() -> bool:
    """惰性构建/重建技能内存向量索引。

    Returns:
        索引是否可用（False = 无技能、构建失败或冷却期内）。
    """
    global _FAIL_COOLDOWN_UNTIL
    import time as _t
    if _t.time() < _FAIL_COOLDOWN_UNTIL:
        return False
    try:
        mtime = os.path.getmtime(_SKILLS_FILE)
    except OSError:
        with _INDEX_LOCK:
            _SKILL_INDEX.update(mtime=0.0, count=0, embeddings=[], skills=[])
        return False
    skills = _load()
    if not skills:
        with _INDEX_LOCK:
            _SKILL_INDEX.update(mtime=mtime, count=0, embeddings=[], skills=[])
        return False
    # 快路径：文件未变化且索引已建 → 直接可用
    if (_SKILL_INDEX["mtime"] == mtime and _SKILL_INDEX["count"] == len(skills)
            and _SKILL_INDEX["embeddings"]):
        return True
    with _INDEX_LOCK:
        # 双检：等锁期间其他线程可能已完成重建（并行的章节生成任务共享索引）
        if (_SKILL_INDEX["mtime"] == mtime and _SKILL_INDEX["count"] == len(skills)
                and _SKILL_INDEX["embeddings"]):
            return True
        try:
            embs = _get_embedder().encode([_skill_text(s) for s in skills])
        except Exception as e:
            _FAIL_COOLDOWN_UNTIL = _t.time() + _SEARCH_COOLDOWN_SECONDS
            print(f"[skill_library] 技能索引构建失败（冷却{_SEARCH_COOLDOWN_SECONDS}s）: {e}")
            return False
        _SKILL_INDEX.update(mtime=mtime, count=len(skills), embeddings=embs, skills=skills)
        print(f"[skill_library] 技能向量索引已重建: {len(skills)} 条技能")
        return True


def search_skills(query: str, top_k: int = 3, min_score: float = 0.35) -> list:
    """检索与写作上下文相关的技能：向量粗召回 → Cross-Encoder 精排（失败时静默降级）。

    Args:
        query: 检索文本（文档类型 + 章节名 + 修改指令等写作上下文）
        top_k: 最多返回的技能数
        min_score: 精排最低相关度阈值（0-1），过滤不相关技能避免噪声进入提示词

    Returns:
        [{"id", "name", "content", "score"}]，按相关度降序；无技能或无达标技能返回 []。
    """
    global _FAIL_COOLDOWN_UNTIL
    query = (query or "").strip()
    if not query:
        return []
    import time as _t
    if _t.time() < _FAIL_COOLDOWN_UNTIL:
        return []
    if not _ensure_index():
        return []
    try:
        import numpy as np
        q_emb = np.asarray(_get_embedder().encode_single(query), dtype=np.float32)
        mat = np.asarray(_SKILL_INDEX["embeddings"], dtype=np.float32)
        # 余弦相似度（Ollama 嵌入未保证归一化，显式除模长）
        qn = float(np.linalg.norm(q_emb)) or 1.0
        mn = np.linalg.norm(mat, axis=1)
        mn[mn == 0] = 1.0
        sims = (mat @ q_emb) / (mn * qn)
        recall_n = min(len(sims), max(top_k * 3, 6))
        cand_idx = np.argsort(-sims)[:recall_n]
        chunks = []
        for i in cand_idx:
            s = _SKILL_INDEX["skills"][int(i)]
            chunks.append({
                "text": _skill_text(s),
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "content": s.get("content", ""),
                "score": round(float(sims[int(i)]), 3),
            })
    except Exception as e:
        _FAIL_COOLDOWN_UNTIL = _t.time() + _SEARCH_COOLDOWN_SECONDS
        print(f"[skill_library] 技能检索失败（冷却{_SEARCH_COOLDOWN_SECONDS}s）: {e}")
        return []
    # Cross-Encoder 精排（bge-reranker，与 KB 问答同款；失败时降级纯向量+更高阈值）
    try:
        from app.services.rag.reranker import Reranker
        ranked = Reranker().rerank_with_threshold(query, chunks, top_k, min_score)
        return [
            {"id": c["id"], "name": c["name"], "content": c["content"],
             "score": round(float(c.get("rerank_score", c["score"])), 3)}
            for c in ranked
        ]
    except Exception as e:
        print(f"[skill_library] 技能精排失败（用向量粗排）: {e}")
        return [
            {"id": c["id"], "name": c["name"], "content": c["content"], "score": c["score"]}
            for c in chunks if c["score"] >= 0.5
        ][:top_k]
