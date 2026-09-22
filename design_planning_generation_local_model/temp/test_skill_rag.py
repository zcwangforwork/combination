# -*- coding: utf-8 -*-
"""技能库 RAG 检索 + 提示词注入 功能测试（monkeypatch 技能文件到 temp，不碰真实数据）"""
import sys, io, os, json, asyncio, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from app.services import skill_library

# ── monkeypatch 技能文件到 temp ──
TMP_SKILLS = os.path.join("temp", "_test_user_skills.json")
skill_library._SKILLS_FILE = TMP_SKILLS

SKILLS = [
    {"name": "风险表格三线表规则", "content": "风险管理文档中的所有表格必须使用三线表格式，表头加粗；风险等级一律用中文表述（严重/一般/轻微），禁止使用英文S/M/L。", "description": ""},
    {"name": "术语统一规则", "content": "全文统一使用“贴敷式胰岛素泵”这一术语，首次出现时括注英文名，后文不再重复英文全称；禁止混用“泵体/输注泵”等非规范称呼。", "description": ""},
    {"name": "软件版本号格式", "content": "软件发布版本号采用V x.y.z三段式格式；版本说明章节必须包含版本历史表格，列出每个版本的发布日期、变更内容与验证结论。", "description": ""},
    {"name": "灭菌验证引用要求", "content": "设计验证中的灭菌验证章节必须引用ISO 11135标准，明确EO灭菌工艺的解析时间与残留量限值，并给出灭菌确认报告编号占位。", "description": ""},
]

def _write_skills(skills):
    data = []
    for i, s in enumerate(skills):
        data.append({"id": f"sk{i:03d}", "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **s})
    with open(TMP_SKILLS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

_write_skills(SKILLS)

print("== search_skills 相关检索 ==")
ok = True

def check(name, cond, detail=""):
    global ok
    print(("OK  " if cond else "FAIL") + f" {name} {detail}")
    if not cond: ok = False

t0 = time.time()
r = skill_library.search_skills("风险管理计划 风险可接受准则 风险表格", top_k=2)
print(f"  (首次含建索引+精排模型加载: {time.time()-t0:.1f}s)")
check("风险查询命中三线表技能", any("三线表" in x["name"] or "三线表" in x["content"] for x in r),
      f"-> {[(x['name'], x['score']) for x in r]}")

r = skill_library.search_skills("软件需求规格说明书 版本说明 版本历史", top_k=2)
check("软件版本查询命中版本号技能", any("版本号" in x["name"] for x in r),
      f"-> {[(x['name'], x['score']) for x in r]}")

r = skill_library.search_skills("设计验证 灭菌验证 EO灭菌工艺", top_k=2)
check("灭菌查询命中灭菌技能", any("灭菌" in x["name"] for x in r),
      f"-> {[(x['name'], x['score']) for x in r]}")

r = skill_library.search_skills("员工食堂菜单安排 财务报销流程", top_k=2)
check("无关查询被阈值过滤", len(r) == 0, f"-> {[(x['name'], x['score']) for x in r]}")

# 索引重建：修改技能文件后应重新嵌入
time.sleep(0.05)
_write_skills(SKILLS[:2])
r = skill_library.search_skills("灭菌验证", top_k=2)
check("删除技能后索引重建（灭菌技能不再命中）", all("灭菌" not in x["name"] for x in r),
      f"-> {[x['name'] for x in r]}")

# ── _retrieve_skill_rules_block（含补充提示词去重）──
print("\n== _retrieve_skill_rules_block ==")
from app.services import agent_tools

_write_skills(SKILLS)
skill_library._SKILL_INDEX.update(mtime=0.0, count=-1, embeddings=[], skills=[])  # 强制重建

async def _t():
    blk = await agent_tools._retrieve_skill_rules_block("风险管理计划 风险表格格式")
    check("注入块非空且含技能标题", "用户技能库规则" in blk and "技能「" in blk, f"len={len(blk)}")
    # 去重：把该技能内容并入补充提示词后应不再注入
    first_content = None
    import re
    m = re.search(r"技能「(.+?)」", blk)
    check("解析出技能名", m is not None, f"name={m.group(1) if m else None}")
    return blk

blk = asyncio.run(_t())

# 去重测试：将命中技能原文放入 supplementary contextvar
skills_hit = skill_library.search_skills("风险管理计划 风险表格格式", top_k=2)
if skills_hit:
    agent_tools._current_supplementary_prompts.set(skills_hit[0]["content"])
    async def _t2():
        blk2 = await agent_tools._retrieve_skill_rules_block("风险管理计划 风险表格格式")
        return blk2
    blk2 = asyncio.run(_t2())
    check("已并入补充提示词的技能被去重", skills_hit[0]["content"][:40] not in blk2,
          f"剩余块长度={len(blk2)}")
    agent_tools._current_supplementary_prompts.set("")

# 清理
os.remove(TMP_SKILLS)
print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
