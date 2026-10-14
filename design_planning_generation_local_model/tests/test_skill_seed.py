"""
test_skill_seed.py - 预置技能卡种子写入测试（方案模块五 §6.2/§6.3）

覆盖:
- 种子卡数据约束: 名称/描述/内容长度满足 create_skill 截断上限（防静默截断）
- 首次运行: 5 张种子卡全部写入
- 幂等: 重复运行跳过同名卡，不产生重复
- 用户治理优先: 已存在同名卡（用户自建/RA 修订版）不被覆盖
- 存储隔离: 写入 tmp 路径，不触碰 app/data/user_skills.json
"""
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import skill_library
import seed_skills


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    p = tmp_path / "user_skills.json"
    p.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(skill_library, "_SKILLS_FILE", str(p))
    return p


def test_seed_cards_fit_create_skill_limits():
    for card in seed_skills.SEED_SKILLS:
        assert card["name"] and len(card["name"]) <= 60
        assert card["content"] and len(card["content"]) <= 5000
        assert len(card["description"]) <= 200


def test_seed_creates_all_cards():
    seed_skills.main()
    names = {s["name"] for s in skill_library.list_skills()}
    assert {c["name"] for c in seed_skills.SEED_SKILLS} <= names
    assert len(names) == len(seed_skills.SEED_SKILLS)


def test_seed_idempotent():
    seed_skills.main()
    before = skill_library.list_skills()
    seed_skills.main()
    after = skill_library.list_skills()
    assert len(before) == len(after) == len(seed_skills.SEED_SKILLS)


def test_user_governance_wins_over_same_name_seed():
    # 用户已建同名卡（内容为 RA 修订版）
    skill_library.create_skill(seed_skills.SEED_SKILLS[0]["name"],
                               "RA 专家修订后的内容", "用户治理版本")
    seed_skills.main()
    skills = skill_library.list_skills()
    same = [s for s in skills
            if s["name"] == seed_skills.SEED_SKILLS[0]["name"]]
    assert len(same) == 1 and same[0]["content"] == "RA 专家修订后的内容"
    # 其余种子卡正常补齐
    assert len(skills) == len(seed_skills.SEED_SKILLS)
