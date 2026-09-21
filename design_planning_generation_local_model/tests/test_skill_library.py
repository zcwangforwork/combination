"""用户技能库测试：CRUD 全链路（JSON 文件持久化）"""
from app.services import skill_library as sl


def test_skill_crud_roundtrip():
    # 创建
    s = sl.create_skill("三线表规则", "所有表格使用三线表样式", "表格规范")
    assert s["id"] and s["name"] == "三线表规则"
    assert s["content"] == "所有表格使用三线表样式"

    # 列表（新建的在前）
    lst = sl.list_skills()
    assert any(x["id"] == s["id"] for x in lst)

    # 更新（只改传入字段）
    u = sl.update_skill(s["id"], content="所有表格使用三线表；表头加粗")
    assert "表头加粗" in u["content"]
    assert u["name"] == "三线表规则"  # 未传 name 不变

    # 删除（幂等）
    assert sl.delete_skill(s["id"]) is True
    assert sl.delete_skill(s["id"]) is False
    assert not any(x["id"] == s["id"] for x in sl.list_skills())


def test_create_skill_validation():
    import pytest
    with pytest.raises(ValueError):
        sl.create_skill("", "内容")
    with pytest.raises(ValueError):
        sl.create_skill("名称", "   ")


def test_update_nonexistent_returns_none():
    assert sl.update_skill("no-such-id", name="x") is None
