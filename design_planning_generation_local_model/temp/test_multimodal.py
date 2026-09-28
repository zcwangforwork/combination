# -*- coding: utf-8 -*-
"""多模态图片注入单元测试：消息构建 / 图像预算 / 历史序列化"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

ok = True
def check(name, cond, detail=""):
    global ok
    print(("OK  " if cond else "FAIL") + f" {name} {detail}")
    if not cond: ok = False

from app.services.agent_engine import _multimodal_content, _cap_image_blocks
from langchain_core.messages import HumanMessage

# ── _multimodal_content ──
c = _multimodal_content("这张图说明了什么", [("test.png", "data:image/png;base64,AAA")])
check("有图时返回blocks", isinstance(c, list) and c[0]["type"] == "text"
      and c[1]["type"] == "image_url" and c[1]["image_url"]["url"].startswith("data:image/png;base64,"))
check("文本块保留原文", c[0]["text"] == "这张图说明了什么")
c2 = _multimodal_content("纯文本", [])
check("无图返回原文本", c2 == "纯文本")
c3 = _multimodal_content("", [("a.jpg", "data:image/jpeg;base64,BBB")])
check("空文本有图时占位", isinstance(c3, list) and c3[0]["text"] == "（请查看以下图片）")

# ── _cap_image_blocks（预算：只留最近2张）──
msgs = [
    HumanMessage(content=[{"type": "text", "text": "第一问"},
                          {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG1"}},
                          {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG2"}}]),
    HumanMessage(content="中间普通消息"),
    HumanMessage(content=[{"type": "text", "text": "第三问"},
                          {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG3"}}]),
]
capped = _cap_image_blocks(msgs, max_images=2)
def img_count(m):
    c = getattr(m, "content", None)
    return sum(1 for b in c if isinstance(b, dict) and b.get("type") == "image_url") if isinstance(c, list) else 0
check("预算后总数=2", sum(img_count(m) for m in capped) == 2)
check("保留的是最新图(IMG3)", any("IMG3" in str(b) for m in capped for b in (m.content if isinstance(m.content, list) else [])))
first_msg_imgs = [b for b in capped[0].content if b.get("type") == "image_url"]
check("最旧消息只留1张图", len(first_msg_imgs) == 1)
check("被替换处有占位文本", any(b.get("type") == "text" and "已省略" in b.get("text", "")
                          for m in capped for b in (m.content if isinstance(m.content, list) else [])))
check("原消息未被修改(state安全)", img_count(msgs[0]) == 2)
_same = msgs[:1]
check("总数不超预算时不处理", _cap_image_blocks(_same, max_images=2) is _same)

# ── 历史端点 blocks 序列化（同款逻辑验证）──
def _blocks_to_text(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text": parts.append(b.get("text", ""))
                elif b.get("type") == "image_url": parts.append("[📷 已向大模型展示图片]")
            else: parts.append(str(b))
        return "\n".join(p for p in parts if p)
    return str(content)
t = _blocks_to_text(c)
check("历史序列化含文本与占位", "这张图说明了什么" in t and "[📷 已向大模型展示图片]" in t and "base64" not in t)
check("纯文本透传", _blocks_to_text("hello") == "hello")

print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
