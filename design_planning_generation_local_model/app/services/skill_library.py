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
