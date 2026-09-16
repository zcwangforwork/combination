# -*- coding: utf-8 -*-
"""
wire_spa.py — 将移植产物接线进体系文档管理系统 SPA（combination 副本，幂等可重跑）。

编辑目标:
  ../user_management/frontend/index.html   (4 处: CSS / 菜单项 / 视图片段 / JS)
  ../user_management/frontend/js/app.js    (3 处: pageTitle / 菜单钩子 / 登出清理)
  ../design_planning_generation_local_model/app/main.py (1 处: CORSMiddleware)

每处插入均以标记做幂等守卫（已存在则跳过），锚点唯一性用 count==1 断言。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRONT = os.path.normpath(os.path.join(HERE, '..', 'user_management', 'frontend'))
INDEX = os.path.join(FRONT, 'index.html')
APPJS = os.path.join(FRONT, 'js', 'app.js')
MAINPY = os.path.normpath(os.path.join(
    HERE, '..', 'design_planning_generation_local_model', 'app', 'main.py'))
FRAG = os.path.join(FRONT, 'agent-view-fragment.html')


def rw(path, edits):
    """edits: [(anchor, replacement, marker, label)]；anchor 唯一且 marker 不存在时执行。
    锚点/替换文本按 LF 书写；文件为 CRLF 时自动适配（整文件统一行尾）。"""
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        text = f.read()
    crlf = '\r\n' in text
    for anchor, repl, marker, label in edits:
        if marker in text:
            print('SKIP (already wired): %s' % label)
            continue
        if crlf:
            anchor, repl = anchor.replace('\n', '\r\n'), repl.replace('\n', '\r\n')
        n = text.count(anchor)
        assert n == 1, '%s: anchor not unique (%d): %r' % (label, n, anchor[:60])
        text = text.replace(anchor, repl)
        print('WIRED: %s' % label)
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


AGENT_MARK_START = '<!-- AGENT-VIEW-START -->'
AGENT_MARK_END = '<!-- AGENT-VIEW-END -->'


def wire_view(text, frag):
    """插入或更新 agent 视图片段。返回 (新文本, 动作描述)。
    三种情况: 带标记 → 原地替换; 旧版无标记接线 → 定位旧块替换; 未接线 → 锚点插入。"""
    crlf = '\r\n' in text
    block = AGENT_MARK_START + '\n' + frag + '\n' + AGENT_MARK_END
    if crlf:
        block = block.replace('\n', '\r\n')

    # (a) 带标记的既有接线 → 原地替换（重建后片段变化时走此路径）
    if AGENT_MARK_START in text:
        i = text.index(AGENT_MARK_START)
        j = text.index(AGENT_MARK_END) + len(AGENT_MARK_END)
        assert 0 <= i < j, 'agent view markers malformed'
        return text[:i] + block + text[j:], 'replaced-marked'

    vshow = '<div v-show="activeMenu === \'agent-chat\'" class="agent-page">'
    end_anchor = '<!-- Employee Add/Edit Dialog -->'

    # (b) 旧版无标记接线 → 从 v-show 行起，到 Employee 锚点前最后一个 page-content 闭合止
    if vshow in text:
        p1 = text.index(vshow)
        pa = text.index(end_anchor, p1)
        tail = '\n            </div>\n        </div>'
        if crlf:
            tail = tail.replace('\n', '\r\n')
        p2 = text.rindex(tail, p1, pa)
        return text[:p1] + block + text[p2:], 'replaced-legacy'

    # (c) 未接线 → commercial-records 视图闭合后、.page-content 闭合前插入
    anchor = (
        '                </div>\n'
        '            </div>\n'
        '        </div>\n'
        '\n'
        '        <!-- Employee Add/Edit Dialog -->'
    )
    if crlf:
        anchor = anchor.replace('\n', '\r\n')
    assert text.count(anchor) == 1, 'view anchor not unique'
    repl = ('                </div>\n' + block + '\n            </div>\n        </div>\n'
            '\n        <!-- Employee Add/Edit Dialog -->')
    if crlf:
        repl = repl.replace('\n', '\r\n')
    return text.replace(anchor, repl), 'inserted'


def wire_index():
    with io.open(FRAG, 'r', encoding='utf-8') as f:
        frag = f.read().rstrip('\n')

    menu_item = (
        '                    <el-menu-item index="agent-chat">\n'
        '                        <el-icon><magic-stick /></el-icon>\n'
        '                        <span>AI 文档写作</span>\n'
        '                    </el-menu-item>\n'
    )

    # 视图片段：独立处理（支持更新已有接线，其余编辑仍走幂等 rw）
    with io.open(INDEX, 'r', encoding='utf-8', newline='') as f:
        text = f.read()
    text, action = wire_view(text, frag)
    with io.open(INDEX, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    print('WIRED: index.html agent view fragment (%s)' % action)

    rw(INDEX, [
        ('    <link rel="stylesheet" href="css/style.css">',
         '    <link rel="stylesheet" href="css/style.css">\n'
         '    <link rel="stylesheet" href="css/agent-chat.css">',
         'css/agent-chat.css', 'index.html +agent-chat.css'),
        ('                    <el-menu-item v-if="currentRole === \'ADMIN\'" index="departments">',
         menu_item
         + '                    <el-menu-item v-if="currentRole === \'ADMIN\'" index="departments">',
         'index="agent-chat"', 'index.html +menu-item'),
        ('    <script src="js/app.js"></script>',
         '    <script src="js/app.js"></script>\n'
         '    <script src="js/agent-chat.js"></script>',
         'js/agent-chat.js', 'index.html +agent-chat.js'),
    ])


def wire_appjs():
    rw(APPJS, [
        ("                'commercial-records': '商业成本记录',",
         "                'commercial-records': '商业成本记录',\n"
         "                'agent-chat': 'AI 文档写作',",
         "'agent-chat'", "app.js +pageTitle"),
        ('        const handleMenuSelect = (index) => {\n'
         '            activeMenu.value = index;',
         '        const handleMenuSelect = (index) => {\n'
         '            activeMenu.value = index;\n'
         '            // AI 文档写作: 首次进入初始化 agent 视图（幂等；重复点击无副作用）\n'
         "            if (index === 'agent-chat' && window.AgentChat) AgentChat.activate();",
         "index === 'agent-chat'", 'app.js +menu hook'),
        ('            localStorage.removeItem(\'token\');\n'
         '            localStorage.removeItem(\'user\');',
         '            localStorage.removeItem(\'token\');\n'
         '            localStorage.removeItem(\'user\');\n'
         '            // 中断 agent 进行中的 SSE 流与定时器（视图随 v-if 登录页切换而保留在 DOM，\n'
         '            // 但流不应在登出后继续）\n'
         '            if (window.AgentChat) AgentChat.deactivate();',
         'AgentChat.deactivate()', 'app.js +logout hook'),
    ])


def wire_mainpy():
    rw(MAINPY, [
        ('from app.api.routes import router',
         'from app.api.routes import router\n'
         '\n'
         '# [COMBINATION-PORT] 跨源 CORS: 允许体系文档管理系统前端(:3000)访问本服务。\n'
         '# 显式 origin 列表（不用 "*" + credentials 组合）；方法/请求头放开发内网所需范围\n'
         'from fastapi.middleware.cors import CORSMiddleware',
         'CORSMiddleware', 'main.py +cors import'),
    ])
    # 中间件本体必须在 app 实例创建后添加 —— 单独处理。
    # 标记用块注释（插入形态为 app.add_middleware(\n    CORSMiddleware 跨行，
    # 单行模式 'add_middleware(CORSMiddleware' 永远匹配不到 → 曾导致每次重跑重复插入）
    with io.open(MAINPY, 'r', encoding='utf-8', newline='') as f:
        text = f.read()
    if '# [COMBINATION-PORT] CORS' not in text:
        # 找 app = FastAPI(...) 的闭合括号后的第一个独立行
        anchor = 'app = FastAPI('
        i = text.index(anchor)
        j = text.index(')', i)  # FastAPI(...) 参数列表闭合
        insert_at = text.index('\n', j) + 1
        block = (
            '\n'
            '# [COMBINATION-PORT] CORS: 体系文档管理系统 SPA (http-server :3000) 跨源访问\n'
            'app.add_middleware(\n'
            '    CORSMiddleware,\n'
            '    allow_origins=[\n'
            '        "http://localhost:3000",\n'
            '        "http://127.0.0.1:3000",\n'
            '    ],\n'
            '    allow_methods=["*"],\n'
            '    allow_headers=["*"],\n'
            ')\n'
        )
        if '\r\n' in text:
            block = block.replace('\n', '\r\n')
        text = text[:insert_at] + block + text[insert_at:]
        print('WIRED: main.py +cors middleware')
    else:
        print('SKIP (already wired): main.py +cors middleware')
    with io.open(MAINPY, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


if __name__ == '__main__':
    wire_index()
    wire_appjs()
    wire_mainpy()
    print('=== wire_spa OK ===')
