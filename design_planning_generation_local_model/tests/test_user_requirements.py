"""历史用户要求累积参考测试：_user_requirements_block / set_current_user_messages

覆盖：
1. 多轮要求累积展示 + 冲突规则文案
2. 退化消息过滤（继续/确认/短消息）
3. 当前指令排除（不重复出现）
4. 无实质消息返回空串
5. 超长截断 + 只取最近 10 条
6. 注入点计数（5 处生成/修改路径）
"""
import inspect


def test_block_accumulates_and_rules():
    from app.services import agent_tools as at
    at.set_current_user_messages([
        "所有表格用三线表",
        "数值右对齐",
        "风险等级用中文",
        "把第三章的表格改成三线表",
    ])
    blk = at._user_requirements_block("把第三章的表格改成三线表")
    assert "历史用户要求" in blk
    assert "不冲突" in blk and "以本次指令为准" in blk
    assert "所有表格用三线表" in blk and "数值右对齐" in blk
    # 当前指令被排除（不重复出现为独立条目）
    assert "[要求" in blk
    assert "把第三章的表格改成三线表" not in blk


def test_block_filters_degenerate():
    from app.services import agent_tools as at
    at.set_current_user_messages(["继续", "好的", "确认", "正文用仿宋"])
    blk = at._user_requirements_block()
    assert "正文用仿宋" in blk
    assert "[要求1] 继续" not in blk
    assert "好的" not in blk and "确认" not in blk


def test_block_empty_when_no_substantive():
    from app.services import agent_tools as at
    at.set_current_user_messages(["继续", "好"])
    assert at._user_requirements_block() == ""
    at.set_current_user_messages([])
    assert at._user_requirements_block() == ""


def test_block_truncates_and_caps():
    from app.services import agent_tools as at
    long_msg = "要求" * 500  # 1000 字
    msgs = [f"第{i}轮要求内容" for i in range(15)] + [long_msg]
    at.set_current_user_messages(msgs)
    blk = at._user_requirements_block()
    # 只取最近 10 条
    assert "第0轮要求内容" not in blk
    assert "第6轮要求内容" in blk
    # 长消息截断
    assert len(blk) < 4000


def test_injection_points():
    from app.services import agent_tools as at
    src = inspect.getsource(at)
    n = src.count("{_user_requirements_block(")
    assert n == 5, f"注入点 {n} 处，应为 5（generate/revise_section/revise_paragraph/write_chapter×2）"
