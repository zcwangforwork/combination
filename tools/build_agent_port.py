# -*- coding: utf-8 -*-
"""
build_agent_port.py — 将 agent.html 忠实移植为体系文档管理系统 SPA 的嵌入视图。

输入（只读源）:
  ../design_planning_generation_local_model/app/static/agent.html
  ../user_management/frontend/css/style.css        (仅读取选择器，用于泄漏防护)

输出:
  ../user_management/frontend/css/agent-chat.css   (命名空间化 + 防泄漏守卫)
  ../user_management/frontend/js/agent-chat.js     (IIFE 封装 + 内联处理器导出)
  ../user_management/frontend/agent-view-fragment.html (待插入 index.html 的视图片段)

变换规则（全部机械化，可审计，可重复运行）:
  CSS: 选择器限定 #agent-root；@keyframes 改名 ag-*；body 100vh→100%；
       与 UM style.css 类名交集的 UM 独有属性发射 unset 守卫
  HTML: 包进 v-show 视图容器 + #agent-root[v-pre]（Vue 跳过编译，onclick 保持原生全局解析）
  JS:  IIFE（非严格模式，保持原文语义）+ window 导出全部内联 handler 函数；
       AGENT_BASE 端口探测(8002→8004)；全部 /api|/agent/review|/kb 加前缀；
       PROJECT_ID const→let + localStorage；项目切换/初始化改视图内一次性执行
  AUTH（用户隔离，combination 新增）：
       fetch 包装注入 Authorization: Bearer <UM JWT>（token 读 localStorage['token']）；
       401 → 顶部横幅提示重登；localStorage 项目 key 按用户名区分（JWT payload sub）；
       PROJECT_ID 生成改 crypto.randomUUID()（防跨用户毫秒级碰撞合并历史）；
       window.open 直开的下载接口改 _agentDownload（fetch→blob→a.click，凭证不进 URL）；
       review/kb 新标签页 URL 附加 #jwt= 片段（页内 token-relay.js 接收转存）
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(
    HERE, '..', 'design_planning_generation_local_model', 'app', 'static', 'agent.html'))
UM_CSS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'css', 'style.css'))
OUT_CSS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'css', 'agent-chat.css'))
OUT_JS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'js', 'agent-chat.js'))
OUT_FRAG = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'agent-view-fragment.html'))
INDEX_HTML = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'index.html'))

with io.open(SRC, 'r', encoding='utf-8') as f:
    FULL = f.read()
    lines = FULL.splitlines(keepends=True)

with io.open(UM_CSS, 'r', encoding='utf-8') as f:
    UM_CSS_TEXT = f.read()

# ── 源文件区段边界（1-based 行号；2026-09-20 源项目同步后重算：
#    <style>@10 </style>@559 <body>@562 <style2>@844 </style2>@858 <script>@860 </script>@4616）──
CSS1 = ''.join(lines[10:558])    # lines 11-558  主 <style>
BODY = ''.join(lines[562:843])   # lines 563-843 <body> 内 HTML（止于第二个 <style> 前）
CSS2 = ''.join(lines[844:857])   # lines 845-857 第二个 <style>（chat-reasoning）
JS = ''.join(lines[860:4615])    # lines 861-4615 主 <script> 内容

AGENT_CSS = CSS1 + '\n' + CSS2


# ══════════════════════════════════════════════════════════════
# 通用：极简 CSS 规则扫描器（顶层 + @media 递归）
# ══════════════════════════════════════════════════════════════

def iter_rules(css_text):
    """yield (head, body)；@media 展开为内部规则（head 不含 @media 条件）。"""
    i, n = 0, len(css_text)
    while i < n:
        if css_text[i:i + 2] == '/*':
            end = css_text.find('*/', i)
            i = n if end == -1 else end + 2
            continue
        brace = css_text.find('{', i)
        if brace == -1:
            break
        head = css_text[i:brace].strip()
        depth, j = 1, brace + 1
        while j < n and depth:
            if css_text[j] == '{':
                depth += 1
            elif css_text[j] == '}':
                depth -= 1
            j += 1
        body = css_text[brace + 1:j - 1]
        if head.startswith('@media'):
            for h, b in iter_rules(body):
                yield h, b
        elif head and not head.startswith('@'):
            yield head, body
        i = j


def props_of(body):
    names = set()
    for decl in body.split(';'):
        decl = decl.strip()
        if not decl or decl.startswith('/*') or decl.startswith('@'):
            continue
        prop = decl.split(':', 1)[0].strip()
        if re.match(r'^-?[a-zA-Z][\w-]*$', prop):
            names.add(prop)
    return names


# ══════════════════════════════════════════════════════════════
# CSS 命名空间化 + 防泄漏守卫
# ══════════════════════════════════════════════════════════════

def _prefix_selector(sel: str) -> str:
    sel = sel.strip()
    if not sel:
        return sel
    if sel in ('body', 'html'):
        return '#agent-root'
    if sel == '*':
        return '#agent-root, #agent-root *'
    return '#agent-root ' + sel


def _scope_rules(css_text: str, keyframe_names: dict) -> str:
    out = []
    i, n = 0, len(css_text)
    while i < n:
        # 保留注释与空白
        m = re.match(r'\s+', css_text[i:])
        if m:
            out.append(m.group(0))
            i += m.end()
            continue
        if css_text[i:i + 2] == '/*':
            m2 = re.match(r'/\*.*?\*/', css_text[i:], re.S)
            out.append(m2.group(0))
            i += m2.end()
            continue
        brace = css_text.find('{', i)
        if brace == -1:
            out.append(css_text[i:])
            break
        head = css_text[i:brace]
        depth, j = 1, brace + 1
        while j < n and depth:
            if css_text[j] == '{':
                depth += 1
            elif css_text[j] == '}':
                depth -= 1
            j += 1
        body = css_text[brace + 1:j - 1]
        head_stripped = head.strip()
        if head_stripped.startswith('@keyframes'):
            m3 = re.match(r'@keyframes\s+([\w-]+)', head_stripped)
            name = m3.group(1)
            new_name = 'ag-' + name
            keyframe_names[name] = new_name
            out.append('@keyframes %s {%s}' % (new_name, body))
        elif head_stripped.startswith('@media'):
            out.append('%s{%s}' % (head_stripped, _scope_rules(body, keyframe_names)))
        elif head_stripped.startswith('@'):
            out.append(css_text[i:j])
        else:
            sels = ', '.join(_prefix_selector(s) for s in head.split(','))
            out.append('%s {%s}' % (sels, body))
        i = j
    return ''.join(out)


def compute_leak_guards():
    """SPA style.css → agent 视图 的样式泄漏防护。

    两侧类名交集上，UM 定义而 agent 未定义的属性会泄漏进 agent 元素
    （#agent-root 前缀只赢得重叠属性）。对这些属性发射 unset 守卫。
    """
    um_class_props = {}   # '.classname' -> props 并集（含 @media 内）
    for head, body in iter_rules(UM_CSS_TEXT):
        for m in re.finditer(r'\.([A-Za-z_][\w-]*)', head):
            um_class_props.setdefault('.' + m.group(1), set()).update(props_of(body))

    ag_class_props = {}
    for head, body in iter_rules(AGENT_CSS):
        for m in re.finditer(r'\.([A-Za-z_][\w-]*)', head):
            ag_class_props.setdefault('.' + m.group(1), set()).update(props_of(body))

    shared = sorted(set(um_class_props) & set(ag_class_props))
    guard_rules = []
    for cls in shared:
        um_only = sorted(um_class_props[cls] - ag_class_props[cls])
        if um_only:
            decls = '\n    '.join('%s: unset;' % p for p in um_only)
            guard_rules.append('#agent-root %s {\n    /* UM-only-props guard */\n    %s\n}' % (cls, decls))
    return shared, guard_rules


def transform_css():
    keyframe_names = {}
    scoped = _scope_rules(AGENT_CSS, keyframe_names)

    # body 规则映射为 #agent-root；高度适配 100vh → 100%（宽松兜底）
    scoped = re.sub(r'(#agent-root \{[^}]*?)height: 100vh;',
                    r'\1height: 100%;\n            min-height: 0;',
                    scoped, count=1)

    # keyframes 引用同步改名
    for old, new in keyframe_names.items():
        scoped = re.sub(r'animation:\s*%s\b' % re.escape(old), 'animation: %s' % new, scoped)
        scoped = re.sub(r'animation-name:\s*%s\b' % re.escape(old), 'animation-name: %s' % new, scoped)

    shared, guards = compute_leak_guards()

    header = (
        '/*\n'
        ' * agent-chat.css — 由 agent.html 提取并命名空间化（#agent-root）\n'
        ' * 生成脚本: combination/tools/build_agent_port.py（勿手改，重跑脚本覆盖）\n'
        ' * 类名交集（UM↔agent）: %s\n'
        ' */\n\n'
        '/* 全屏浮层：agent 视图覆盖整个视口（含 UM 头部与侧边栏），还原原独立页体验。\n'
        '   v-show 关闭时 display:none，不参与布局；z-index 低于 UM 弹层(2000+)，\n'
        '   agent 内部浮层（遮罩 1000/toast 2000）在本层叠上下文内不受影响 */\n'
        '.agent-page {\n'
        '    position: fixed; top: 0; left: 0; right: 0; bottom: 0;\n'
        '    z-index: 1800;\n'
        '    background: #f5f7fa;\n'
        '    overflow: hidden;\n'
        '}\n\n'
        '/* 全屏模式返回按钮（agent 工具栏首项，随工具栏流动不遮挡既有按钮）*/\n'
        '#agent-root .agent-back-btn {\n'
        '    margin-right: 12px; padding: 6px 14px; flex-shrink: 0;\n'
        '    background: #455a64; color: #fff; border: none; border-radius: 6px;\n'
        '    font-size: 12px; cursor: pointer;\n'
        '}\n'
        '#agent-root .agent-back-btn:hover { background: #37474f; }\n\n'
        '/* Agent 服务不可用提示横幅 */\n'
        '#agent-root .agent-service-error {\n'
        '    margin: 16px auto; max-width: 560px; padding: 14px 18px;\n'
        '    background: #ffebee; color: #c62828; border: 1px solid #ef9a9a;\n'
        '    border-radius: 8px; font-size: 13px; line-height: 1.7; text-align: center;\n'
        '}\n'
        '#agent-root .agent-service-error button {\n'
        '    margin-top: 8px; padding: 4px 14px; background: #c62828; color: #fff;\n'
        '    border: none; border-radius: 6px; cursor: pointer; font-size: 12px;\n'
        '}\n\n'
    ) % (', '.join(shared) or '(无)')

    guard_block = ''
    if guards:
        guard_block = ('\n/* ══ SPA 样式泄漏防护（自动生成，误删会导致 UM 属性渗入 agent 视图）══ */\n'
                       + '\n\n'.join(guards) + '\n')

    return header + scoped + guard_block, keyframe_names, shared


# ══════════════════════════════════════════════════════════════
# HTML 片段：v-show 视图容器 + #agent-root[v-pre] + 错误横幅
# ══════════════════════════════════════════════════════════════

def transform_body():
    banner = (
        '\n        <!-- Agent 服务不可用横幅（由 agent-chat.js 控制） -->\n'
        '        <div class="agent-service-error" id="agentServiceError" style="display:none">\n'
        '            <div>⚠ 无法连接设计开发文档写作 Agent 服务（已尝试端口 8002 / 8003 / 8004）。</div>\n'
        '            <div style="font-size:12px;color:#b71c1c;margin-top:4px">请确认 Agent 服务已启动（见 combination/README.md），然后重试。</div>\n'
        '            <button onclick="AgentChat.activate(true)">重试连接</button>\n'
        '        </div>\n'
    )
    # 全屏模式返回 UM 系统的入口：插入为 agent 工具栏首项（随工具栏流动，不遮挡既有按钮）
    assert BODY.count('<div class="main-header">') == 1, 'main-header anchor not unique'
    body = BODY.replace(
        '<div class="main-header">',
        '<div class="main-header">\n'
        '            <button class="agent-back-btn" onclick="AgentChat.backToSystem()"'
        ' title="返回体系文档管理系统">⟵ 返回系统</button>', 1)
    # v-pre: Vue 编译器跳过整个子树 —— 内联 onclick 保持原生全局解析（window.fn 导出），
    # 原生 JS 的 DOM 修改不会被 Vue 补丁触碰
    return ('<div v-show="activeMenu === \'agent-chat\'" class="agent-page">\n'
            '<div id="agent-root" v-pre>\n'
            + banner + body +
            '\n</div>\n</div>\n')


# ══════════════════════════════════════════════════════════════
# 内联事件处理器发现（静态 HTML + JS 模板字符串动态生成的 handler 全覆盖）
# ══════════════════════════════════════════════════════════════

JS_BUILTINS = {
    'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'new',
    'confirm', 'alert', 'prompt', 'parseInt', 'parseFloat', 'isNaN',
    'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'setInterval',
    'clearTimeout', 'clearInterval', 'fetch', 'String', 'Number', 'Boolean',
    'Array', 'Object', 'Date', 'Math', 'JSON', 'Promise', 'RegExp', 'Error',
    'event', 'stopPropagation', 'preventDefault', 'AgentChat',
}


def discover_inline_handlers():
    """扫描全文（含 JS 生成的动态 HTML）中 onXXX="code" 引用的函数名，
    与 JS 函数声明求交 → 必须导出到 window 的函数清单。"""
    codes = []
    for m in re.finditer(r'on(?:click|change|input|submit|keydown|keyup|keypress|load|error|focus|blur|mouseover|mouseout|mousedown|mouseup)\s*=\s*"([^"]*)"', FULL):
        codes.append(m.group(1))
    for m in re.finditer(r"on(?:click|change|input|submit|keydown|keyup|keypress|load|error|focus|blur|mouseover|mouseout|mousedown|mouseup)\s*=\s*'([^']*)'", FULL):
        codes.append(m.group(1))

    names = set()
    for code in codes:
        # (?<![.\w$]) 排除方法调用（.fn(）与属性访问
        for m in re.finditer(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(', code):
            names.add(m.group(1))

    declared = set(re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(', JS))
    to_export = sorted(names & declared)
    missing = sorted(n for n in names - declared if n not in JS_BUILTINS)
    return to_export, missing, len(codes)


# ══════════════════════════════════════════════════════════════
# JS 变换
# ══════════════════════════════════════════════════════════════

OLD_PROJECT_BLOCK = '''        // ── State ──
        // 从URL参数恢复已有项目，或创建新项目ID
        const urlParams = new URLSearchParams(window.location.search);
        const existingProject = urlParams.get('project');
        const PROJECT_ID = existingProject || ('project_' + Date.now());
        // 更新URL以保持PROJECT_ID一致（支持页面刷新后恢复）
        if (!existingProject) {
            const newUrl = window.location.pathname + '?project=' + PROJECT_ID;
            window.history.replaceState({}, '', newUrl);
        }
'''

NEW_PROJECT_BLOCK = '''        // ── State ──
        // [PORT] 原从 URL ?project= 恢复并 replaceState 写回；
        // SPA 内嵌后改为 localStorage 持久化（读=恢复，写=新建后立即落盘）
        // [PORT-AUTH] key 按登录用户名区分：同浏览器多账号切换互不串项目；
        // 新建 ID 用 UUID：两用户同一毫秒新建不再碰撞出同一 thread_id。
        // 本脚本随 SPA 首屏加载，彼时可能尚未登录（无 token → 用户名不可知），
        // 故恢复读取与首次落盘均延迟到 _doInit()（activate 时必已登录）
        let _restoredProject = null;
        let PROJECT_ID = null;
        // [PORT] 原语义：!existingProject 时 loadHistory 直接返回（新项目页面生命周期内不拉历史）。
        // 恢复/切换到既有项目时为 true，新建项目时为 false
        let _hasHistory = false;
        function _persistProject() { if (PROJECT_ID) localStorage.setItem(_projectKey(), PROJECT_ID); }
'''

OLD_INIT = '''        // ── Init ──
        if (existingProject) {
            // 恢复已有项目：清除空状态，显示恢复提示
            const area = document.getElementById('chatArea');
            area.innerHTML = '';
            appendMessage('agent', '已恢复之前的会话。文档生成进度已加载，可继续操作或直接下载。');
            // 加载之前的对话历史（用户消息 + Agent 回复），展示在恢复提示之后；
            // 若该任务仍有后台生成在进行（切换任务后切回/刷新页面），自动重连续播
            checkAndReconnect();
            fetchState();
        }
        // 始终从服务端加载附件列表（新项目也可能已有上传记录）
        fetchAttachments();
        // 加载侧边栏聊天任务列表（多任务切换）
        loadChatList();
        // 加载已添加的模板
        fetchTemplates();
        // 找回刷新/切换任务后中断的模板上传：补 finalize 孤儿模板任务
        recoverOrphanTemplates();
        // 恢复进行中的上传（知识库/模板）：进度 UI + 续接轮询（跨刷新/任务切换）
        restoreActiveUploads();
        // 加载完整文档类型列表（填充模板「目标文档类型」下拉框）
        loadDocTypes();
        renderSteps({});
        document.getElementById('userInput').focus();
'''

NEW_INIT = '''        // ── Init（[PORT] 原为脚本尾部立即执行；改为 activate() 首次触发，一次性执行。
        // 后续菜单切换不重跑——v-show 视图与页面共存亡，等价于原页面持续打开）──
        let _inited = false;

        function _resetTransientState() {
            // 切换项目时清理进行中的流与定时器（登出走 deactivate 同路径）
            try { if (currentAbortController) currentAbortController.abort(); } catch (e) { /* ignore */ }
            resetTypewriter();
            resetChatReasoning();
            isStreaming = false;
            waitingApproval = null;
            const pauseBtn = document.getElementById('pauseBtn');
            if (pauseBtn) pauseBtn.style.display = 'none';
        }

        // [PORT] 视图内切换项目（原为整页跳转 ?project=，状态由页面重载天然隔离；
        // 此处手动完成等价的"重载"：换 ID、清屏、重跑初始化）
        function _switchToProject(projectId) {
            _resetTransientState();
            PROJECT_ID = projectId || ('project_' + _newProjectId());
            _persistProject();
            _hasHistory = !!projectId;
            const area = document.getElementById('chatArea');
            area.innerHTML = '';
            appendMessage('agent', projectId
                ? '已切换聊天任务。文档生成进度已加载，可继续操作或直接下载。'
                : '已开始新的聊天任务。');
            if (projectId) {
                checkAndReconnect();
                fetchState();
            }
            fetchAttachments();
            loadChatList();
            fetchTemplates();
            recoverOrphanTemplates();
            restoreActiveUploads();
            renderSteps({});
            _refreshProjectBadge(!!projectId);
            _refreshReviewLink();
        }

        function _doInit() {
            if (_inited) return;
            _inited = true;
            // [PORT-AUTH] 登录后才可知用户名：此处才读按用户分键的恢复项目并落盘
            _restoredProject = localStorage.getItem(_projectKey());
            PROJECT_ID = _restoredProject || ('project_' + _newProjectId());
            _hasHistory = !!_restoredProject;
            _persistProject();
            // [PORT] 原顶层的 DOM 事件绑定（登录后视图 DOM 才存在）
            setupDragDrop();
            setupInputDragDrop();
            setupKbDialogMask();
            if (_restoredProject) {
                // 恢复已有项目：清除空状态，显示恢复提示
                const area = document.getElementById('chatArea');
                area.innerHTML = '';
                appendMessage('agent', '已恢复之前的会话。文档生成进度已加载，可继续操作或直接下载。');
                // 加载之前的对话历史（用户消息 + Agent 回复），展示在恢复提示之后；
                // 若该任务仍有后台生成在进行（切换任务后切回/刷新页面），自动重连续播
                checkAndReconnect();
                fetchState();
            }
            // 始终从服务端加载附件列表（新项目也可能已有上传记录）
            fetchAttachments();
            // 加载侧边栏聊天任务列表（多任务切换）
            loadChatList();
            // 加载已添加的模板
            fetchTemplates();
            // 找回刷新/切换任务后中断的模板上传：补 finalize 孤儿模板任务
            recoverOrphanTemplates();
            // 恢复进行中的上传（知识库/模板）：进度 UI + 续接轮询（跨刷新/任务切换）
            restoreActiveUploads();
            // 加载完整文档类型列表（填充模板「目标文档类型」下拉框）
            loadDocTypes();
            renderSteps({});
            _refreshProjectBadge(!!_restoredProject);
            _refreshReviewLink();
            document.getElementById('userInput').focus();
        }
'''


def transform_js():
    js = JS
    rep_counts = {}

    def rep(old, new, key):
        assert old in js, 'pattern not found: %s' % key
        rep_counts[key] = js.count(old)
        return js.replace(old, new)

    # 0) 项目状态块
    js = rep(OLD_PROJECT_BLOCK, NEW_PROJECT_BLOCK, 'project_block')

    # 1) API / 页面地址前缀
    for pat, new, key in [
        ('fetch(`/api/', 'fetch(`${AGENT_BASE}/api/', 'tpl_fetch'),
        ("fetch('/api/", "fetch(AGENT_BASE + '/api/", 'str_fetch'),
        ('window.open(`/api/', 'window.open(`${AGENT_BASE}/api/', 'tpl_open'),
        ("window.open('/api/", "window.open(AGENT_BASE + '/api/", 'str_open'),
        ("reviewLink.href = '/agent/review/' + PROJECT_ID;",
         "reviewLink.href = AGENT_BASE + '/agent/review/' + PROJECT_ID;", 'review_href'),
        ("window.location.href = '/kb?project=' + encodeURIComponent(PROJECT_ID);",
         "window.open(AGENT_BASE + '/kb?project=' + encodeURIComponent(PROJECT_ID), '_blank');", 'kb_nav'),
    ]:
        js = rep(pat, new, key)

    # 1b) [PORT-AUTH] 下载接口改认证下载：window.open 无法携带请求头 →
    #     _agentDownload（fetch 带 token → blob → a.click），凭证全程不进 URL
    for pat, new, key in [
        ("window.open(AGENT_BASE + '/api/agent/download/' + downloadId, '_blank');",
         "_agentDownload(AGENT_BASE + '/api/agent/download/' + downloadId);", 'auth_dl_downloadid'),
        ("window.open(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/download', '_blank');",
         "_agentDownload(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/download');", 'auth_dl_doc'),
        ("window.open(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/download-excel', '_blank');",
         "_agentDownload(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/download-excel');", 'auth_dl_excel'),
        ("window.open(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/modified-documents/${encodeURIComponent(latest.file_id)}/download`, '_blank');",
         "_agentDownload(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/modified-documents/${encodeURIComponent(latest.file_id)}/download`);", 'auth_dl_latest'),
        ("window.open(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/modified-documents/' + fileId + '/download', '_blank');",
         "_agentDownload(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/modified-documents/' + fileId + '/download');", 'auth_dl_file'),
        # kb 新标签页：URL 附加 #jwt= 片段（页内 token-relay.js 接收转存 sessionStorage）
        ("window.open(AGENT_BASE + '/kb?project=' + encodeURIComponent(PROJECT_ID), '_blank');",
         "window.open(_agentPageUrl(AGENT_BASE + '/kb?project=' + encodeURIComponent(PROJECT_ID)), '_blank');",
         'auth_kb_url'),
    ]:
        js = rep(pat, new, key)

    # 2) 项目切换：location.href → 视图内切换
    js = rep('''        function switchChat(projectId) {
            if (projectId === PROJECT_ID) return;
            window.location.href = window.location.pathname + '?project=' + encodeURIComponent(projectId);
        }''',
        '''        function switchChat(projectId) {
            if (projectId === PROJECT_ID) return;
            _switchToProject(projectId);
        }''', 'switch_chat')
    js = rep('''        function startNewChat() {
            window.location.href = window.location.pathname;
        }''',
        '''        function startNewChat() {
            _switchToProject(null);
        }''', 'start_new_chat')
    js = rep('''                if (isCurrent) {
                    window.location.href = window.location.pathname;  // 跳转到新聊天
                } else {''',
        '''                if (isCurrent) {
                    _switchToProject(null);  // [PORT] 原为整页跳转，改为视图内切换
                } else {''', 'delete_current')

    # 3) 初始化块
    js = rep(OLD_INIT, NEW_INIT, 'init_block')

    # 3b) 顶层立即执行的 DOM 绑定 → 具名函数（登录前 v-if 分支未渲染，DOM 不存在；
    # 且顶层崩溃会终止整个 IIFE，window.AgentChat 都不会定义）
    js = rep('''        // Drag-and-drop on chat area
        (function setupDragDrop() {''',
        '''        // Drag-and-drop on chat area（[PORT] 顶层 IIFE → 具名函数，由 _doInit 首次调用）
        function setupDragDrop() {''', 'iife_dragdrop_head')
    js = rep('''            attArea.addEventListener('dragleave', function(e) {
                attArea.classList.remove('drag-over');
            });
        })();''',
        '''            attArea.addEventListener('dragleave', function(e) {
                attArea.classList.remove('drag-over');
            });
        }''', 'iife_dragdrop_tail')
    js = rep('        (function setupInputDragDrop() {',
             '        function setupInputDragDrop() {', 'iife_input_head')
    js = rep('''            });
        })();

        // ── Progress Panel ──''',
        '''            });
        }

        // ── Progress Panel ──''', 'iife_input_tail')
    js = rep('''        // 点击遮罩层关闭
        document.getElementById('kbFilesDialog').addEventListener('click', function(e) {
            if (e.target === this) closeKbFilesDialog();
        });''',
        '''        // 点击遮罩层关闭（[PORT] 顶层绑定 → 具名函数，由 _doInit 首次调用）
        function setupKbDialogMask() {
            document.getElementById('kbFilesDialog').addEventListener('click', function(e) {
                if (e.target === this) closeKbFilesDialog();
            });
        }''', 'kbmask_toplevel')

    # 4) 徽标 + reviewLink 顶层设置改为函数（随初始化/项目切换刷新）
    js = rep('''        document.getElementById('projectBadge').textContent =
            '项目: ' + (existingProject ? '已恢复会话' : new Date().toLocaleDateString());
        // Set up review link
        const reviewLink = document.getElementById('reviewLink');
        reviewLink.href = AGENT_BASE + '/agent/review/' + PROJECT_ID;
        reviewLink.style.display = 'inline';''',
        '''        // [PORT] 项目徽标 + review 链接改为函数，随初始化/项目切换刷新
        function _refreshProjectBadge(restored) {
            document.getElementById('projectBadge').textContent =
                '项目: ' + (restored ? '已恢复会话' : new Date().toLocaleDateString());
        }
        function _refreshReviewLink() {
            const reviewLink = document.getElementById('reviewLink');
            reviewLink.href = AGENT_BASE + '/agent/review/' + PROJECT_ID;
            reviewLink.style.display = 'inline';
        }''', 'badge_review_fn')

    # 4b) [PORT-AUTH] review 链接附加 #jwt= 片段（新标签页由 token-relay.js 接收；
    #      必须在 badge_review_fn 之后做，改写其产物中的最终赋值形式）
    js = rep("reviewLink.href = AGENT_BASE + '/agent/review/' + PROJECT_ID;",
             "reviewLink.href = _agentPageUrl(AGENT_BASE + '/agent/review/' + PROJECT_ID);",
             'auth_review_url')

    # 5) loadHistory 守卫：existingProject → _hasHistory（复刻原语义）
    js = rep('            if (!existingProject) return;',
             '            if (!_hasHistory) return;  // [PORT] 原 !existingProject', 'history_guard')

    return js, rep_counts


def build_js(to_export):
    js, rep_counts = transform_js()

    header = '''/*
 * agent-chat.js — 由 agent.html 的内联 <script> 忠实移植（构建脚本生成，勿手改）
 * 生成脚本: combination/tools/build_agent_port.py
 *
 * 相对原文的改动（全部为嵌入 SPA 所必需，对话逻辑零重写）:
 *  1. IIFE 封装（非严格模式，保持原文语义）；内联事件处理器全部导出到 window
 *  2. AGENT_BASE 运行时解析：依次健康探测 :8002/:8003/:8004（对齐后端端口回退）
 *  3. 全部 /api/**、/agent/review/**、/kb 地址加 AGENT_BASE 前缀（跨源 CORS）
 *  4. 项目 ID 由 URL ?project= 改为 localStorage 持久化 + 视图内切换
 *  5. 初始化改为 activate() 首次惰性触发；登出 deactivate() 中断流；mermaid 按需加载
 *  6. [PORT-AUTH] 用户隔离：fetch 包装自动携带 Authorization: Bearer <UM JWT>；
 *     localStorage 项目 key 按用户名区分；新建项目 ID 用 UUID 防跨用户碰撞；
 *     下载接口走 _agentDownload（凭证不进 URL）；review/kb 页经 #jwt= 片段中转凭证
 */
(function () {

    // ── Agent 服务地址解析（健康探测，缓存；探测目的=找端口，不代表 Ollama 就绪）──
    let AGENT_BASE = '';
    let _baseProbing = null;

    function resolveAgentBase(force) {
        if (AGENT_BASE && !force) return Promise.resolve(AGENT_BASE);
        if (_baseProbing) return _baseProbing;
        _baseProbing = (async () => {
            for (const port of [8002, 8003, 8004]) {
                const base = window.location.protocol + '//' + window.location.hostname + ':' + port;
                try {
                    const r = await fetch(base + '/api/health', { method: 'GET' });
                    if (r.ok) { AGENT_BASE = base; return base; }
                } catch (e) { /* 端口不通，试下一个 */ }
            }
            return null;
        })();
        var p = _baseProbing;
        p.then(function () { _baseProbing = null; }, function () { _baseProbing = null; });
        return p;
    }

    // ── mermaid 按需加载（原为 <head> 同步引入，SPA 内避免拖慢首屏）──
    let _mermaidLoading = null;
    function ensureMermaid() {
        if (window.mermaid) return Promise.resolve(window.mermaid);
        if (_mermaidLoading) return _mermaidLoading;
        _mermaidLoading = new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
            s.onload = () => resolve(window.mermaid);
            s.onerror = () => reject(new Error('mermaid 加载失败'));
            document.head.appendChild(s);
        });
        return _mermaidLoading;
    }

    // ── [PORT-AUTH] 用户隔离（combination 新增）──
    // 体系管理系统登录后 JWT 存于 localStorage['token']（:3000 源）；Agent 服务以
    // 共享密钥验签（HS256），项目归属按用户名（sub claim）隔离。

    function _umToken() {
        try { return localStorage.getItem('token') || ''; } catch (e) { return ''; }
    }

    // 从 JWT payload 解出用户名（仅用于本地 key 命名，不做签名校验——校验在服务端）
    function _umUsername() {
        var t = _umToken();
        try {
            var part = t.split('.')[1];
            if (!part) return 'anonymous';
            part = part.replace(/-/g, '+').replace(/_/g, '/');
            while (part.length % 4) part += '=';
            var bytes = Uint8Array.from(atob(part), function (c) { return c.charCodeAt(0); });
            var payload = JSON.parse(new TextDecoder('utf-8').decode(bytes));
            return payload.sub || 'anonymous';
        } catch (e) { return 'anonymous'; }
    }

    // 当前用户的项目持久化 key（同浏览器多账号互不串项目）
    function _projectKey() { return 'agent_project_id:' + _umUsername(); }

    // 新建项目 ID：UUID 优先（防两用户同一毫秒新建碰撞出同一 thread_id 合并历史）
    function _newProjectId() {
        return (window.crypto && crypto.randomUUID)
            ? crypto.randomUUID()
            : Date.now() + '-' + Math.random().toString(36).slice(2);
    }

    function _isAgentUrl(url) {
        if (!url) return false;
        if (AGENT_BASE) return url.indexOf(AGENT_BASE) === 0;
        return /^\/(api|kb|agent)/.test(url) || /:800[234]\//.test(url);
    }

    function _showAuthError() {
        var box = document.getElementById('agentAuthError');
        if (!box) {
            box = document.createElement('div');
            box.id = 'agentAuthError';
            box.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;'
                + 'background:#c62828;color:#fff;padding:10px 16px;font-size:14px;'
                + 'text-align:center;';
            box.textContent = '登录状态无效或已过期：请保存当前内容，重新登录体系管理系统后再试';
            (document.body || document.documentElement).appendChild(box);
        }
    }

    // fetch 包装：agent 服务请求自动携带 Authorization（CORS 已放行该头）；
    // 401 → 顶部横幅提示（不静默失败）。注意 _rawFetch 必须 bind(window)——
    // 原生 fetch 对 this 敏感，绑定到其他对象会抛 Illegal invocation
    (function () {
        var _rawFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            var p;
            try {
                var url = (typeof input === 'string') ? input : ((input && input.url) || '');
                var t = _umToken();
                if (t && _isAgentUrl(url)) {
                    init = Object.assign({}, init || {});
                    if (init.headers instanceof Headers) {
                        init.headers = new Headers(init.headers);
                        init.headers.set('Authorization', 'Bearer ' + t);
                    } else {
                        init.headers = Object.assign({}, init.headers || {},
                            { 'Authorization': 'Bearer ' + t });
                    }
                }
            } catch (e) { /* 注入失败按原样请求 */ }
            p = _rawFetch(input, init);
            p.then(function (r) { if (r && r.status === 401) _showAuthError(); },
                   function () { /* 网络错误由调用方处理 */ });
            return p;
        };
    })();

    // 页面跳转（review/kb 新标签页）：凭证经 URL #jwt= 片段中转（fragment 不发给
    // 服务器、不进服务端日志），页内 token-relay.js 读取后转存 sessionStorage 并清 hash
    function _agentPageUrl(u) {
        var t = _umToken();
        return t ? (u + '#jwt=' + encodeURIComponent(t)) : u;
    }

    // 认证下载：window.open 无法携带请求头，改为 fetch(带 token) → blob → a.click
    // （文件名优先取 Content-Disposition，回退 URL 末段）
    function _agentDownload(url) {
        var opts = {};
        var t = _umToken();
        if (t) opts.headers = { 'Authorization': 'Bearer ' + t };
        return window.fetch(url, opts).then(function (r) {
            if (!r.ok) {
                if (r.status === 401) _showAuthError();
                throw new Error('HTTP ' + r.status);
            }
            var cd = r.headers.get('Content-Disposition') || '';
            var m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
            var name = m ? decodeURIComponent(m[1].replace(/"/g, ''))
                : (url.split('/').pop().split('?')[0] || 'download');
            return r.blob().then(function (b) {
                var a = document.createElement('a');
                a.href = URL.createObjectURL(b);
                a.download = name;
                document.body.appendChild(a);
                a.click();
                setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
            });
        }).catch(function (e) {
            alert('下载失败：' + (e && e.message ? e.message : e));
        });
    }

'''

    exports = '\n'.join('    window.%s = %s;' % (n, n) for n in to_export)
    footer = '''
    // ── 内联事件处理器导出（自动生成）──
    // agent HTML（静态 + JS 动态生成）使用 onclick="fn()" 原生全局解析，
    // IIFE 内必须显式挂到 window。清单 = 内联引用 ∩ JS 函数声明。
%s

    // ── 对外接口（SPA 调用）──
    window.AgentChat = {
        /** 激活视图：解析服务地址 → 首次初始化。幂等；force=true 重新探测端口。 */
        activate: function (force) {
            resolveAgentBase(force).then((base) => {
                const errBox = document.getElementById('agentServiceError');
                if (!base) {
                    if (errBox) errBox.style.display = 'block';
                    return;
                }
                if (errBox) errBox.style.display = 'none';
                ensureMermaid().catch((e) => console.warn('[AgentChat] mermaid 懒加载失败（流程图功能不可用）:', e));
                _doInit();
            }).catch((e) => {
                console.error('[AgentChat] activate failed:', e);
                const errBox = document.getElementById('agentServiceError');
                if (errBox) errBox.style.display = 'block';
            });
        },
        /** 登出时中断进行中的流与定时器（菜单切换不调用——等价原页面切标签页，流在后台继续） */
        deactivate: function () {
            try { if (currentAbortController) currentAbortController.abort(); } catch (e) { /* ignore */ }
            try { resetTypewriter(); } catch (e) { /* ignore */ }
            try { resetChatReasoning(); } catch (e) { /* ignore */ }
            isStreaming = false;
        },
        /** 全屏模式返回 UM 系统：点击 UM 侧边栏第一个非 agent 菜单项（触发 handleMenuSelect
            切走 activeMenu，v-show 隐藏全屏层；进行中的流按设计继续在后台） */
        backToSystem: function () {
            const items = document.querySelectorAll('.el-menu-item');
            for (const it of items) {
                if (it.textContent.indexOf('AI 文档写作') === -1) { it.click(); return; }
            }
        }
    };
})();
''' % exports

    return header + js + footer, rep_counts


def main():
    to_export, missing, n_handlers = discover_inline_handlers()
    if missing:
        print('FATAL: inline handlers reference undeclared functions: %s' % missing)
        sys.exit(1)

    css, keyframes, shared = transform_css()
    frag = transform_body()
    js, rep_counts = build_js(to_export)

    # ┐ 审计断言（剥离行注释后检查，避免 [PORT] 说明文字误报）
    js_nocomment = re.sub(r'//[^\n]*', '', js)
    assert 'existingProject' not in js_nocomment, 'existingProject leftover'
    assert 'urlParams' not in js_nocomment, 'urlParams leftover'
    assert 'history.replaceState' not in js_nocomment, 'replaceState leftover'
    # [PORT-AUTH] 审计：用户隔离相关变换必须全部生效（源头漂移时构建即失败）
    assert "'project_' + Date.now()" not in js, 'project id collision guard missing'
    assert "localStorage.getItem('agent_project_id')" not in js, 'per-user project key missing'
    assert "localStorage.setItem('agent_project_id'" not in js, 'per-user project key (write) missing'
    assert not re.search(r"window\.open\([^)]*download", js), 'unauthenticated window.open download leftover'
    assert "_agentPageUrl(AGENT_BASE + '/agent/review/'" in js, 'review page jwt relay missing'
    assert "_agentPageUrl(AGENT_BASE + '/kb" in js, 'kb page jwt relay missing'
    # 顶层副作用残留审计：不允许顶层 IIFE / 顶层 DOM 立即绑定（登录前 DOM 不存在）
    assert not re.search(r'^        \(', js, re.M), 'top-level IIFE leftover'
    assert not re.search(r'^        document\.getElementById\([\'"]\w+[\'"]\)\.(addEventListener|textContent|href|style)', js, re.M), 'top-level DOM binding leftover'
    assert not re.search(r'^        window\.(location|addEventListener)', js, re.M), 'top-level window op leftover'
    for name in to_export:
        assert ('window.%s = %s;' % (name, name)) in js
    unprefixed = [l.strip()[:120] for l in js.split('\n')
                  if re.search(r"(fetch|open)\(\s*['\"`]/(api|kb|agent)", l)]
    locs = [l.strip()[:120] for l in js.split('\n')
            if 'location.href' in l or 'location.pathname' in l]
    # ┘

    for p in (OUT_CSS, OUT_JS, OUT_FRAG):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(OUT_CSS, 'w', encoding='utf-8') as f:
        f.write(css)
    with io.open(OUT_JS, 'w', encoding='utf-8') as f:
        f.write(js)
    with io.open(OUT_FRAG, 'w', encoding='utf-8') as f:
        f.write(frag)

    # [PORT] cache-busting：index.html 对生成产物的引用附加内容哈希版本号，
    # 产物一变 URL 即变，浏览器不再持有旧 CSS/JS（2026-09-20 连续三次缓存事故后引入）
    import hashlib as _hl
    with io.open(INDEX_HTML, 'r', encoding='utf-8') as f:
        idx = f.read()
    for attr, path, out_path in [
        ('href', 'css/agent-chat.css', OUT_CSS),
        ('src', 'js/agent-chat.js', OUT_JS),
    ]:
        with open(out_path, 'rb') as f:
            v = _hl.md5(f.read()).hexdigest()[:10]
        pat = re.compile(r'(%s="%s)(\?v=[0-9a-f]+)?(")' % (attr, re.escape(path)))
        idx, n_sub = pat.subn(lambda m: m.group(1) + '?v=' + v + m.group(3), idx)
        assert n_sub >= 1, 'cache-bust target not found: %s' % path
        print('cache-bust: %s?v=%s (%d 处)' % (path, v, n_sub))
    with io.open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(idx)

    print('=== build_agent_port OK ===')
    print('css: %d lines; keyframes renamed: %s' % (css.count('\n'), sorted(keyframes.values())))
    print('shared classes (UM & agent): %s' % ', '.join(shared))
    print('leak guards emitted: %d' % css.count('UM-only-props guard'))
    print('js: %d lines; fragment: %d lines' % (js.count('\n'), frag.count('\n')))
    print('inline handler attrs scanned: %d; functions exported: %d' % (n_handlers, len(to_export)))
    print('exported:', ', '.join(to_export))
    print('replace counts: %s' % rep_counts)
    print('unprefixed url lines (expect 0): %d' % len(unprefixed))
    for l in unprefixed:
        print('  LEFTOVER:', l)
    print('location.href/pathname lines (expect 0): %d' % len(locs))
    for l in locs:
        print('  LOC:', l)


import sys  # noqa: E402  (main 中 sys.exit 需要)

if __name__ == '__main__':
    main()
