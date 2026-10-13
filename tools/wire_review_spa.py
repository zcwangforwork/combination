# -*- coding: utf-8 -*-
"""
wire_review_spa.py — 将审核 agent 视图接线进体系文档管理系统 SPA（幂等可重跑）。

编辑目标（对齐 wire_spa.py 的做法）:
  ../user_management/frontend/index.html   4 处: css 引用 / 侧边栏菜单项 /
                                            视图片段(AGENT-REVIEW-VIEW 标记) / js 引用
  ../user_management/frontend/js/app.js    3 处: pageTitle / 菜单切换钩子 /
                                            登出钩子

幂等性: 每处编辑先查特征串已存在则 SKIP；视图片段用标记对整块替换（重跑=刷新）。
行尾: 目标文件为 CRLF —— 读 newline='' 原文判断，插入块统一转换，避免混行尾。
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'index.html'))
APPJS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'js', 'app.js'))
FRAG = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'agent-review-fragment.html'))

FRAG_START = '<!-- AGENT-REVIEW-VIEW-START -->'
FRAG_END = '<!-- AGENT-REVIEW-VIEW-END -->'


def _crlf_block(block, crlf):
    """插入块以 \\n 构造，按目标文件行尾统一转换"""
    return block.replace('\n', '\r\n') if crlf else block


def rw(path, fn):
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        text = f.read()
    crlf = '\r\n' in text
    text2, action = fn(text, crlf)
    if text2 != text:
        with io.open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text2)
    return action


# ── index.html ────────────────────────────────────────────────

def wire_index(text, crlf):
    # 1) css 引用：插在 agent-chat.css 之后（同 head 内顺序加载）
    if 'css/agent-review.css' in text:
        print('SKIP (already wired): index.html css link')
    else:
        pat = re.compile(r'(<link rel="stylesheet" href="css/agent-chat\.css[^>]*>)(\r?\n)')
        m = pat.search(text)
        assert m, 'agent-chat.css link not found'
        ins = _crlf_block('    <link rel="stylesheet" href="css/agent-review.css">\n', crlf)
        text = text[:m.end(2)] + ins + text[m.end(2):]
        print('WIRED: index.html css link')

    # 2) 侧边栏菜单项：紧随「AI 文档写作」项（图标 DocumentChecked 已全局注册）
    if 'index="agent-review"' in text:
        print('SKIP (already wired): index.html menu item')
    else:
        anchor = _crlf_block(
            '                    <el-menu-item index="agent-chat">\n'
            '                        <el-icon><magic-stick /></el-icon>\n'
            '                        <span>AI 文档写作</span>\n'
            '                    </el-menu-item>\n', crlf)
        assert text.count(anchor) == 1, 'agent-chat menu anchor not unique'
        item = _crlf_block(
            '                    <el-menu-item index="agent-review">\n'
            '                        <el-icon><DocumentChecked /></el-icon>\n'
            '                        <span>AI 文档审核</span>\n'
            '                    </el-menu-item>\n', crlf)
        text = text.replace(anchor, anchor + item)
        print('WIRED: index.html menu item')

    # 3) 视图片段：AGENT-VIEW-END 之后；标记对内整块替换（重跑=刷新内容）
    with io.open(FRAG, 'r', encoding='utf-8') as f:
        frag = f.read().strip('\n')
    frag = _crlf_block(frag, crlf)
    block = _crlf_block(
        '\n' + FRAG_START + '\n' + frag + '\n' + FRAG_END + '\n', crlf)
    if FRAG_START in text:
        i = text.index(FRAG_START)
        j = text.index(FRAG_END) + len(FRAG_END)
        # 连同标记后的行尾一起吃掉，避免重跑时行尾累积
        k = j
        if text[k:k + 2] == '\r\n':
            k += 2
        elif text[k:k + 1] == '\n':
            k += 1
        text = text[:i] + block.lstrip('\r\n') + text[k:]
        print('WIRED: index.html view fragment (replaced)')
    else:
        anchor = _crlf_block('<!-- AGENT-VIEW-END -->\n', crlf)
        assert text.count(anchor) == 1, 'AGENT-VIEW-END anchor not unique'
        text = text.replace(anchor, anchor + block)
        print('WIRED: index.html view fragment (inserted)')

    # 4) js 引用：插在 agent-chat.js 之后（body 尾，初始化顺序无关——IIFE 无副作用）
    if 'js/agent-review.js' in text:
        print('SKIP (already wired): index.html js script')
    else:
        pat = re.compile(r'(<script src="js/agent-chat\.js[^>]*></script>)(\r?\n)')
        m = pat.search(text)
        assert m, 'agent-chat.js script not found'
        ins = _crlf_block('    <script src="js/agent-review.js"></script>\n', crlf)
        text = text[:m.end(2)] + ins + text[m.end(2):]
        print('WIRED: index.html js script')

    return text, 'index.html'


# ── app.js ────────────────────────────────────────────────────

def wire_appjs(text, crlf):
    # 1) 页面标题映射
    if "'agent-review':" in text:
        print('SKIP (already wired): app.js pageTitle')
    else:
        anchor = _crlf_block("                'agent-chat': 'AI 文档写作',\n", crlf)
        assert text.count(anchor) == 1, 'pageTitle anchor not unique'
        ins = _crlf_block("                'agent-review': 'AI 文档审核',\n", crlf)
        text = text.replace(anchor, anchor + ins)
        print('WIRED: app.js pageTitle')

    # 2) 菜单切换钩子：handleMenuSelect 内首次进入初始化（幂等）
    if "index === 'agent-review'" in text:
        print('SKIP (already wired): app.js menu hook')
    else:
        anchor = _crlf_block(
            "            if (index === 'agent-chat' && window.AgentChat) AgentChat.activate();\n", crlf)
        assert text.count(anchor) == 1, 'menu hook anchor not unique'
        ins = _crlf_block(
            '            // AI 文档审核: 首次进入初始化 review 视图（幂等；重复点击无副作用）\n'
            "            if (index === 'agent-review' && window.AgentReview) AgentReview.activate();\n",
            crlf)
        text = text.replace(anchor, anchor + ins)
        print('WIRED: app.js menu hook')

    # 3) 登出钩子：中断 SSE 流与倒计时
    if 'window.AgentReview) AgentReview.deactivate()' in text:
        print('SKIP (already wired): app.js logout hook')
    else:
        anchor = _crlf_block('            if (window.AgentChat) AgentChat.deactivate();\n', crlf)
        assert text.count(anchor) == 1, 'logout hook anchor not unique'
        ins = _crlf_block('            if (window.AgentReview) AgentReview.deactivate();\n', crlf)
        text = text.replace(anchor, anchor + ins)
        print('WIRED: app.js logout hook')

    return text, 'app.js'


def main():
    assert os.path.exists(FRAG), 'fragment missing: %s（先运行 build_review_port.py）' % FRAG
    rw(INDEX, wire_index)
    rw(APPJS, wire_appjs)
    print('=== wire_review_spa OK ===')


if __name__ == '__main__':
    main()
