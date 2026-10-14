# -*- coding: utf-8 -*-
"""
build_review_port.py — 将文档审核 Agent 的 agent.html 忠实移植为体系文档管理系统
SPA 的嵌入视图（模式对齐 build_agent_port.py / 「AI 文档写作」）。

输入（只读源）:
  ../documents_review_local_model/frontend/agent.html
  ../user_management/frontend/css/style.css        (仅读取选择器，用于泄漏防护)

输出:
  ../user_management/frontend/css/agent-review.css     (命名空间化 + 防泄漏守卫)
  ../user_management/frontend/js/agent-review.js       (IIFE 封装 + 内联处理器导出)
  ../user_management/frontend/agent-review-fragment.html (待插入 index.html 的视图片段)

变换规则（全部机械化，可审计，可重复运行）:
  CSS: 选择器限定 #ar-root（:root/body/html → #ar-root）；@keyframes 改名 ar-*；
       body 的 min-height:100vh → height:100%；与 UM style.css 类名交集的
       UM 独有属性发射 unset 守卫
  HTML: 包进 v-show 视图容器 + #ar-root[v-pre]（Vue 跳过编译，onclick 原生全局解析）；
       全部 DOM id 加 ar- 前缀（fileInput/sendBtn 等与写作 agent 视图冲突）；
       移除「经典模式 / Agent 模式」导航链接，注入「⟵ 返回系统」按钮
  JS:  IIFE（非严格模式）+ window 导出内联 handler；REVIEW_BASE 端口探测
       (8012→8014，对齐 run.py 回退)；全部 /api 地址加 REVIEW_BASE 前缀；
       顶层 DOM 绑定 → _bindDom()（登录前 v-if 分支未渲染，DOM 不存在）；
       脚本尾 startConversation() → activate() 首次触发
  AUTH（用户隔离，combination 新增）：
       fetch 包装注入 Authorization: Bearer <UM JWT>（token 读 localStorage['token']）；
       401 → 顶部横幅提示重登；session_id 生成改 UUID（防跨用户毫秒级碰撞）；
       EventSource → fetch 流式 reader（EventSource 无法携带 Authorization 头，
       服务端 SSE 端点已挂 require_session_access 依赖，必须带头发请求）
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(
    HERE, '..', 'documents_review_local_model', 'frontend', 'agent.html'))
UM_CSS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'css', 'style.css'))
OUT_CSS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'css', 'agent-review.css'))
OUT_JS = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'js', 'agent-review.js'))
OUT_FRAG = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'agent-review-fragment.html'))
INDEX_HTML = os.path.normpath(os.path.join(
    HERE, '..', 'user_management', 'frontend', 'index.html'))

with io.open(SRC, 'r', encoding='utf-8') as f:
    FULL = f.read()
    lines = FULL.splitlines(keepends=True)

with io.open(UM_CSS, 'r', encoding='utf-8') as f:
    UM_CSS_TEXT = f.read()

# ── 源文件区段边界：按标记自动定位（行数无关，源文件演变免重算）──


def _find_line(text_lines, marker, start=0):
    for i in range(start, len(text_lines)):
        if text_lines[i].strip() == marker:
            return i
    raise AssertionError('section marker not found: %r' % marker)


_i_style = _find_line(lines, '<style>')
_i_stylee = _find_line(lines, '</style>', _i_style + 1)
_i_body = _find_line(lines, '<body>')
_i_js = _find_line(lines, '<script>', _i_body + 1)
_i_jse = _find_line(lines, '</script>', _i_js + 1)

CSS_TEXT = ''.join(lines[_i_style + 1:_i_stylee])          # <style> 内容
BODY = ''.join(lines[_i_body + 1:_i_js])                   # <body> 内 HTML
JS = ''.join(lines[_i_js + 1:_i_jse])                      # <script> 内容

# 原页全部 DOM id（HTML id= / label for= / JS getElementById / 内联 onclick 共用）
DOM_IDS = [
    'uploadZone', 'fileInput', 'fileInfo', 'fileName', 'fileSize',
    'startConvBtn', 'uploadOverlay', 'chatContainer', 'chatMessages',
    'inputArea', 'messageInput', 'sendBtn', 'progressBarWrap',
    'uploadDocBtn', 'auditType', 'agentMode', 'autoResumeCountdown',
    # P0 优化新增：历史会话列表弹层
    'historyBtn', 'sessionListOverlay', 'sessionListBody',
]

# ══════════════════════════════════════════════════════════════
# 通用：极简 CSS 规则扫描器（顶层 + @media 递归）— 与 build_agent_port 同源
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
    # :root 变量声明迁到 #ar-root：视口级变量改为 wrapper 级（覆盖 UM :root 泄漏）
    if sel in (':root', 'body', 'html'):
        return '#ar-root'
    if sel == '*':
        return '#ar-root, #ar-root *'
    return '#ar-root ' + sel


def _scope_rules(css_text: str, keyframe_names: dict) -> str:
    out = []
    i, n = 0, len(css_text)
    while i < n:
        # 注意：re.match 作用于切片 css_text[i:]，end() 是切片内偏移，
        # 必须 i += end()——直接 i = end() 会回跳到文件头造成死循环
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
            new_name = 'ar-' + name
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
    """SPA style.css → agent 视图 的样式泄漏防护（同 build_agent_port 算法）。"""
    um_class_props = {}
    for head, body in iter_rules(UM_CSS_TEXT):
        for m in re.finditer(r'\.([A-Za-z_][\w-]*)', head):
            um_class_props.setdefault('.' + m.group(1), set()).update(props_of(body))

    ag_class_props = {}
    for head, body in iter_rules(CSS_TEXT):
        for m in re.finditer(r'\.([A-Za-z_][\w-]*)', head):
            ag_class_props.setdefault('.' + m.group(1), set()).update(props_of(body))

    shared = sorted(set(um_class_props) & set(ag_class_props))
    guard_rules = []
    for cls in shared:
        um_only = sorted(um_class_props[cls] - ag_class_props[cls])
        if um_only:
            decls = '\n    '.join('%s: unset;' % p for p in um_only)
            guard_rules.append('#ar-root %s {\n    /* UM-only-props guard */\n    %s\n}' % (cls, decls))
    return shared, guard_rules


def transform_css():
    keyframe_names = {}
    scoped = _scope_rules(CSS_TEXT, keyframe_names)

    # body 规则映射为 #ar-root 后：全屏浮层内取整高度（flex 布局依赖父高度确定）
    scoped = re.sub(r'(#ar-root \{[^}]*?)min-height: 100vh;',
                    r'\1height: 100%;\n    min-height: 0;', scoped, count=1)

    for old, new in keyframe_names.items():
        scoped = re.sub(r'animation:\s*%s\b' % re.escape(old), 'animation: %s' % new, scoped)
        scoped = re.sub(r'animation-name:\s*%s\b' % re.escape(old), 'animation-name: %s' % new, scoped)

    shared, guards = compute_leak_guards()

    header = (
        '/*\n'
        ' * agent-review.css — 由审核 agent.html 提取并命名空间化（#ar-root）\n'
        ' * 生成脚本: combination/tools/build_review_port.py（勿手改，重跑脚本覆盖）\n'
        ' * 类名交集（UM↔agent-review）: %s\n'
        ' */\n\n'
        '/* 全屏浮层：审核视图覆盖整个视口（含 UM 头部与侧边栏），还原原独立页体验。\n'
        '   v-show 关闭时 display:none，不参与布局；z-index 与写作 agent 浮层同层\n'
        '   （两视图互斥呈现，不叠加）；内部 upload-overlay z-index:100 在本层叠\n'
        '   上下文内不受影响 */\n'
        '.agent-review-page {\n'
        '    position: fixed; top: 0; left: 0; right: 0; bottom: 0;\n'
        '    z-index: 1800;\n'
        '    overflow: hidden;\n'
        '}\n\n'
        '/* 全屏模式返回按钮（注入 header .nav 首项，随导航栏流动）*/\n'
        '#ar-root .ar-back-btn {\n'
        '    background: #455a64; color: #fff; border: none; border-radius: 6px;\n'
        '    padding: 6px 14px; font-size: 13px; cursor: pointer; font-weight: 600;\n'
        '}\n'
        '#ar-root .ar-back-btn:hover { background: #37474f; }\n\n'
        '/* 审核服务不可用提示横幅 */\n'
        '#ar-root .ar-service-error {\n'
        '    margin: 16px auto; max-width: 560px; padding: 14px 18px;\n'
        '    background: #ffebee; color: #c62828; border: 1px solid #ef9a9a;\n'
        '    border-radius: 8px; font-size: 13px; line-height: 1.7; text-align: center;\n'
        '}\n'
        '#ar-root .ar-service-error button {\n'
        '    margin-top: 8px; padding: 4px 14px; background: #c62828; color: #fff;\n'
        '    border: none; border-radius: 6px; cursor: pointer; font-size: 12px;\n'
        '}\n\n'
    ) % (', '.join(shared) or '(无)')

    guard_block = ''
    if guards:
        guard_block = ('\n/* ══ SPA 样式泄漏防护（自动生成，误删会导致 UM 属性渗入审核视图）══ */\n'
                       + '\n\n'.join(guards) + '\n')

    return header + scoped + guard_block, keyframe_names, shared


# ══════════════════════════════════════════════════════════════
# HTML 片段：v-show 视图容器 + #ar-root[v-pre] + id 前缀 + 错误横幅
# ══════════════════════════════════════════════════════════════

def transform_body():
    body = BODY

    # 1) 导航链接处置：经典模式(/)与 Agent 模式(/agent) 链接在 SPA 内会跳到 :3000
    #    根路径——移除；nav 首部注入「返回系统」按钮（对齐写作 agent 的做法）
    for a in ('    <a href="/">经典模式</a>\n',
              '    <a href="/agent" class="active">Agent 模式</a>\n'):
        assert a in body, 'nav link not found: %r' % a[:40]
        body = body.replace(a, '')
    nav_anchor = '<div class="nav">'
    assert body.count(nav_anchor) == 1, 'nav anchor not unique'
    body = body.replace(
        nav_anchor,
        nav_anchor + '\n'
        '    <button class="ar-back-btn" onclick="AgentReview.backToSystem()"'
        ' title="返回体系文档管理系统">⟵ 返回系统</button>', 1)

    # 2) DOM id 前缀化（HTML id= / label for= / 内联 onclick 里的 getElementById）
    for x in DOM_IDS:
        body = body.replace('id="%s"' % x, 'id="ar-%s"' % x)
        body = body.replace('for="%s"' % x, 'for="ar-%s"' % x)
        body = body.replace("getElementById('%s')" % x, "getElementById('ar-%s')" % x)
        body = body.replace('getElementById("%s")' % x, 'getElementById("ar-%s")' % x)

    banner = (
        '\n        <!-- 审核服务不可用横幅（由 agent-review.js 控制） -->\n'
        '        <div class="ar-service-error" id="arServiceError" style="display:none">\n'
        '            <div>⚠ 无法连接文档审核 Agent 服务（已尝试端口 8012 / 8013 / 8014）。</div>\n'
        '            <div style="font-size:12px;color:#b71c1c;margin-top:4px">请确认审核服务已启动（见 combination/README.md），然后重试。</div>\n'
        '            <button onclick="AgentReview.activate(true)">重试连接</button>\n'
        '        </div>\n'
    )
    # v-pre: Vue 编译器跳过整个子树 —— 内联 onclick 保持原生全局解析（window.fn 导出），
    # 原生 JS 的 DOM 修改不会被 Vue 补丁触碰
    return ('<div v-show="activeMenu === \'agent-review\'" class="agent-review-page">\n'
            '<div id="ar-root" v-pre>\n'
            + banner + body +
            '\n</div>\n</div>\n')


# ══════════════════════════════════════════════════════════════
# 内联事件处理器发现
# ══════════════════════════════════════════════════════════════

JS_BUILTINS = {
    'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'new',
    'confirm', 'alert', 'prompt', 'parseInt', 'parseFloat', 'isNaN',
    'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'setInterval',
    'clearTimeout', 'clearInterval', 'fetch', 'String', 'Number', 'Boolean',
    'Array', 'Object', 'Date', 'Math', 'JSON', 'Promise', 'RegExp', 'Error',
    'event', 'stopPropagation', 'preventDefault', 'AgentReview',
    'document', 'getElementById', 'click',
}


def discover_inline_handlers():
    """扫描全文（含 JS 动态生成）中 onXXX="code" 引用的函数名，
    与 JS 函数声明求交 → 必须导出到 window 的函数清单。"""
    codes = []
    for m in re.finditer(r'on(?:click|change|input|submit|keydown|keyup|keypress|load|error|focus|blur|mouseover|mouseout|mousedown|mouseup)\s*=\s*"([^"]*)"', FULL):
        codes.append(m.group(1))
    for m in re.finditer(r"on(?:click|change|input|submit|keydown|keyup|keypress|load|error|focus|blur|mouseover|mouseout|mousedown|mouseup)\s*=\s*'([^']*)'", FULL):
        codes.append(m.group(1))

    names = set()
    for code in codes:
        for m in re.finditer(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(', code):
            names.add(m.group(1))

    declared = set(re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(', JS))
    to_export = sorted(names & declared)
    missing = sorted(n for n in names - declared if n not in JS_BUILTINS)
    return to_export, missing, len(codes)


# [PORT-GLOBAL] 全局函数名冲突规避（对齐 DOM id 加 ar- 前缀的做法）：
# agent-review.js 在 index.html 中晚于 agent-chat.js 加载，二者 IIFE 都向
# window 导出内联 handler 用函数；sendMessage / handleFileSelect 重名时审核侧
# 覆盖写作侧，写作页发消息会调到审核侧未初始化的 messageInput 而崩溃。
# 导出名加 ar 前缀，视图片段内联属性同步改写；JS 内部调用走词法作用域不受影响。
GLOBAL_RENAME = {
    'sendMessage': 'arSendMessage',
    'handleFileSelect': 'arHandleFileSelect',
}


def _rename_colliding_handlers(frag):
    """视图片段 onXXX="..." 属性值内的冲突函数名改写为 ar 前缀全局名。"""
    def fix_attr(m):
        inner = re.sub(r'\b(sendMessage|handleFileSelect)\b',
                       lambda n: GLOBAL_RENAME[n.group(0)], m.group(2))
        return m.group(1) + inner + m.group(3)
    pat = re.compile(
        r'(on(?:click|change|input|submit|keydown|keyup|keypress|load|error'
        r'|focus|blur|mouseover|mouseout|mousedown|mouseup)\s*=\s*")([^"]*)(")')
    return pat.sub(fix_attr, frag)


# ══════════════════════════════════════════════════════════════
# JS 变换
# ══════════════════════════════════════════════════════════════

OLD_STATE = '''let selectedFile = null;
let sessionId = null;
let eventSource = null;
let isAwaitingInput = false;'''

NEW_STATE = '''let selectedFile = null;
let sessionId = null;
// [PORT-AUTH] 原为 EventSource；无法携带 Authorization 头 → fetch 流式 reader
// （sseController 控制断开，sseAlive 标记连接存活性，对齐原 readyState 语义）
let sseController = null;
let sseAlive = false;
let isAwaitingInput = false;'''

OLD_DOM = '''// DOM elements
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const startConvBtn = document.getElementById('startConvBtn');
const uploadOverlay = document.getElementById('uploadOverlay');
const chatMessages = document.getElementById('chatMessages');
const inputArea = document.getElementById('inputArea');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const progressBarWrap = document.getElementById('progressBarWrap');

// File handling
uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});'''

NEW_DOM = '''// DOM elements（[PORT] 原为顶层 const 立即取值 + 顶层事件绑定；SPA 登录前
// v-if 分支未渲染 DOM 不存在 → let 延迟到 _bindDom() 绑定，由 _doInit 调用）
let uploadZone, fileInput, fileInfo, startConvBtn, uploadOverlay,
    chatMessages, inputArea, messageInput, sendBtn, progressBarWrap;

function _bindDom() {
  uploadZone = document.getElementById('ar-uploadZone');
  fileInput = document.getElementById('ar-fileInput');
  fileInfo = document.getElementById('ar-fileInfo');
  startConvBtn = document.getElementById('ar-startConvBtn');
  uploadOverlay = document.getElementById('ar-uploadOverlay');
  chatMessages = document.getElementById('ar-chatMessages');
  inputArea = document.getElementById('ar-inputArea');
  messageInput = document.getElementById('ar-messageInput');
  sendBtn = document.getElementById('ar-sendBtn');
  progressBarWrap = document.getElementById('ar-progressBarWrap');

  // File handling
  uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
  uploadZone.addEventListener('drop', e => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
}'''

OLD_SSE = '''// SSE connection（P0 优化：seq 游标 — 断线重连/恢复后用 from_seq 补齐漏收事件）
function connectSSE(replayAll = false) {
  if (eventSource) { eventSource.close(); }
  if (sseReconnectTimer) { clearTimeout(sseReconnectTimer); sseReconnectTimer = null; }

  // replayAll=true：刚 restore 的新事件通道从 0 全量重放（checkpoint/complete 等）
  // lastSeq>0：断线重连，从上次收到的位置续传；新会话（lastSeq=0）仅推新事件
  const qs = replayAll ? '?from_seq=0' : (lastSeq > 0 ? `?from_seq=${lastSeq}` : '');
  const url = `${apiBase()}/conversation/stream/${sessionId}${qs}`;
  eventSource = new EventSource(url);

  eventSource.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      if (event.seq && event.seq > lastSeq) lastSeq = event.seq;
      handleSSEEvent(event);
    } catch (err) {
      console.error('SSE parse error:', err);
    }
  };

  eventSource.onerror = () => {
    console.warn('SSE connection lost, probing session state before reconnect...');
    eventSource.close();
    if (sessionFinished) return;  // 已完成的会话无需重连
    sseReconnectTimer = setTimeout(reconnectWithProbe, 2000);
  };
}'''

NEW_SSE = '''// SSE connection（[PORT-AUTH] 原为 EventSource——无法携带 Authorization 头，
// 服务端流端点已挂 require_session_access 鉴权 → 改 fetch 流式读取。
// P0 优化同步：seq 游标 from_seq 续传 / restore 全量重放 / 完成会话不重连 /
// 断线先探测会话状态再决定 restore 或续连）
function connectSSE(replayAll = false) {
  if (sseController) { try { sseController.abort(); } catch (e) {} }
  if (sseReconnectTimer) { clearTimeout(sseReconnectTimer); sseReconnectTimer = null; }
  sseAlive = false;
  const qs = replayAll ? '?from_seq=0' : (lastSeq > 0 ? `?from_seq=${lastSeq}` : '');
  const url = `${apiBase()}/conversation/stream/${sessionId}${qs}`;
  sseController = new AbortController();
  const ctl = sseController;
  const _fail = () => {
    if (sseController === ctl) sseController = null;
    sseAlive = false;
    if (sessionFinished) return;  // 已完成的会话无需重连
    console.warn('SSE connection lost, probing session state before reconnect...');
    sseReconnectTimer = setTimeout(reconnectWithProbe, 2000);
  };
  fetch(url, { signal: ctl.signal }).then(resp => {
    if (!resp.ok || !resp.body) throw new Error('SSE HTTP ' + resp.status);
    sseAlive = true;
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    const _pump = () => reader.read().then(({ done, value }) => {
      if (done) { _fail(); return; }
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\\n\\n')) !== -1) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of chunk.split('\\n')) {
          if (line.startsWith('data:')) {
            try {
              const event = JSON.parse(line.slice(5).trim());
              if (event.seq && event.seq > lastSeq) lastSeq = event.seq;
              handleSSEEvent(event);
            } catch (err) {
              console.error('SSE parse error:', err);
            }
          }
        }
      }
      return _pump();
    });
    return _pump();
  }).catch(err => {
    if (err && err.name === 'AbortError') return;
    _fail();
  });
}'''

OLD_TAIL = '''// 页面加载：优先恢复上次会话（P0 优化 — 刷新/服务重启后不丢上下文），
// 无可恢复会话时新建自由对话；可随时点「📄 上传文档审核」进入结构化审核
async function initPage() {
  const saved = loadSavedSession();
  if (saved && saved.sessionId && await tryRestoreSession(saved)) return;
  startConversation();
}
initPage();'''

NEW_TAIL = '''// 页面加载：优先恢复上次会话（P0 优化 — 刷新/服务重启后不丢上下文），
// 无可恢复会话时新建自由对话；可随时点「📄 上传文档审核」进入结构化审核
async function initPage() {
  const saved = loadSavedSession();
  if (saved && saved.sessionId && await tryRestoreSession(saved)) return;
  startConversation();
}
// ── Init（[PORT] 原为脚本尾顶层立即调用；改为 activate() 首次触发，一次性执行。
// 后续菜单切换不重跑——v-show 视图与页面共存亡，等价于原页面持续打开。
// 注意：initPage 定义必须保留在产物内——_doInit 调用它，旧版 NEW_TAIL 曾把
// 定义随顶层调用一起删掉，导致 activate 抛 ReferenceError、视图卡占位符）──
let _inited = false;
function _doInit() {
  if (_inited) return;
  _inited = true;
  _bindDom();
  initPage();
}'''


def transform_js():
    js = JS
    rep_counts = {}

    def rep(old, new, key):
        assert old in js, 'pattern not found: %s' % key
        rep_counts[key] = js.count(old)
        return js.replace(old, new)

    # 0) 状态声明：EventSource → fetch reader 变量
    js = rep(OLD_STATE, NEW_STATE, 'state_block')

    # 1) 顶层 DOM 绑定 → _bindDom()（含拖拽事件）
    js = rep(OLD_DOM, NEW_DOM, 'dom_block')

    # 2) API 地址前缀（apiBase 是全部会话端点的唯一出口；另有两处局部 base 与导出）
    js = rep("function apiBase() { return agentMode === 'multi' ? '/api/multi-agent' : '/api/agent'; }",
             "function apiBase() { return agentMode === 'multi' ? REVIEW_BASE + '/api/multi-agent'"
             " : REVIEW_BASE + '/api/agent'; }",
             'api_base')
    js = rep("      const rptBase = agentMode === 'multi' ? '/api/multi-agent' : '/api/agent';",
             "      const rptBase = agentMode === 'multi' ? REVIEW_BASE + '/api/multi-agent'"
             " : REVIEW_BASE + '/api/agent';",
             'rpt_base')
    js = rep("    const msgBase = agentMode === 'multi' ? '/api/multi-agent' : '/api/agent';",
             "    const msgBase = agentMode === 'multi' ? REVIEW_BASE + '/api/multi-agent'"
             " : REVIEW_BASE + '/api/agent';",
             'msg_base')
    js = rep("    const resp = await fetch('/api/export-review', {",
             "    const resp = await fetch(REVIEW_BASE + '/api/export-review', {",
             'export_fetch')
    # P0 优化新增：会话列表/删除端点前缀（/api/sessions 不含 conversation 关键字）
    js = rep("    const r = await fetch('/api/sessions');",
             "    const r = await fetch(REVIEW_BASE + '/api/sessions');",
             'sessions_fetch')
    js = rep("    const r = await fetch(`/api/sessions/${sid}`, { method: 'DELETE' });",
             "    const r = await fetch(REVIEW_BASE + `/api/sessions/${sid}`, { method: 'DELETE' });",
             'sessions_delete_fetch')

    # 3) [PORT-AUTH] session_id 生成：UUID 防跨用户毫秒级碰撞
    js = rep("  formData.append('session_id', 'conv-' + Date.now());",
             "  formData.append('session_id', 'conv-' + _newSessionId());",
             'session_uuid')

    # 4) SSE：EventSource → fetch reader
    js = rep(OLD_SSE, NEW_SSE, 'sse_connect')
    js = rep('  if (eventSource) { eventSource.close(); eventSource = null; }',
             '  if (sseController) { try { sseController.abort(); } catch (e) {} sseController = null; }\n'
             '  sseAlive = false;',
             'sse_close_return')
    js = rep('''    if (eventSource && eventSource.readyState === EventSource.CLOSED) {
      console.warn('SSE unexpectedly closed, reconnecting...');
      connectSSE();
    }''',
             '''    if (!sseAlive && sessionId) {
      console.warn('SSE unexpectedly closed, reconnecting...');
      connectSSE();
    }''',
             'sse_check_message')
    js = rep('  if (eventSource) eventSource.close();',
             '  if (sseController) { try { sseController.abort(); } catch (e) {} sseController = null; }\n'
             '  sseAlive = false;',
             'sse_close_complete')

    # 5) 脚本尾顶层调用 → _doInit()
    js = rep(OLD_TAIL, NEW_TAIL, 'tail_init')

    # 6) getElementById 的 id 前缀化（覆盖 JS 内全部引用 + HTML 内联 onclick）；
    #    另含 JS 动态建元素的 .id 赋值（如 showAutoResumeCountdown 的
    #    cd.id='autoResumeCountdown'，创建与查找必须同步前缀否则失配）
    for x in DOM_IDS:
        js = js.replace("getElementById('%s')" % x, "getElementById('ar-%s')" % x)
        js = js.replace(".id = '%s';" % x, ".id = 'ar-%s';" % x)

    return js, rep_counts


def build_js(to_export):
    js, rep_counts = transform_js()

    header = '''/*
 * agent-review.js — 由审核 agent.html 的内联 <script> 忠实移植（构建脚本生成，勿手改）
 * 生成脚本: combination/tools/build_review_port.py
 *
 * 相对原文的改动（全部为嵌入 SPA 所必需，对话/审核逻辑零重写）:
 *  1. IIFE 封装（非严格模式，保持原文语义）；内联事件处理器全部导出到 window
 *  2. REVIEW_BASE 运行时解析：依次健康探测 :8012/:8013/:8014（对齐 run.py 端口回退）
 *  3. 全部 /api/** 地址加 REVIEW_BASE 前缀（跨源 CORS）
 *  4. 顶层 DOM 取值/绑定 → _bindDom()（登录前 v-if 分支未渲染，DOM 不存在）
 *  5. 初始化改为 activate() 首次惰性触发；登出 deactivate() 中断 SSE 与倒计时
 *  6. [PORT-AUTH] 用户隔离：fetch 包装自动携带 Authorization: Bearer <UM JWT>；
 *     session_id 用 UUID 防跨用户碰撞；EventSource → fetch 流式 reader（SSE 带鉴权头）
 */
(function () {

    // ── 审核服务地址解析（健康探测，缓存；探测目的=找端口，不代表 Ollama 就绪）──
    let REVIEW_BASE = '';
    let _baseProbing = null;

    function resolveReviewBase(force) {
        if (REVIEW_BASE && !force) return Promise.resolve(REVIEW_BASE);
        if (_baseProbing) return _baseProbing;
        _baseProbing = (async () => {
            for (const port of [8012, 8013, 8014]) {
                const base = window.location.protocol + '//' + window.location.hostname + ':' + port;
                try {
                    const r = await fetch(base + '/health', { method: 'GET' });
                    if (r.ok) { REVIEW_BASE = base; return base; }
                } catch (e) { /* 端口不通，试下一个 */ }
            }
            return null;
        })();
        var p = _baseProbing;
        p.then(function () { _baseProbing = null; }, function () { _baseProbing = null; });
        return p;
    }

    // ── [PORT-AUTH] 用户隔离（combination 新增）──
    // 体系管理系统登录后 JWT 存于 localStorage['token']（:3000 源）；审核服务以
    // 共享密钥验签（HS256），会话归属按用户名（sub claim）隔离。

    function _umToken() {
        try { return localStorage.getItem('token') || ''; } catch (e) { return ''; }
    }

    // 新建会话 ID：UUID 优先（防两用户同一毫秒新建碰撞出同一 session_id 抢注归属）
    function _newSessionId() {
        return (window.crypto && crypto.randomUUID)
            ? crypto.randomUUID()
            : Date.now() + '-' + Math.random().toString(36).slice(2);
    }

    function _isReviewUrl(url) {
        if (!url) return false;
        if (REVIEW_BASE) return url.indexOf(REVIEW_BASE) === 0;
        return /^\\/api\\//.test(url) || /:801[234]\\//.test(url);
    }

    function _showAuthError() {
        var box = document.getElementById('arAuthError');
        if (!box) {
            box = document.createElement('div');
            box.id = 'arAuthError';
            box.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;'
                + 'background:#c62828;color:#fff;padding:10px 16px;font-size:14px;'
                + 'text-align:center;';
            box.textContent = '登录状态无效或已过期：请保存当前内容，重新登录体系管理系统后再试';
            (document.body || document.documentElement).appendChild(box);
        }
    }

    // fetch 包装：审核服务请求自动携带 Authorization（CORS 已放行该头）；
    // 401 → 顶部横幅提示（不静默失败）。注意 _rawFetch 必须 bind(window)——
    // 原生 fetch 对 this 敏感，绑定到其他对象会抛 Illegal invocation
    (function () {
        var _rawFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            var p;
            try {
                var url = (typeof input === 'string') ? input : ((input && input.url) || '');
                var t = _umToken();
                if (t && _isReviewUrl(url)) {
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

'''

    exports = '\n'.join('    window.%s = %s;' % (GLOBAL_RENAME.get(n, n), n)
                        for n in to_export)
    footer = '''
    // ── 内联事件处理器导出（自动生成）──
    // 审核 HTML（静态 + JS 动态生成）使用 onclick="fn()" 原生全局解析，
    // IIFE 内必须显式挂到 window。清单 = 内联引用 ∩ JS 函数声明。
%s

    // ── 对外接口（SPA 调用）──
    window.AgentReview = {
        /** 激活视图：解析服务地址 → 首次初始化。幂等；force=true 重新探测端口。 */
        activate: function (force) {
            resolveReviewBase(force).then((base) => {
                const errBox = document.getElementById('arServiceError');
                if (!base) {
                    if (errBox) errBox.style.display = 'block';
                    return;
                }
                if (errBox) errBox.style.display = 'none';
                _doInit();
            }).catch((e) => {
                console.error('[AgentReview] activate failed:', e);
                const errBox = document.getElementById('arServiceError');
                if (errBox) errBox.style.display = 'block';
            });
        },
        /** 登出时中断进行中的 SSE 流与倒计时（菜单切换不调用——等价原页面切标签页） */
        deactivate: function () {
            try { if (sseController) sseController.abort(); } catch (e) { /* ignore */ }
            sseController = null;
            sseAlive = false;
            // P0 优化：取消待执行的探测式重连，避免登出后仍拉起 SSE
            try {
                if (sseReconnectTimer) { clearTimeout(sseReconnectTimer); sseReconnectTimer = null; }
            } catch (e) { /* ignore */ }
            try {
                if (autoResumeTimer) { clearInterval(autoResumeTimer); autoResumeTimer = null; }
            } catch (e) { /* ignore */ }
            try { removeAutoResumeCountdown(); } catch (e) { /* ignore */ }
            isAwaitingInput = false;
        },
        /** 全屏模式返回 UM 系统：点击 UM 侧边栏第一个非 agent 菜单项（触发
            handleMenuSelect 切走 activeMenu，v-show 隐藏全屏层） */
        backToSystem: function () {
            const items = document.querySelectorAll('.el-menu-item');
            for (const it of items) {
                if (it.textContent.indexOf('AI 文档') === -1) { it.click(); return; }
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
    frag = _rename_colliding_handlers(transform_body())
    js, rep_counts = build_js(to_export)

    # ┐ 审计断言（[PORT-AUTH] 相关变换必须全部生效，源头漂移时构建即失败）
    assert 'new EventSource' not in js, 'EventSource leftover (cannot carry auth header)'
    assert 'eventSource' not in js, 'eventSource variable leftover'
    assert "'conv-' + Date.now()" not in js, 'session id collision guard missing'
    unprefixed = [l.strip()[:120] for l in js.split('\n')
                  if re.search(r"fetch\(\s*['\"`]/api", l)]
    # 顶层副作用残留审计：不允许顶层立即执行的 DOM 取值/绑定/启动调用
    assert not re.search(r'^(const|let)\s+\w+\s*=\s*document\.getElementById', js, re.M), \
        'top-level DOM binding leftover'
    assert not re.search(r'^uploadZone\.addEventListener', js, re.M), 'top-level listener leftover'
    assert not re.search(r'^startConversation\(\);', js, re.M), 'top-level init leftover'
    for x in DOM_IDS:
        assert "getElementById('%s')" % x not in js, 'unprefixed id reference: %s' % x
        assert 'id="%s"' % x not in frag, 'unprefixed id in fragment: %s' % x
    assert frag.count('id="ar-root"') == 1, 'ar-root wrapper missing'
    # ┘

    for p in (OUT_CSS, OUT_JS, OUT_FRAG):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(OUT_CSS, 'w', encoding='utf-8') as f:
        f.write(css)
    with io.open(OUT_JS, 'w', encoding='utf-8') as f:
        f.write(js)
    with io.open(OUT_FRAG, 'w', encoding='utf-8') as f:
        f.write(frag)

    # [PORT] 先接线再 cache-bust：首次运行时 index.html 尚无产物引用，
    # wire 插入裸引用（css/js link、菜单项、视图片段）后才能附加哈希版本号
    import subprocess as _sp
    _r = _sp.run([sys.executable, os.path.join(HERE, 'wire_review_spa.py')],
                 capture_output=True, text=True, encoding='utf-8')
    assert _r.returncode == 0, 'wire_review_spa failed: %s' % (_r.stderr or 'no stderr')
    for l in (_r.stdout or '').splitlines():
        print('wire: %s' % l)

    # [PORT] cache-busting：index.html 对生成产物的引用附加内容哈希版本号
    import hashlib as _hl
    with io.open(INDEX_HTML, 'r', encoding='utf-8', newline='') as f:
        idx = f.read()
    for attr, path, out_path in [
        ('href', 'css/agent-review.css', OUT_CSS),
        ('src', 'js/agent-review.js', OUT_JS),
    ]:
        with open(out_path, 'rb') as f:
            v = _hl.md5(f.read()).hexdigest()[:10]
        pat = re.compile(r'(%s="%s)(\?v=[0-9a-f]+)?(")' % (attr, re.escape(path)))
        idx, n_sub = pat.subn(lambda m: m.group(1) + '?v=' + v + m.group(3), idx)
        assert n_sub >= 1, 'cache-bust target not found: %s' % path
        print('cache-bust: %s?v=%s (%d 处)' % (path, v, n_sub))
    with io.open(INDEX_HTML, 'w', encoding='utf-8', newline='') as f:
        f.write(idx)

    print('=== build_review_port OK ===')
    print('css: %d lines; keyframes renamed: %s' % (css.count('\n'), sorted(keyframes.values())))
    print('shared classes (UM & agent-review): %s' % ', '.join(shared))
    print('leak guards emitted: %d' % css.count('UM-only-props guard'))
    print('js: %d lines; fragment: %d lines' % (js.count('\n'), frag.count('\n')))
    print('inline handler attrs scanned: %d; functions exported: %d' % (n_handlers, len(to_export)))
    print('exported:', ', '.join(to_export))
    print('replace counts: %s' % rep_counts)
    print('unprefixed url lines (expect 0): %d' % len(unprefixed))
    for l in unprefixed:
        print('  LEFTOVER:', l)


if __name__ == '__main__':
    main()
