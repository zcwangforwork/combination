/*
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

        // ── State ──
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
        let isStreaming = false;
        let waitingApproval = null;
        let currentDocLabel = '文档';
        let currentDocType = '';
        // 风险分析总表类文档类型：支持导出 Excel
        const RISK_EXCEL_DOC_TYPES = ['product_risk_analysis_matrix', 'cybersecurity_risk_analysis_matrix'];
        // 文档语言风格选择（仅文档内容生成，不影响聊天回复）: 'detailed'=严谨详细 | 'concise'=精炼简洁（默认，字数约1万字收敛）
        let writingStyle = 'concise';
        // 当前 SSE 流的 AbortController，用于撤回消息时中止进行中的请求
        let currentAbortController = null;
        // 记录最近一次操作，供出错时引导「一键重试」
        let lastAction = null;        // 'send' | 'resume'
        let lastUserMessage = null;    // send 场景的最后一条用户消息
        let lastDecision = null;       // resume 场景的 HITL 决定

        // ── 对话思维链（chat_reasoning 事件 → 对话区折叠块）──
        let chatReasoningDiv = null;  // 对话区思维链容器

        // ── Agent 工作状态条：集中跟踪所有 SSE 事件，实时更新当前动作 ──
        // 任何时刻进入对话（含切任务/刷新重连回放）都能立即看到 agent 在做什么；
        // 文档生成完成（file_ready）时给显著提示（状态条 + 大 toast）
        let _statusHideTimer = null;
        let _lastStatusType = '';

        function setAgentStatus(text, spinning, tone) {
            const bar = document.getElementById('agentStatusBar');
            if (!bar) return;
            if (!text) { bar.style.display = 'none'; return; }
            document.getElementById('agentStatusText').textContent = text;
            const sp = document.getElementById('agentStatusSpinner');
            if (sp) sp.style.display = spinning ? '' : 'none';
            bar.className = 'agent-status-bar' + (tone ? ' ' + tone : '');
            bar.style.display = 'flex';
            if (_statusHideTimer) { clearTimeout(_statusHideTimer); _statusHideTimer = null; }
        }

        function _scheduleStatusHide(delayMs) {
            if (_statusHideTimer) clearTimeout(_statusHideTimer);
            _statusHideTimer = setTimeout(() => {
                const bar = document.getElementById('agentStatusBar');
                if (bar) bar.style.display = 'none';
            }, delayMs);
        }

        function trackAgentStatus(data) {
            if (!data || !data.type) return;
            const t = data.type;
            if (t === 'token' || t === 'chat_reasoning') {
                // 回复中：仅首次设置，避免每个 chunk 重绘
                if (_lastStatusType !== 'reply') {
                    _lastStatusType = 'reply';
                    setAgentStatus('💬 正在回复…', true);
                }
                return;
            }
            const prev = _lastStatusType;
            _lastStatusType = t;
            switch (t) {
                case 'tool_start':
                    setAgentStatus(`🔧 ${toolLabel(data.tool) || data.tool}执行中…`, true);
                    break;
                case 'subagent_start':
                    setAgentStatus(data.message || '正在处理…', true);
                    break;
                case 'subagent_complete':
                    setAgentStatus(`✅ ${data.message || '完成'}`, false, 'done');
                    break;
                case 'waiting_approval':
                    setAgentStatus('⏸ 等待你的确认（请在对话中点击 确认/修改/跳过）', false, 'warn');
                    break;
                case 'file_ready':
                    // 文档生成完成：显著提示（状态条绿色常驻较久 + 大 toast）
                    setAgentStatus(`📄 文档《${data.filename}》已生成完成，点击下载按钮获取`, false, 'done');
                    showToast(`🎉 文档《${data.filename}》已生成完成`, 'success', 8000);
                    _scheduleStatusHide(60000);
                    break;
                case 'sections_ready':
                    setAgentStatus('📝 章节已生成完成', false, 'done');
                    _scheduleStatusHide(10000);
                    break;
                case 'modified_doc_ready':
                    setAgentStatus(`📄 修改版《${data.filename}》已生成`, false, 'done');
                    _scheduleStatusHide(15000);
                    break;
                case 'done':
                    // 文档完成提示优先于通用完成语（done 在 file_ready 之后到达时不覆盖）
                    if (prev !== 'file_ready') {
                        setAgentStatus('✅ 本轮已完成', false, 'done');
                        _scheduleStatusHide(6000);
                    }
                    break;
                case 'error':
                    setAgentStatus(`⚠️ ${String(data.message || '出错了').slice(0, 80)}`, false, 'warn');
                    _scheduleStatusHide(15000);
                    break;
                case 'cancelled':
                    setAgentStatus('⏸ 已暂停生成', false, 'warn');
                    _scheduleStatusHide(8000);
                    break;
            }
        }

        // 对话区滚动节流：流式 chunk 到达频率高，逐条 scrollTop 会频繁触发重排卡顿页面，
        // 用 requestAnimationFrame 合并到每帧一次
        let _chatScrollPending = false;
        function scheduleChatScroll() {
            if (_chatScrollPending) return;
            _chatScrollPending = true;
            requestAnimationFrame(() => {
                _chatScrollPending = false;
                const ca = document.getElementById('chatArea');
                if (ca) ca.scrollTop = ca.scrollHeight;
            });
        }

        function resetChatReasoning() {
            chatReasoningDiv = null;
            _reasoningBuf = '';
        }

        // 思维链批量追加：chunk 按流式速率到达（每秒可达上百个），逐个插 DOM 会让
        // 可见的 pre-wrap 容器每帧多次失效重排导致卡顿。先入缓冲，rAF 每帧只追加一次。
        let _reasoningBuf = '';
        let _reasoningFlushPending = false;

        function _flushChatReasoning() {
            _reasoningFlushPending = false;
            if (!_reasoningBuf) return;
            const text = _reasoningBuf;
            _reasoningBuf = '';
            // 防脱挂：chatArea 重渲染（一键生成清屏/任务切换重连等）会使旧块脱离文档，
            // 检测 isConnected 失效即原地重建，避免追加到不可见的孤立节点
            if (!chatReasoningDiv || !chatReasoningDiv.isConnected) {
                chatReasoningDiv = document.createElement('div');
                chatReasoningDiv.className = 'chat-reasoning';
                chatReasoningDiv.innerHTML =
                    '<div class="chat-reasoning-header" onclick="this.nextElementSibling.style.display=' +
                    "(this.nextElementSibling.style.display === 'none' ? 'block' : 'none')\">" +
                    '🧠 思维链 <span style="color:#999">▾</span></div>' +
                    '<div class="chat-reasoning-body"></div>';
                document.getElementById('chatArea').appendChild(chatReasoningDiv);
            }
            chatReasoningDiv.querySelector('.chat-reasoning-body').insertAdjacentText('beforeend', text);
            scheduleChatScroll();
        }

        function appendChatReasoning(content) {
            // 对话思维链：缓冲后按帧批量渲染（见 _flushChatReasoning 注释）
            _reasoningBuf += content;
            if (!_reasoningFlushPending) {
                _reasoningFlushPending = true;
                requestAnimationFrame(_flushChatReasoning);
            }
        }

        // ── 打字机节流（放慢正文流式显示速度，避免过快刷屏）──
        const TW_INTERVAL_MS = 50;   // 每 tick 间隔
        const TW_CHARS_PER_TICK = 2; // 每 tick 释放字符数（约 40 字/秒）
        let twRaw = '';
        let twPos = 0;
        let twTimer = null;
        let twDiv = null;

        // 增量追加（文本节点 + <br>）：全量重写 innerHTML 会在长回复时反复重新解析
        // 整段 HTML，导致 O(n²) 开销、主线程卡死（页面"没有响应"）。此处只追加增量。
        function _appendEscapedText(div, text) {
            const parts = text.split('\n');
            for (let i = 0; i < parts.length; i++) {
                if (i > 0) div.appendChild(document.createElement('br'));
                if (parts[i]) div.appendChild(document.createTextNode(parts[i]));
            }
        }

        function dripTypewriter() {
            if (!twDiv || !twDiv.isConnected) { clearInterval(twTimer); twTimer = null; return; }
            const newPos = Math.min(twPos + TW_CHARS_PER_TICK, twRaw.length);
            if (newPos > twPos) {
                _appendEscapedText(twDiv, twRaw.slice(twPos, newPos));
                twPos = newPos;
                scheduleChatScroll();
            }
            if (twPos >= twRaw.length) {
                clearInterval(twTimer);
                twTimer = null;
            }
        }

        function feedTypewriter(content, div) {
            twDiv = div;
            twRaw += content;
            if (!twTimer) twTimer = setInterval(dripTypewriter, TW_INTERVAL_MS);
        }

        function flushTypewriter() {
            if (twDiv && twDiv.isConnected && twPos < twRaw.length) {
                _appendEscapedText(twDiv, twRaw.slice(twPos));
            }
            clearInterval(twTimer);
            twTimer = null; twRaw = ''; twPos = 0; twDiv = null;
        }

        function resetTypewriter() {
            clearInterval(twTimer);
            twTimer = null; twRaw = ''; twPos = 0; twDiv = null;
        }

        // ── 暂停生成：中止后台生成任务 + 断开本地 SSE 订阅，恢复输入 ──
        async function pauseGeneration() {
            if (!isStreaming) return;
            let ok = false;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/stream/cancel`, { method: 'POST' });
                const data = await resp.json().catch(() => ({}));
                ok = !!data.cancelled;
            } catch (e) {
                console.warn('暂停请求失败:', e);
            }
            if (ok) showToast('⏸ 已暂停生成，可直接输入新消息', 'info');
            else showToast('生成已结束', 'info');
            // 断开本地 SSE 订阅；abort 触发所在流的 finally 重置 UI（发送按钮恢复可用）
            if (currentAbortController) {
                try { currentAbortController.abort(); } catch (e) { /* ignore */ }
            }
        }

        // [PORT] 项目徽标 + review 链接改为函数，随初始化/项目切换刷新
        function _refreshProjectBadge(restored) {
            document.getElementById('projectBadge').textContent =
                '项目: ' + (restored ? '已恢复会话' : new Date().toLocaleDateString());
        }
        function _refreshReviewLink() {
            const reviewLink = document.getElementById('reviewLink');
            reviewLink.href = _agentPageUrl(AGENT_BASE + '/agent/review/' + PROJECT_ID);
            reviewLink.style.display = 'inline';
        }

        // ── Attachments ──
        let uploadedFiles = [];  // {file_id, filename, char_count, preview, status}
        // 进行中的上传：uploadId -> AbortController，用于取消附件/模板/文件夹上传
        const activeUploads = {};

        async function handleFileSelect(event) {
            const files = event.target.files;
            if (!files.length) return;
            for (const file of files) {
                await uploadFile(file);
            }
            event.target.value = '';  // reset input
        }

        // 根据相对路径列表构建目录树（用于文件夹上传时的目录结构预览）
        function buildFolderTree(paths) {
            const root = { dirs: {}, files: [] };
            for (const p of paths) {
                const parts = String(p).split('/').filter(Boolean);
                let node = root;
                for (let i = 0; i < parts.length; i++) {
                    const part = parts[i];
                    const isLast = i === parts.length - 1;
                    if (isLast) {
                        node.files.push(part);
                    } else {
                        if (!node.dirs[part]) node.dirs[part] = { dirs: {}, files: [] };
                        node = node.dirs[part];
                    }
                }
            }
            return root;
        }

        function renderTree(node, depth) {
            let html = '';
            const indent = '&nbsp;&nbsp;'.repeat(depth);
            for (const dir of Object.keys(node.dirs).sort()) {
                html += `<div>${indent}📁 ${escapeHtml(dir)}/</div>`;
                html += renderTree(node.dirs[dir], depth + 1);
            }
            node.files.slice().sort().forEach(f => {
                html += `<div>${indent}📄 ${escapeHtml(f)}</div>`;
            });
            return html;
        }

        async function handleFolderSelect(event) {
            // 关键：先 Array.from 快照 FileList，再 reset input.value。
            // 浏览器中 input.value = '' 会清空其 FileList（引用型），
            // 若先 reset 再读取 files，会导致 files 变空、上传静默失败。
            const files = Array.from(event.target.files || []);
            if (!files.length) return;

            // 从第一个文件的 webkitRelativePath 推断文件夹名
            const firstPath = files[0].webkitRelativePath || files[0].name;
            const folderName = firstPath.split('/')[0] || '未命名文件夹';

            // 收集文件与相对路径（先捕获 File 引用，再 reset input）
            const fileList = [];
            const relativePaths = [];
            for (const file of files) {
                const relPath = file.webkitRelativePath || file.name;
                fileList.push({ file, relativePath: relPath });
                relativePaths.push(relPath);
            }

            event.target.value = '';  // reset input（清空以便下次选择同一文件夹）

            const folderUploadId = 'folder_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
            const controller = new AbortController();
            activeUploads[folderUploadId] = controller;

            // 目录结构（上传前即可见）
            const treeHtml = renderTree(buildFolderTree(relativePaths), 0);

            const progressDiv = document.createElement('div');
            progressDiv.className = 'folder-progress-container';
            progressDiv.innerHTML = `
                <div class="folder-progress-text" id="folderTitle">📁 正在上传「${escapeHtml(folderName)}」（${fileList.length} 个文件）... <a style="cursor:pointer;color:#f44336;margin-left:8px;text-decoration:none" onclick="cancelUpload('${folderUploadId}')" title="取消上传">取消</a></div>
                <div class="folder-progress"><div class="folder-progress-fill" id="folderFill" style="width:0%"></div></div>
                <div style="margin:10px 0;padding:8px;background:#fafafa;border:1px solid #eee;border-radius:6px;font-size:12px;max-height:180px;overflow-y:auto">
                    <div style="color:#666;margin-bottom:4px">目录结构：</div>
                    ${treeHtml}
                </div>
                <div id="folderFileList" style="font-size:12px"></div>
            `;
            document.getElementById('chatArea').appendChild(progressDiv);

            const fileListEl = progressDiv.querySelector('#folderFileList');
            const fillEl = progressDiv.querySelector('#folderFill');
            const titleEl = progressDiv.querySelector('#folderTitle');

            const onEvent = (data) => {
                switch (data.type) {
                    case 'file_start': {
                        const row = document.createElement('div');
                        row.id = `folder-file-${data.index}`;
                        row.style.cssText = 'padding:4px 0;border-bottom:1px solid #f5f5f5;color:#555';
                        row.innerHTML = `<span style="color:#999">[${data.index}/${data.total}]</span> ⏳ ${escapeHtml(data.topic || data.filename)} <span style="color:#bbb">· 解析中...</span>`;
                        fileListEl.appendChild(row);
                        fillEl.style.width = `${Math.round((data.index - 1) / data.total * 100)}%`;
                        break;
                    }
                    case 'file_done': {
                        const row = document.getElementById(`folder-file-${data.index}`);
                        if (row) {
                            const icon = data.status === 'ok' ? '✅' : (data.status === 'empty' || data.status === 'binary') ? 'ℹ️' : '⚠️';
                            const summary = data.summary ? ` — ${escapeHtml(data.summary)}` : '';
                            row.innerHTML = `<span style="color:#999">[${data.index}/${data.total}]</span> ${icon} ${escapeHtml(data.topic || data.filename)}${summary}`;
                            row.style.color = data.status === 'ok' ? '#2e7d32' : '#d32f2f';
                        }
                        fillEl.style.width = `${Math.round(data.index / data.total * 100)}%`;
                        break;
                    }
                    case 'done': {
                        fillEl.style.width = '100%';
                        titleEl.innerHTML = `✅ 文件夹「${escapeHtml(data.folder_name)}」解析完成（${data.total_files} 个文件，成功 ${data.ok_count}，共 ${(data.total_chars / 1024).toFixed(1)} KB${data.failed_count > 0 ? '，' + data.failed_count + ' 个失败' : ''}）`;
                        break;
                    }
                    case 'error': {
                        const row = document.createElement('div');
                        row.style.cssText = 'color:#c62828;padding:4px 0';
                        row.innerHTML = `❌ ${escapeHtml(data.message)}`;
                        fileListEl.appendChild(row);
                        break;
                    }
                }
                document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
            };

            try {
                await uploadFolderBatch(fileList, folderName, controller.signal, onEvent);
                await fetchAttachments();
                fetchState();
            } catch (err) {
                if (err.name === 'AbortError') {
                    titleEl.innerHTML = `⏹️ 已取消上传「${escapeHtml(folderName)}」`;
                } else {
                    const row = document.createElement('div');
                    row.style.cssText = 'color:#c62828;padding:4px 0';
                    row.innerHTML = '❌ 文件夹上传失败: ' + escapeHtml(err.message);
                    fileListEl.appendChild(row);
                }
            } finally {
                delete activeUploads[folderUploadId];
                // 保留进度容器，供用户查看目录结构与逐文件主题/摘要
            }
        }

        async function uploadFolderBatch(fileList, folderName, signal, onEvent) {
            const formData = new FormData();
            const relativePaths = [];

            for (const { file, relativePath } of fileList) {
                relativePaths.push(relativePath);
                formData.append('files', file);
            }

            formData.append('relative_paths', JSON.stringify(relativePaths));
            formData.append('folder_name', folderName);

            const resp = await fetch(`${AGENT_BASE}/api/agent/upload-folder/${PROJECT_ID}`, {
                method: 'POST',
                body: formData,
                signal: signal,
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${resp.status}`);
            }

            // 流式读取 SSE：逐文件解析进度事件
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    let data;
                    try { data = JSON.parse(line.slice(6)); } catch (e) { continue; }
                    onEvent(data);
                }
            }
        }

        async function uploadFile(file, hidden = false) {
            // Validate size (20MB)
            const maxSize = 20 * 1024 * 1024;
            if (file.size > maxSize) {
                showError(`文件「${file.name}」超过20MB限制 (${(file.size/1024/1024).toFixed(1)}MB)`);
                return null;
            }
            // Validate format
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            const allowed = ['.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls', '.md', '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'];
            if (!allowed.includes(ext)) {
                showError(`不支持的文件格式「${ext}」`);
                return null;
            }

            let resultFileId = null;

            // Add uploading chip（隐藏模式不上传为附件，仅作为「修改文档」处理对象）
            const tempId = 'uploading_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
            if (!hidden) {
                uploadedFiles.push({ file_id: tempId, filename: file.name, char_count: 0, status: 'uploading' });
                renderAttachmentChips();
            }

            // 解析提示：隐藏模式（修改文档入口）上传后无附件 chip，需在聊天区单独提示解析进度
            let parsingDiv = null;
            if (hidden) {
                parsingDiv = document.createElement('div');
                parsingDiv.className = 'tool-indicator';
                parsingDiv.id = 'parsing-indicator';
                parsingDiv.innerHTML = `<div class="spinner"></div>📄 正在解析文档「${escapeHtml(file.name)}」，请稍候...`;
                const area = document.getElementById('chatArea');
                area.appendChild(parsingDiv);
                area.scrollTop = area.scrollHeight;
            }

            const controller = new AbortController();
            activeUploads[tempId] = controller;

            try {
                const formData = new FormData();
                formData.append('file', file);
                if (hidden) {
                    formData.append('hidden', 'true');
                }

                const resp = await fetch(`${AGENT_BASE}/api/agent/upload/${PROJECT_ID}`, {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal,
                });
                const data = await resp.json();

                // HTTP 4xx/5xx 时后端错误信息在 detail 字段（如"文件提取超时"），
                // 透传真实原因，避免只显示笼统的"上传失败"
                if (!resp.ok) {
                    if (!hidden) {
                        uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                    }
                    showError(data.detail || data.message || `上传失败 (HTTP ${resp.status})`);
                    return null;
                }

                if (data.success) {
                    const taskId = data.file_id;
                    if (!taskId) {
                        if (!hidden) {
                            uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                        }
                        showError(data.message || '上传失败');
                        return null;
                    }

                    // 后端已改为异步：上传接口立即返回 processing，
                    // 此处轮询提取状态，完成后调用 finalize 把全文写入 Agent 状态
                    let finalized = false;
                    for (let i = 0; i < 1600; i++) {
                        if (controller.signal.aborted) {
                            throw new DOMException('已取消', 'AbortError');
                        }
                        await new Promise(r => setTimeout(r, 1500));
                        const statusResp = await fetch(AGENT_BASE + '/api/extract-status/' + taskId);
                        if (statusResp.status === 404) {
                            throw new Error('提取任务已丢失（服务可能重启），请重试');
                        }
                        if (!statusResp.ok) {
                            throw new Error('查询提取状态失败');
                        }
                        const st = await statusResp.json();
                        if (st.status === 'failed') {
                            throw new Error(st.message || '提取失败');
                        }
                        if (st.status === 'completed') {
                            // 提取完成，调用 finalize 将全文写入 Agent 状态
                            const finResp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/attachments/${taskId}/finalize`, { method: 'POST' });
                            const finData = await finResp.json().catch(() => ({}));
                            if (!finData.success) {
                                throw new Error(finData.detail || '附件状态写入失败');
                            }
                            if (!hidden) {
                                uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                                uploadedFiles.push({
                                    file_id: taskId,
                                    filename: finData.filename || data.filename,
                                    char_count: finData.char_count,
                                    preview: finData.preview,
                                    status: 'completed',
                                });
                                // Brief success indicator in chat
                                appendMessage('agent', `📎 已上传「${finData.filename || data.filename}」(${finData.char_count} 字符)。我可以在对话中检索此文件内容。`);
                            }
                            resultFileId = taskId;
                            finalized = true;
                            break;
                        }
                    }
                    if (!finalized) {
                        throw new Error('提取超时（超过 40 分钟），请重试或使用更小的文档');
                    }
                } else {
                    if (!hidden) {
                        uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                    }
                    showError(data.detail || data.message || '上传失败');
                }
            } catch (err) {
                if (!hidden) {
                    uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                }
                if (err.name !== 'AbortError') {
                    showError('上传失败: ' + err.message);
                }
            } finally {
                delete activeUploads[tempId];
                if (parsingDiv) parsingDiv.remove();
            }
            if (!hidden) {
                renderAttachmentChips();
                fetchState();  // refresh sidebar
            }
            return resultFileId;
        }

        // 在输入框光标处插入一段引用文本（如 @文件名），仅插入文字、不上传文件
        function insertReferenceToken(token) {
            const input = document.getElementById('userInput');
            const pos = (input.selectionStart != null) ? input.selectionStart : input.value.length;
            const before = input.value.slice(0, pos);
            const after = input.value.slice(pos);
            const sep = (before && !before.endsWith(' ') && !before.endsWith('\n')) ? ' ' : '';
            const tail = (after && !after.startsWith(' ')) ? ' ' : '';
            input.value = before + sep + token + tail + after;
            const newPos = (before + sep + token + tail).length;
            input.setSelectionRange(newPos, newPos);
            input.focus();
            // 手动自适应高度
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
            updateClearBtn();
        }

        // 快速清空输入框（点击"×"按钮）
        function clearInput() {
            const input = document.getElementById('userInput');
            input.value = '';
            input.style.height = 'auto';
            updateClearBtn();
            input.focus();
        }

        // 根据输入框是否有文字，显示/隐藏清空按钮
        function updateClearBtn() {
            const input = document.getElementById('userInput');
            const btn = document.getElementById('clearBtn');
            if (btn) btn.style.display = input.value ? 'inline-block' : 'none';
        }

        async function removeAttachment(fileId) {
            try {
                await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/attachments/${fileId}`, {
                    method: 'DELETE',
                });
            } catch (err) {
                // Still remove locally even if server fails
            }
            uploadedFiles = uploadedFiles.filter(f => f.file_id !== fileId);
            renderAttachmentChips();
            fetchState();
        }

        // 取消一个进行中的上传（附件/模板/文件夹）。
        // abort 对应的 fetch（其 catch 分支会识别 AbortError 而不弹错误），
        // 并立即清理本地占位 chip；对不存在的 uploadId 是幂等空操作。
        function cancelUpload(uploadId) {
            const controller = activeUploads[uploadId];
            if (controller) {
                controller.abort();
                delete activeUploads[uploadId];
            }
            uploadedFiles = uploadedFiles.filter(f => f.file_id !== uploadId);
            templates = templates.filter(t => t.template_id !== uploadId);
            renderAttachmentChips();
            renderTemplateChips();
        }

        function renderAttachmentChips() {
            const area = document.getElementById('attachmentArea');
            // Clear all chips but keep the upload buttons
            const uploadBtn = document.getElementById('attUploadBtn');
            const fileInput = document.getElementById('fileInput');
            const folderInput = document.getElementById('folderInput');
            const folderBtn = document.getElementById('folderUploadBtn');
            area.innerHTML = '';
            area.appendChild(fileInput);
            area.appendChild(uploadBtn);
            area.appendChild(folderInput);
            area.appendChild(folderBtn);

            const folderFiles = uploadedFiles.filter(f => f.relative_path);
            const regularFiles = uploadedFiles.filter(f => !f.relative_path);

            // 渲染普通文件（无 relative_path）
            regularFiles.forEach(f => {
                area.appendChild(buildAttachmentChip(f));
            });

            // 渲染文件夹文件（按根文件夹分组）
            if (folderFiles.length > 0) {
                const folderName = (folderFiles[0].relative_path || '').split('/')[0] || '文件夹';
                const folderHeader = document.createElement('span');
                folderHeader.className = 'att-chip folder-header';
                folderHeader.style.background = '#ede7f6';
                folderHeader.style.borderColor = '#d1c4e9';
                folderHeader.style.color = '#5e35b1';
                folderHeader.innerHTML = `<span class="att-name" title="${escapeHtml(folderName)}">📁 ${escapeHtml(folderName)}</span><span class="att-size">${folderFiles.length} 文件</span>`;
                area.appendChild(folderHeader);

                folderFiles.forEach(f => {
                    area.appendChild(buildAttachmentChip(f));
                });
            }
        }

        function buildAttachmentChip(f) {
            const chip = document.createElement('span');
            chip.className = 'att-chip' + (f.status === 'uploading' ? ' uploading' : '');
            if (f.status === 'uploading') {
                chip.innerHTML = `
                    <span class="att-spinner"></span>
                    <span class="att-name">${escapeHtml(f.filename)}</span>
                    <span class="att-size">上传中...</span>
                    <span class="att-remove" onclick="cancelUpload('${f.file_id}')" title="取消上传">×</span>
                `;
            } else {
                const sizeKB = (f.char_count / 1024).toFixed(1);
                const displayName = f.relative_path ? f.relative_path.split('/').slice(1).join('/') : f.filename;
                chip.innerHTML = `
                    <span class="att-name" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span>
                    <span class="att-size">${sizeKB}KB</span>
                    <span class="att-modify" onclick="openModifyDialog('${f.file_id}', '${(f.filename || '').replace(/'/g, "\\'")}')" title="修改文档">✏️</span>
                    <span class="att-remove" onclick="removeAttachment('${f.file_id}')" title="移除附件">×</span>
                `;
                // 文件夹文件用完整相对路径，普通文件用文件名（与 Agent 提示中标注一致）
                makeChipDraggable(chip, f.relative_path || f.filename);
            }
            return chip;
        }

        async function fetchAttachments() {
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/attachments`);
                const data = await resp.json();
                if (data.success && data.attachments) {
                    uploadedFiles = data.attachments.map(a => ({ ...a, status: 'completed' }));
                    renderAttachmentChips();
                }
            } catch (e) { /* Silently fail */ }
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        // 让附件/模板 chip 可拖拽到输入框：dragstart 时携带「引用文本」（原始文件名/相对路径）
        function makeChipDraggable(el, refText) {
            el.draggable = true;
            el.addEventListener('dragstart', function(e) {
                e.dataTransfer.setData('application/x-file-ref', refText);
                e.dataTransfer.setData('text/plain', refText);
                e.dataTransfer.effectAllowed = 'copy';
            });
        }

        // ── Templates (模板管理) ──
        let templates = [];  // {template_id, name, filename, doc_type, char_count, status}
        let _selectedTemplateFiles = [];  // File[]，支持一次选择多个模板文件批量添加
        const TPL_ALLOWED = ['.pdf', '.docx', '.doc', '.txt', '.md'];
        const TPL_MAX_SIZE = 20 * 1024 * 1024;  // 20MB
        const TPL_DOC_TYPE_LABELS = {
            'design_input': '设计输入',
            'design_development_plan': '项目开发计划书',
            'risk_management_plan': '风险管理计划',
            'market_research_product_definition': '市场调研与产品定义报告',
            'project_feasibility_study': '项目可行性研究报告',
            'patent_analysis_report': '专利分析报告',
            'project_approval_review': '立项评审记录',
            'regulatory_strategy_document': '注册路径策略'
        };

        // 从后端 /api/doc-types 加载完整文档类型（9 大生命周期 140+ 种），
        // 动态填充「目标文档类型」下拉框，并按分类分组展示。
        async function loadDocTypes() {
            try {
                const resp = await fetch(AGENT_BASE + '/api/doc-types');
                const data = await resp.json();
                if (!data.categories || !Array.isArray(data.types)) return;

                // 合并完整 value→label 映射，供模板列表展示用
                const labelMap = {};
                for (const t of data.types) {
                    if (t.value && t.label) labelMap[t.value] = t.label;
                }
                Object.assign(TPL_DOC_TYPE_LABELS, labelMap);

                // 按分类分组填充下拉框
                const sel = document.getElementById('tplDocType');
                if (!sel) return;
                sel.innerHTML = '';
                // 「不指定」空选项置顶并作为默认：模板类型可选，不选则为通用模板
                const noneOpt = document.createElement('option');
                noneOpt.value = '';
                noneOpt.textContent = '不指定（通用模板）';
                sel.appendChild(noneOpt);

                if (Array.isArray(data.dhf_types) && data.dhf_types.length) {
                    // [DHF] 模板上传「目标文档类型」与 胰岛素泵-DHF清单.xlsx 的文件名称
                    // 保持一致：按设计开发阶段分组，value=label=清单文件名称
                    for (const cat of data.dhf_categories) {
                        const og = document.createElement('optgroup');
                        const items = data.dhf_types.filter(t => t.category === cat);
                        og.label = cat + '（' + items.length + '）';
                        for (const t of items) {
                            const opt = document.createElement('option');
                            opt.value = t.value;
                            opt.textContent = t.label;
                            og.appendChild(opt);
                            TPL_DOC_TYPE_LABELS[t.value] = t.label;
                        }
                        sel.appendChild(og);
                    }
                } else {
                    // 降级：DHF 清单不可用时按原 9 大生命周期分类填充
                    for (const cat of data.categories) {
                        const og = document.createElement('optgroup');
                        og.label = cat.name + '（' + (cat.count || 0) + '）';
                        const types = data.types.filter(t => t.category_key === cat.key);
                        for (const t of types) {
                            const opt = document.createElement('option');
                            opt.value = t.value;
                            opt.textContent = t.label;
                            og.appendChild(opt);
                        }
                        sel.appendChild(og);
                    }
                }
                sel.value = '';
            } catch (e) {
                // 加载失败则保留硬编码的 8 个选项作为降级
            }
        }

        function showTemplateDialog() {
            const nameInput = document.getElementById('tplName');
            nameInput.value = '';
            nameInput.disabled = false;
            nameInput.placeholder = '留空则使用文件名';
            document.getElementById('tplDocType').value = '';
            document.getElementById('tplFileName').textContent = '未选择文件';
            document.getElementById('tplFileName').title = '';
            document.getElementById('tplFileInput').value = '';
            _selectedTemplateFiles = [];
            renderSelectedTemplateFiles();
            document.getElementById('templateDialog').style.display = 'flex';
        }

        function closeTemplateDialog() {
            document.getElementById('templateDialog').style.display = 'none';
        }

        // 渲染对话框内「已选文件列表」，每个文件可单独移除
        function renderSelectedTemplateFiles() {
            const container = document.getElementById('tplSelectedList');
            if (!container) return;
            container.innerHTML = '';
            _selectedTemplateFiles.forEach((file, idx) => {
                const row = document.createElement('div');
                row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 8px;background:#e0f2f1;border:1px solid #b2dfdb;border-radius:6px;font-size:12px;color:#00695c';
                const sizeKB = (file.size / 1024).toFixed(1);
                row.innerHTML = `
                    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(file.name)}">📄 ${escapeHtml(file.name)}</span>
                    <span style="color:#80cbc4;font-size:10px;flex-shrink:0">${sizeKB}KB</span>
                    <span style="cursor:pointer;color:#999;font-size:14px;line-height:1;flex-shrink:0" onclick="removeSelectedTemplateFile(${idx})" title="移除该文件">×</span>
                `;
                container.appendChild(row);
            });
        }

        function removeSelectedTemplateFile(idx) {
            _selectedTemplateFiles.splice(idx, 1);
            // 重新计算 UI 状态
            const nameInput = document.getElementById('tplName');
            const fileNameEl = document.getElementById('tplFileName');
            const total = _selectedTemplateFiles.length;
            if (total > 1) {
                fileNameEl.textContent = `已选择 ${total} 个文件`;
                fileNameEl.title = _selectedTemplateFiles.map(f => f.name).join('\n');
                nameInput.value = '';
                nameInput.disabled = true;
                nameInput.placeholder = '（多文件批量添加时使用各文件名）';
            } else if (total === 1) {
                fileNameEl.textContent = _selectedTemplateFiles[0].name;
                fileNameEl.title = '';
                nameInput.disabled = false;
                nameInput.placeholder = '留空则使用文件名';
            } else {
                fileNameEl.textContent = '未选择文件';
                fileNameEl.title = '';
                nameInput.disabled = false;
                nameInput.placeholder = '留空则使用文件名';
            }
            renderSelectedTemplateFiles();
        }

        function handleTemplateFileSelect(event) {
            const files = Array.from(event.target.files || []);
            // 重置 input.value，允许下一次选择同一文件（例如误选后重新点选）
            event.target.value = '';
            if (!files.length) return;

            // 逐个校验格式与大小；对已选列表做去重（同名同大小视为重复）
            const valid = [];
            const rejected = [];
            for (const file of files) {
                const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
                if (!TPL_ALLOWED.includes(ext)) {
                    rejected.push(`${file.name}（格式不支持）`);
                    continue;
                }
                if (file.size > TPL_MAX_SIZE) {
                    rejected.push(`${file.name}（超过20MB限制）`);
                    continue;
                }
                const dup = _selectedTemplateFiles.some(existing =>
                    existing.name === file.name && existing.size === file.size);
                if (dup) {
                    rejected.push(`${file.name}（已选择）`);
                    continue;
                }
                valid.push(file);
            }
            if (rejected.length) {
                showError(`以下文件已跳过：${rejected.join('、')}。支持格式: ${TPL_ALLOWED.join(', ')}`);
            }

            // 追加到已选列表（而非替换），支持「一次选一个、多次追加」的批量添加方式
            _selectedTemplateFiles = _selectedTemplateFiles.concat(valid);

            const nameInput = document.getElementById('tplName');
            const fileNameEl = document.getElementById('tplFileName');
            const total = _selectedTemplateFiles.length;
            if (total > 1) {
                // 多文件：名称输入框禁用，各模板以文件名命名
                fileNameEl.textContent = `已选择 ${total} 个文件`;
                fileNameEl.title = _selectedTemplateFiles.map(f => f.name).join('\n');
                nameInput.value = '';
                nameInput.disabled = true;
                nameInput.placeholder = '（多文件批量添加时使用各文件名）';
            } else if (total === 1) {
                fileNameEl.textContent = _selectedTemplateFiles[0].name;
                fileNameEl.title = '';
                nameInput.disabled = false;
                nameInput.placeholder = '留空则使用文件名';
            } else {
                fileNameEl.textContent = '未选择文件';
                fileNameEl.title = '';
                nameInput.disabled = false;
                nameInput.placeholder = '留空则使用文件名';
            }
            renderSelectedTemplateFiles();
        }

        async function submitTemplate() {
            const name = document.getElementById('tplName').value.trim();
            const docType = document.getElementById('tplDocType').value;
            const files = _selectedTemplateFiles;
            if (!files.length) { showError('请选择模板文件'); return; }

            closeTemplateDialog();

            let successCount = 0;
            const failures = [];
            // 逐个串行上传：后端每个文件都要提取文本（可能触发 MinerU 解析），串行避免资源争用
            for (const file of files) {
                // 名称优先级：用户输入的名称（仅单文件时生效） > 文件名
                // 多文件批量添加时，每个模板以各自文件名命名
                const tplName = (files.length === 1 && name) ? name : file.name;
                const chipId = 'uploading-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);

                // 先显示上传中的 chip 占位
                templates.push({ template_id: chipId, name: tplName, filename: file.name,
                                 doc_type: docType, char_count: 0, status: 'uploading' });
                renderTemplateChips();

                const fd = new FormData();
                fd.append('file', file);
                fd.append('name', tplName);
                fd.append('doc_type', docType);

                const controller = new AbortController();
                activeUploads[chipId] = controller;

                try {
                    const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/templates`, { method: 'POST', body: fd, signal: controller.signal });
                    const data = await resp.json();
                    if (!data.success) {
                        throw new Error(data.message || data.detail || '添加失败');
                    }

                    const taskId = data.template_id;
                    const startedAt = Date.now();
                    // 登记上传任务（跨刷新/任务切换可恢复进度与 finalize）
                    registerUpload({ type: 'template', taskId, filename: file.name,
                                     name: tplName, projectId: PROJECT_ID, docType: docType, startedAt });
                    // 可恢复轮询：chip 实时显示阶段+耗时；超时保留登记（刷新后自动恢复），
                    // 取消/失败时由 pollTemplateUpload 内部注销登记
                    await pollTemplateUpload(taskId, PROJECT_ID, chipId, startedAt, controller.signal);
                    successCount++;
                } catch (e) {
                    templates = templates.filter(t => t.template_id !== chipId);
                    if (e.name === 'AbortError') {
                        renderTemplateChips();
                        break;  // 用户取消：停止整个批量上传
                    }
                    failures.push(`${file.name}: ${e.message}`);
                } finally {
                    delete activeUploads[chipId];
                }
                renderTemplateChips();
            }

            if (successCount) showToast(`成功添加 ${successCount} 个模板，已作为文档风格参照`);
            if (failures.length) showError(`部分模板暂未完成提取：${failures.join('；')}`);
        }

        function renderTemplateChips() {
            const area = document.getElementById('templateArea');
            if (!templates.length) {
                area.style.display = 'none';
                area.innerHTML = '';
                return;
            }
            area.style.display = 'flex';
            area.innerHTML = '';
            templates.forEach(t => {
                const chip = document.createElement('span');
                chip.className = 'tpl-chip' + (t.status === 'uploading' ? ' uploading' : '');
                const sizeText = t.status === 'uploading'
                    ? `${t.stage || '上传中'}${t.elapsed ? ' · ' + t.elapsed + 's' : ''}`
                    : (t.char_count ? (t.char_count / 1024).toFixed(1) + 'KB' : '');
                chip.innerHTML = `
                    <span class="tpl-name" title="${escapeHtml(t.filename)}">${t.status === 'uploading' ? '⏳ ' : '📄 '}${escapeHtml(t.name || t.filename)}</span>
                    <span class="tpl-type">${escapeHtml(TPL_DOC_TYPE_LABELS[t.doc_type] || t.doc_type || '模板')}</span>
                    <span style="color:#80cbc4;font-size:10px;flex-shrink:0">${sizeText}</span>
                    ${t.status === 'uploading'
                        ? `<span class="tpl-remove" onclick="cancelUpload('${t.template_id}')" title="取消上传">×</span>`
                        : `<span class="tpl-remove" onclick="removeTemplate('${t.template_id}')" title="移除模板">×</span>`}
                `;
                if (t.status !== 'uploading') {
                    // 模板引用名与 Agent 提示一致：name（用户命名）优先，回退文件名
                    makeChipDraggable(chip, t.name || t.filename);
                }
                area.appendChild(chip);
            });
        }

        async function removeTemplate(templateId) {
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/templates/${templateId}`, { method: 'DELETE' });
                const data = await resp.json();
                if (data.success) {
                    templates = templates.filter(t => t.template_id !== templateId);
                    renderTemplateChips();
                    showToast('模板已移除');
                } else {
                    showError(data.message || '移除模板失败');
                }
            } catch (e) {
                showError('移除模板失败: ' + e.message);
            }
        }

        async function fetchTemplates() {
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/templates`);
                const data = await resp.json();
                if (data.success && data.templates) {
                    templates = data.templates.map(t => ({ ...t, status: 'completed' }));
                    renderTemplateChips();
                }
            } catch (e) { /* Silently fail */ }
        }

        // 找回刷新/切换任务后中断的模板上传：对属于当前项目的孤儿模板任务补 finalize
        async function recoverOrphanTemplates() {
            try {
                const resp = await fetch(AGENT_BASE + '/api/agent/templates/orphan');
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok || !data.orphans || !data.orphans.length) return;
                const mine = data.orphans.filter(o => o.project_id === PROJECT_ID);
                if (!mine.length) return;
                for (const o of mine) {
                    if (o.status === 'failed') continue;
                    try {
                        const finResp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/templates/${o.template_id}/finalize`, { method: 'POST' });
                        const finData = await finResp.json().catch(() => ({}));
                        if (finData.success && !finData.duplicate) {
                            showToast(`✓ 已恢复中断的模板上传「${finData.name || o.name}」`, 'success', 4000);
                        }
                    } catch (e) { /* 单个失败不影响其他 */ }
                }
                await fetchTemplates();
            } catch (e) { /* Silently fail */ }
        }

        // Drag-and-drop on chat area（[PORT] 顶层 IIFE → 具名函数，由 _doInit 首次调用）
        function setupDragDrop() {
            const chatArea = document.getElementById('chatArea');
            const attArea = document.getElementById('attachmentArea');

            ['dragenter', 'dragover'].forEach(evt => {
                chatArea.addEventListener(evt, function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    attArea.classList.add('drag-over');
                });
            });
            ['dragleave', 'drop'].forEach(evt => {
                chatArea.addEventListener(evt, function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    attArea.classList.remove('drag-over');
                });
            });
            chatArea.addEventListener('drop', function(e) {
                const files = e.dataTransfer.files;
                if (files.length) {
                    for (const file of files) {
                        uploadFile(file);
                    }
                }
            });
            // Also allow drop on attachment area itself
            attArea.addEventListener('drop', function(e) {
                e.preventDefault();
                e.stopPropagation();
                attArea.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                if (files.length) {
                    for (const file of files) {
                        uploadFile(file);
                    }
                }
            });
            ['dragenter', 'dragover'].forEach(evt => {
                attArea.addEventListener(evt, function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    attArea.classList.add('drag-over');
                });
            });
            attArea.addEventListener('dragleave', function(e) {
                attArea.classList.remove('drag-over');
            });
        }

        // 拖拽到输入框 → 仅把「@文件名/@相对路径」作为引用插入输入框（不上传、不入附件）
        // 支持两种来源：1) 从系统拖入的文件；2) 从附件/模板 chip 拖来的已上传文件
        function setupInputDragDrop() {
            const inputArea = document.querySelector('.input-area');
            if (!inputArea) return;

            function isAcceptableDrag(e) {
                if (!e.dataTransfer) return false;
                const types = Array.from(e.dataTransfer.types || []);
                return types.includes('Files') || types.includes('application/x-file-ref');
            }

            ['dragenter', 'dragover'].forEach(evt => {
                inputArea.addEventListener(evt, function(e) {
                    if (!isAcceptableDrag(e)) return;
                    e.preventDefault();
                    e.stopPropagation();
                    inputArea.classList.add('drag-over');
                });
            });
            ['dragleave', 'drop'].forEach(evt => {
                inputArea.addEventListener(evt, function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    inputArea.classList.remove('drag-over');
                });
            });
            inputArea.addEventListener('drop', function(e) {
                const dt = e.dataTransfer;
                e.preventDefault();
                e.stopPropagation();
                inputArea.classList.remove('drag-over');
                if (!dt) return;

                // 1) 从附件/模板 chip 拖来的引用（精确文件名/相对路径）
                if (Array.from(dt.types || []).includes('application/x-file-ref')) {
                    const refText = dt.getData('application/x-file-ref');
                    if (refText) insertReferenceToken('@' + refText);
                    return;
                }
                // 2) 从系统拖入的文件 → 引用其文件名
                const files = dt.files;
                if (files && files.length) {
                    for (const file of files) {
                        insertReferenceToken('@' + file.name);
                    }
                }
            });
        }

        // ── Progress Panel ──
        const STEPS = [
            { id: 'product', label: '1. 产品画像', key: 'product' },
            { id: 'standards', label: '2. 标准适用性清单', key: 'standards' },
            { id: 'content_collection', label: '3. 结构化内容采集', key: 'content_sections' },
            { id: 'document', label: '4. 文档生成', key: 'document_generation' },
            { id: 'review', label: '5. 文档审核', key: 'review' },
            { id: 'export', label: '6. 导出交付', key: 'export' },
        ];

        function renderSteps(state) {
            const list = document.getElementById('stepList');
            list.innerHTML = STEPS.map(s => {
                let icon = '⬜', cls = 'pending';
                if (s.key === 'product') {
                    if (state?.product?.status === 'confirmed') { icon = '✅'; cls = 'done'; }
                    else if (state?.product?.status === 'partial') { icon = '🔄'; cls = 'in_progress'; }
                } else if (s.key === 'standards') {
                    if (state?.standards?.status === 'confirmed') { icon = '✅'; cls = 'done'; }
                    else if (state?.standards?.status === 'partial') { icon = '🔄'; cls = 'in_progress'; }
                } else if (s.key === 'content_sections') {
                    const secs = state?.content_sections || {};
                    const done = Object.values(secs).filter(v => v.status === 'confirmed').length;
                    const total = Object.keys(secs).length || 10;
                    if (done === total) { icon = '✅'; cls = 'done'; }
                    else if (done > 0) { icon = '🔄'; cls = 'in_progress'; }
                } else if (s.key === 'document_generation') {
                    const status = state?.document_generation?.status;
                    if (status === 'completed') { icon = '✅'; cls = 'done'; }
                    else if (status === 'in_progress') { icon = '🔄'; cls = 'in_progress'; }
                } else if (s.key === 'traceability') {
                    if (state?.traceability?.status === 'completed') { icon = '✅'; cls = 'done'; }
                } else if (s.key === 'review') {
                    if (state?.review?.status === 'completed') { icon = '✅'; cls = 'done'; }
                }
                return `<div class="step-item">
                    <div class="step-icon ${cls}">${icon}</div>
                    <div class="step-text"><span class="step-label">${s.label}</span></div>
                </div>`;
            }).join('');

            // Unresolved items
            const unresolved = state?.unresolved_items || [];
            const box = document.getElementById('unresolvedBox');
            if (unresolved.length) {
                box.style.display = 'block';
                document.getElementById('unresolvedList').innerHTML =
                    unresolved.map(i => `<li>${i}</li>`).join('');
            } else {
                box.style.display = 'none';
            }
        }

        // ── 用户技能库：沉淀指导命令/生成规则，快捷复用 ──
        let _editingSkillId = null;

        function openSkillsDialog() {
            _editingSkillId = null;
            document.getElementById('skillNameInput').value = '';
            document.getElementById('skillContentInput').value = '';
            document.getElementById('skillDescInput').value = '';
            document.getElementById('skillSaveBtn').textContent = '保存技能';
            document.getElementById('skillsDialog').style.display = 'flex';
            loadSkills();
        }

        function closeSkillsDialog() {
            document.getElementById('skillsDialog').style.display = 'none';
        }

        async function loadSkills() {
            try {
                const resp = await fetch(AGENT_BASE + '/api/skills');
                const data = await resp.json().catch(() => ({ skills: [] }));
                renderSkillList(data.skills || []);
            } catch (e) {
                renderSkillList([]);
            }
        }

        function renderSkillList(skills) {
            window._skills = skills;
            const box = document.getElementById('skillList');
            if (!skills.length) {
                box.innerHTML = '<p style="color:#999;text-align:center;padding:12px">暂无技能，用下方表单创建第一个</p>';
                return;
            }
            box.innerHTML = '';
            const btnStyle = 'padding:3px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:11px;cursor:pointer';
            skills.forEach(s => {
                const item = document.createElement('div');
                item.style.cssText = 'border:1px solid #e0e0e0;border-radius:8px;padding:8px 10px';
                const content = s.content.length > 120 ? s.content.slice(0, 120) + '…' : s.content;
                item.innerHTML =
                    `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
                        <strong style="font-size:13px">🧩 ${escapeHtml(s.name)}</strong>
                        <span style="display:flex;gap:5px;flex-shrink:0">
                            <button style="${btnStyle};color:#2e7d32" onclick="useSkillSend('${s.id}')" title="把技能作为指令发送给 Agent">发送</button>
                            <button style="${btnStyle};color:#1565c0" onclick="useSkillInsert('${s.id}')" title="插入输入框，可再编辑">插入</button>
                            <button style="${btnStyle}" onclick="editSkill('${s.id}')">编辑</button>
                            <button style="${btnStyle};color:#c62828" onclick="deleteSkill('${s.id}')">删除</button>
                        </span>
                    </div>
                    <div style="font-size:12px;color:#666;margin-top:4px;white-space:pre-wrap">${escapeHtml(content)}</div>`;
                box.appendChild(item);
            });
        }

        function _getSkill(id) {
            return (window._skills || []).find(s => s.id === id);
        }

        function useSkillInsert(id) {
            const s = _getSkill(id);
            if (!s) return;
            const input = document.getElementById('userInput');
            input.value = (input.value ? input.value + '\n' : '') + s.content;
            input.focus();
            updateClearBtn();
        }

        function useSkillSend(id) {
            const s = _getSkill(id);
            if (!s) return;
            closeSkillsDialog();
            const input = document.getElementById('userInput');
            input.value = `【应用技能「${s.name}」】请按以下规则执行：\n${s.content}`;
            updateClearBtn();
            sendMessage();
        }

        async function saveSkill() {
            const name = document.getElementById('skillNameInput').value.trim();
            const content = document.getElementById('skillContentInput').value.trim();
            const description = document.getElementById('skillDescInput').value.trim();
            if (!name || !content) { showError('技能名称与内容不能为空'); return; }
            try {
                let resp;
                if (_editingSkillId) {
                    resp = await fetch(AGENT_BASE + '/api/skills/' + _editingSkillId, {
                        method: 'PUT',
                        body: new URLSearchParams({ name, content, description }),
                    });
                } else {
                    const fd = new FormData();
                    fd.append('name', name);
                    fd.append('content', content);
                    fd.append('description', description);
                    resp = await fetch(AGENT_BASE + '/api/skills', { method: 'POST', body: fd });
                }
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || '保存失败');
                showToast(_editingSkillId ? '✓ 技能已更新' : '✓ 技能已保存', 'success');
                _editingSkillId = null;
                document.getElementById('skillNameInput').value = '';
                document.getElementById('skillContentInput').value = '';
                document.getElementById('skillDescInput').value = '';
                document.getElementById('skillSaveBtn').textContent = '保存技能';
                loadSkills();
            } catch (e) {
                showError('保存技能失败: ' + e.message);
            }
        }

        function editSkill(id) {
            const s = _getSkill(id);
            if (!s) return;
            _editingSkillId = id;
            document.getElementById('skillNameInput').value = s.name;
            document.getElementById('skillContentInput').value = s.content;
            document.getElementById('skillDescInput').value = s.description || '';
            document.getElementById('skillSaveBtn').textContent = '更新技能';
        }

        async function deleteSkill(id) {
            if (!confirm('确认删除该技能？')) return;
            try {
                const resp = await fetch(AGENT_BASE + '/api/skills/' + id, { method: 'DELETE' });
                if (!resp.ok) throw new Error('删除失败');
                showToast('✓ 技能已删除', 'success');
                loadSkills();
            } catch (e) {
                showError('删除技能失败: ' + e.message);
            }
        }

        // ── Chat ──
        // 时间戳格式化：接受 ISO 字符串或 Date，输出 "MM-dd HH:mm"
        function fmtMsgTs(t) {
            const d = (t instanceof Date) ? t : new Date(t);
            if (isNaN(d.getTime())) return '';
            const p = n => String(n).padStart(2, '0');
            return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
        }

        function appendMessage(role, content, historical, ts) {
            const area = document.getElementById('chatArea');
            // Remove empty state
            const empty = area.querySelector('.empty-state');
            if (empty) empty.remove();

            // 时间戳：历史消息用持久化的 ts；实时消息用当前时间；历史且无 ts（旧消息）不显示
            let timeHtml = '';
            const timeStr = ts ? fmtMsgTs(ts) : (historical ? '' : fmtMsgTs(new Date()));
            if (timeStr) timeHtml = `<div class="msg-time">${timeStr}</div>`;

            const div = document.createElement('div');
            div.className = `msg ${role}`;
            div.innerHTML = timeHtml + formatContent(content);
            area.appendChild(div);
            renderMermaidIn(div);

            // 用户消息：追加「撤回」按钮，点击后移除该消息及其后所有内容
            // 历史消息（historical）不追加：撤回仅支持回滚最新一轮对话
            if (role === 'user' && !historical) {
                const recallBar = document.createElement('div');
                recallBar.className = 'recall-bar';
                const btn = document.createElement('button');
                btn.className = 'recall-btn';
                btn.textContent = '↩ 撤回';
                btn.title = '撤回此消息及其后的所有内容（含 Agent 回复）';
                btn.onclick = function () { recallMessage(div, btn); };
                recallBar.appendChild(btn);
                div.appendChild(recallBar);
            }

            area.scrollTop = area.scrollHeight;
            return div;
        }

        // 加载历史对话：页面刷新/恢复会话后，从后端读取之前的用户消息与 Agent 回复
        // 仅用于展示，历史消息不附「撤回」按钮（撤回只支持回滚最新一轮）
        // limitCount: 可选，只渲染前 N 条（重连续播时排除本轮生成已写入 checkpoint 的消息，
        //             本轮内容由回放事件渲染，避免重复）
        // 历史回顾仅显示最近 HISTORY_LIMIT 条，更早的在顶部给省略提示
        const HISTORY_LIMIT = 20;

        async function loadHistory(limitCount) {
            if (!_hasHistory) return;  // [PORT] 原 !existingProject
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/history`);
                const data = await resp.json();
                if (!resp.ok) {
                    console.warn('加载对话历史失败:', data.detail || resp.status);
                    return;
                }
                if (!data.messages || !data.messages.length) return;
                let msgs = (typeof limitCount === 'number' && limitCount >= 0)
                    ? data.messages.slice(0, limitCount)
                    : data.messages;
                if (msgs.length > HISTORY_LIMIT) {
                    const omitted = msgs.length - HISTORY_LIMIT;
                    msgs = msgs.slice(-HISTORY_LIMIT);
                    const hint = document.createElement('div');
                    hint.className = 'history-omit-hint';
                    hint.textContent = `⋯ 已省略更早的 ${omitted} 条消息（显示最近 ${HISTORY_LIMIT} 条）`;
                    document.getElementById('chatArea').appendChild(hint);
                }
                for (const m of msgs) {
                    const role = m.role === 'assistant' ? 'agent' : m.role;
                    appendMessage(role, m.content, true, m.ts);
                }
            } catch (e) {
                console.warn('加载对话历史失败:', e);
            }
        }

        // ── 后台生成流重连（切换任务切回 / 页面刷新后恢复现场）──
        // 生成在后端后台任务中执行、与页面连接解耦：页面加载时先查询流状态，
        // 若本任务仍在生成中，则只渲染本轮之前的历史 + 本轮用户消息，
        // 再重连 SSE 回放已产生的事件并继续实时接收，恢复到切走前的画面。
        async function checkAndReconnect() {
            let status = null;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/stream/status`);
                status = await resp.json();
            } catch (e) {
                console.warn('查询生成流状态失败:', e);
            }

            if (status && status.active) {
                // 只渲染本轮生成开始前的历史，本轮内容全部由回放事件渲染，避免重复
                await loadHistory(typeof status.history_count === 'number' ? status.history_count : undefined);
                if (status.user_message) appendMessage('user', status.user_message);
                setAgentStatus('⚡ 该任务正在后台生成中，正在恢复实时进度…', true);
                showToast('⚡ 该任务正在后台生成中，已为你重连实时进度', 'info', 4000);
                await reconnectStream();
            } else {
                await loadHistory();
            }
        }

        // 重连后台生成流：GET /stream?from_seq=0 回放缓冲事件并继续实时订阅。
        // 事件渲染逻辑与 sendMessage 一致；此处的 abort 只断开订阅，不影响后台生成。
        async function reconnectStream() {
            isStreaming = true;
            document.getElementById('sendBtn').disabled = true;
            document.getElementById('pauseBtn').style.display = '';
            currentAbortController = new AbortController();

            let agentDiv = null;
            let currentTool = null;
            let thinkingShown = true;
            appendThinkingIndicator();

            try {
                const response = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/stream?from_seq=0`, {
                    signal: currentAbortController.signal,
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const data = JSON.parse(line.slice(6));
                        trackAgentStatus(data);

                        // 首个事件到达即结束「思考中」提示
                        if (thinkingShown) {
                            removeThinkingIndicator();
                            thinkingShown = false;
                        }

                        switch (data.type) {
                            case 'doc_token':
                                // 文档流式输出已下线：前端只保留对话正文与对话思维链
                                break;
                            case 'chat_reasoning':
                                appendChatReasoning(data.content);
                                break;
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                feedTypewriter(data.content, agentDiv);
                                document.getElementById('chatArea').scrollTop =
                                    document.getElementById('chatArea').scrollHeight;
                                break;
                            case 'context_compressed':
                                showToast('🧹 对话历史较长，已自动压缩较早内容以节省上下文', 'info');
                                break;

                            case 'tool_start':
                                currentTool = data.tool;
                                appendToolIndicator(data.tool, true);
                                break;

                            case 'openviking_recall_start':
                                appendOpenVikingIndicator('recall_start', data);
                                break;
                            case 'openviking_recall_done':
                                appendOpenVikingIndicator('recall_done', data);
                                break;
                            case 'openviking_capture':
                                appendOpenVikingIndicator('capture', data);
                                break;
                            case 'openviking_tool':
                                appendOpenVikingIndicator('tool', data);
                                break;
                            case 'ltm_recall_start':
                                appendLtmIndicator('recall_start', data);
                                break;
                            case 'ltm_recall_done':
                                appendLtmIndicator('recall_done', data);
                                break;
                            case 'ltm_capture':
                                appendLtmIndicator('capture', data);
                                break;

                            case 'tool_end':
                                if (currentTool) {
                                    const el = document.getElementById(`tool-${currentTool}`);
                                    if (el) {
                                        el.innerHTML = `<div class="icon">✅</div>${toolLabel(currentTool)}完成`;
                                    }
                                }
                                currentTool = null;
                                break;

                            case 'rag_results':
                                appendRagResults(data);
                                break;

                            case 'waiting_approval':
                                showApprovalButtons(data.interrupt_data);
                                break;

                            case 'done':
                                flushTypewriter();
                                if (agentDiv) autoCollapseLongMessage(agentDiv);
                                break;

                            case 'file_ready':
                                showDownloadButton(data.download_id, data.filename, data.size_bytes);
                                break;

                            case 'modified_doc_ready':
                                showModifiedDownloadButton(data);
                                break;

                            case 'sections_ready':
                                showQuickDownloadBox();
                                break;

                            case 'cancelled':
                                // 后台生成被取消（撤回/删除）：静默结束
                                break;

                            case 'error':
                                showError(data.message);
                                break;
                        }
                    }
                }
            } catch (err) {
                if (err && err.name !== 'AbortError') {
                    console.warn('重连生成流失败:', err);
                }
            } finally {
                removeThinkingIndicator();
                isStreaming = false;
                currentAbortController = null;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('pauseBtn').style.display = 'none';

                // Refresh state sidebar and attachments
                fetchState();
                fetchAttachments();
                fetchTemplates();
            }
        }

        // ── 聊天任务列表（多任务切换）──
        // 从后端拉取全部聊天任务并渲染到侧边栏；当前任务高亮
        async function loadChatList() {
            const listEl = document.getElementById('chatList');
            if (!listEl) return;
            try {
                const resp = await fetch(AGENT_BASE + '/api/agent/projects');
                const data = await resp.json();
                if (!resp.ok) { console.warn('加载聊天任务列表失败:', data.detail || resp.status); return; }
                const projects = data.projects || [];

                // 当前项目若尚未产生 checkpoint（还没发过消息），也要在列表中显示
                const ids = projects.map(p => p.project_id);
                const items = [...projects];
                if (!ids.includes(PROJECT_ID)) {
                    items.unshift({ project_id: PROJECT_ID, title: '新聊天', message_count: 0 });
                }

                listEl.innerHTML = '';
                for (const p of items) {
                    const isActive = p.project_id === PROJECT_ID;
                    const div = document.createElement('div');
                    div.className = 'chat-item' + (isActive ? ' active' : '');
                    const titleSpan = document.createElement('span');
                    titleSpan.className = 'chat-item-title';
                    titleSpan.textContent = p.title || '新聊天';
                    titleSpan.title = p.title || '新聊天';
                    div.appendChild(titleSpan);

                    // 删除按钮（仅非当前任务显示删除；删除当前任务会跳转到全新聊天）
                    const delBtn = document.createElement('button');
                    delBtn.className = 'chat-item-del';
                    delBtn.textContent = '×';
                    delBtn.title = '删除此聊天任务';
                    delBtn.onclick = function (ev) { ev.stopPropagation(); deleteChat(p.project_id); };
                    div.appendChild(delBtn);

                    div.onclick = function () { switchChat(p.project_id); };
                    listEl.appendChild(div);
                }
            } catch (e) {
                console.warn('加载聊天任务列表失败:', e);
            }
        }

        // 切换聊天任务：整页跳转到 ?project=<id>（各任务的状态完全隔离）
        // 生成任务在后端后台执行、与页面连接解耦：切走不会中断生成，
        // 切回该任务时页面会自动重连续播实时进度（见 checkAndReconnect）
        function switchChat(projectId) {
            if (projectId === PROJECT_ID) return;
            _switchToProject(projectId);
        }

        // 开启新聊天任务：跳转到无 project 参数的页面（页面会自动分配新项目ID）
        // 当前任务若在生成中，后台会继续执行，随时可切回查看
        function startNewChat() {
            _switchToProject(null);
        }

        // 删除聊天任务（连同全部对话历史与已生成内容）
        async function deleteChat(projectId) {
            const isCurrent = projectId === PROJECT_ID;
            const tip = isCurrent
                ? '将删除当前聊天任务（含全部对话历史与已生成文档），删除后开启新聊天。'
                : '将删除该聊天任务（含全部对话历史与已生成文档）。';
            if (!confirm('确认删除？' + tip)) return;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    showToast('删除失败: ' + (data.detail || data.message || resp.status), 'error', 5000);
                    return;
                }
                if (isCurrent) {
                    _switchToProject(null);  // [PORT] 原为整页跳转，改为视图内切换
                } else {
                    showToast('✓ 已删除', 'success', 3000);
                    loadChatList();
                }
            } catch (e) {
                showToast('删除失败: ' + e.message, 'error', 5000);
            }
        }

        // 撤回用户消息：移除该消息及其后所有内容；若 Agent 正在生成则中止当前流
        // 同时调用后端 checkpoint 回滚 API，确保 Agent 状态也回到发送前
        // ── 手动压缩上下文：较早消息归并为摘要，保留最近 15 条完整消息 ──
        async function compressContext() {
            if (isStreaming) {
                showToast('正在生成中，请等本轮完成或先暂停再压缩上下文', 'info');
                return;
            }
            if (!confirm('手动压缩对话上下文？\n\n'
                + '· 较早的对话消息将被归并为一段进度摘要（最新优先，旧要求以最新为准）\n'
                + '· 保留最近 15 条完整消息\n'
                + '· 文档内容、附件、模板不受影响；此操作不可撤销')) return;
            const btn = document.getElementById('compressCtxBtn');
            btn.disabled = true;
            btn.textContent = '🗜️ 压缩中...';
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/compress-context`, { method: 'POST' });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || '压缩失败');
                showToast(data.message, data.compressed ? 'success' : 'info', 6000);
            } catch (e) {
                showError('压缩上下文失败: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '🗜️ 压缩上下文';
            }
        }

        // ── 清空当前聊天对话：仅清对话消息，文档/附件/模板状态不受影响 ──
        async function clearConversation() {
            if (isStreaming) {
                showToast('正在生成中，请先暂停生成（⏸）再清空对话', 'info');
                return;
            }
            if (!confirm('确认清空当前聊天的所有对话内容？\n\n'
                + '· 仅清除对话消息；已生成的文档内容、附件、模板不受影响\n'
                + '· Agent 将丢失本轮对话上下文（文档状态仍在）\n'
                + '· 此操作不可撤销')) return;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/messages`, { method: 'DELETE' });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || '清空失败');
                const area = document.getElementById('chatArea');
                area.innerHTML = `<div class="empty-state">
                    <h3>👋 你好！我是设计开发文档写作助手</h3>
                    <p>我会按 SOP 流程引导你完成贴敷式胰岛素泵<br>设计开发阶段文档的编写。</p>
                    <p style="margin-top:12px;color:#bbb">你可以随时提问、跳过、或调整顺序。<br>输一条消息开始吧。</p>
                </div>`;
                // 重置流式相关状态
                chatReasoningDiv = null; _reasoningBuf = '';
                resetTypewriter();
                const bar = document.getElementById('agentStatusBar');
                if (bar) bar.style.display = 'none';
                showToast(data.cleared ? `✓ 已清空 ${data.cleared} 条对话消息` : '当前没有对话内容', 'success');
                fetchState();
                loadChatList();
            } catch (e) {
                showError('清空对话失败: ' + e.message);
            }
        }

        async function recallMessage(userMsgDiv, btn) {
            const area = document.getElementById('chatArea');
            const allChildren = Array.from(area.children);
            const msgIndex = allChildren.indexOf(userMsgDiv);
            if (msgIndex === -1) return;

            // 确认撤回（避免误触丢失 Agent 回复）
            if (!confirm('确认撤回此消息及其后的所有内容？')) return;

            // 若 Agent 正在生成，先中止当前 SSE 流
            if (isStreaming && currentAbortController) {
                try { currentAbortController.abort(); } catch (e) { /* ignore */ }
            }

            // 调用后端 checkpoint 回滚 API
            btn.textContent = '⏳ 撤回中...';
            btn.disabled = true;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/recall`, { method: 'POST' });
                const data = await resp.json();
                if (!resp.ok) {
                    console.warn('后端撤回失败:', data.detail || data.message);
                    // 即使后端失败，前端仍继续清理 DOM（至少视觉上撤回）
                }
            } catch (e) {
                console.warn('后端撤回请求异常:', e);
                // 网络错误时继续前端清理
            }

            // 移除审批条（若存在）
            const approvalBar = document.getElementById('approvalBar');
            if (approvalBar) approvalBar.remove();

            // 从该用户消息起，倒序移除所有后续元素
            for (let i = allChildren.length - 1; i >= msgIndex; i--) {
                allChildren[i].remove();
            }

            // 重置流式状态，允许用户重新发送
            isStreaming = false;
            currentAbortController = null;
            waitingApproval = null;
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('pauseBtn').style.display = 'none';

            // 若聊天区已空，恢复空状态提示
            if (!area.children.length) {
                area.innerHTML = `<div class="empty-state">
                    <h3>👋 你好！我是设计开发文档写作助手</h3>
                    <p>我会按 SOP 流程引导你完成贴敷式胰岛素泵<br>设计开发阶段文档的编写。</p>
                    <p style="margin-top:12px;color:#bbb">你可以随时提问、跳过、或调整顺序。<br>输一条消息开始吧。</p>
                </div>`;
            }
        }

        function toolLabel(tool) {
            if (tool === 'search_kb') return '检索知识库';
            if (tool === 'search_attachment') return '检索附件';
            if (tool === 'generate_section') return '生成章节';
            if (tool === 'modify_attachment') return '修改附件';
            if (tool === 'enrich_attachment') return '补充附件';
            if (tool === 'summarize_attachment') return '精简附件';
            if (tool === 'revise_section') return '修改章节';
            if (tool === 'revise_paragraph') return '修改段落';
            if (tool === 'build_docx') return '构建文档';
            if (tool === 'design_outline' || tool === 'outline_from_attachment') return '设计文档框架';
            if (tool === 'write_chapter') return '编写章节';
            if (tool === 'summarize_section' || tool === 'summarize_document') return '精简章节';
            if (tool === 'viking_find') return '检索历史记忆';
            if (tool === 'viking_search') return '搜索当前会话记忆';
            if (tool === 'viking_read') return '读取记忆详情';
            if (tool === 'viking_store') return '保存记忆';
            if (tool === 'viking_add_resource') return '添加记忆资源';
            if (tool === 'sql_db_list_tables') return '查询数据库表';
            if (tool === 'sql_db_schema') return '查看数据库表结构';
            if (tool === 'sql_db_query') return '执行数据库查询';
            if (tool === 'pgsql_list_tables') return '查询PG库表';
            if (tool === 'pgsql_schema') return '查看PG库表结构';
            if (tool === 'pgsql_query') return '执行PG库查询';
            return '处理';
        }

        function appendThinkingIndicator() {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'tool-indicator';
            div.id = 'thinking-indicator';
            div.innerHTML = `<div class="spinner"></div>🤔 Agent 正在思考...`;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return div;
        }

        function removeThinkingIndicator() {
            const el = document.getElementById('thinking-indicator');
            if (el) el.remove();
        }

        function appendToolIndicator(tool, isStart) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'tool-indicator';
            div.id = `tool-${tool}`;
            const label = toolLabel(tool);
            if (isStart) {
                div.innerHTML = `<div class="spinner"></div>🔧 Agent 正在${label}...`;
            } else {
                div.innerHTML = `<div class="icon">✅</div>${label}完成`;
            }
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return div;
        }

        // ── OpenViking 记忆活动指示器 ──
        // recall_start/done: 自动检索历史记忆（done 携带召回内容摘要，展开可查看）；
        // capture: 对话存入记忆；openviking_tool: LLM 主动调用 viking_* 工具
        function appendOpenVikingIndicator(kind, data) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'tool-indicator ov-indicator';
            if (kind === 'recall_start') {
                div.id = 'ov-recall';
                div.innerHTML = `<div class="spinner"></div>🧠 OpenViking 正在检索历史记忆...`;
            } else if (kind === 'recall_done') {
                let el = document.getElementById('ov-recall');
                if (el) {
                    // 移除 spinner，替换为完成态
                    el.innerHTML = '';
                    el.className = 'ov-recall-box';
                } else {
                    el = div;
                    el.className = 'ov-recall-box';
                }
                const memories = data.memories || [];
                const count = data.count || memories.length;
                let html = '';
                if (count > 0 && memories.length > 0) {
                    html = `<div class="rag-header" onclick="this.parentElement.classList.toggle('collapsed')">
                        <span>🧠 OpenViking 已召回 ${count} 条相关历史记忆</span>
                        <span class="rag-toggle">▼</span>
                    </div><div class="rag-body">`;
                    memories.forEach((m, i) => {
                        const scorePct = (m.score * 100).toFixed(1);
                        html += `<div class="rag-item">
                            <div class="rag-item-header">#${i + 1} · 相关度: ${scorePct}%</div>
                            <div class="rag-item-content">${escapeHtml(m.text)}</div>
                        </div>`;
                    });
                    html += '</div>';
                } else if (count > 0) {
                    html = `<div class="icon">🧠</div>OpenViking 已召回 ${count} 条相关历史记忆`;
                } else {
                    html = `<div class="icon">🧠</div>OpenViking 历史记忆检索完成（无高相关记忆）`;
                }
                el.innerHTML = html;
                if (el !== div) return el;
            } else if (kind === 'capture') {
                div.innerHTML = `<div class="icon">💾</div>OpenViking 已存档本轮对话（${data.count} 条消息）`;
            } else if (kind === 'tool') {
                div.innerHTML = `<div class="spinner"></div>🧠 OpenViking 工具调用: ${toolLabel(data.tool)}...`;
                div.id = `ov-tool-${data.tool}`;
            }
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return div;
        }

        // ── PostgreSQL 长期记忆活动指示器 ──
        // recall_start/done: 自动语义检索跨会话长期记忆（done 携带召回内容摘要，展开可查看）；
        // capture: 本轮对话已自动沉淀为长期记忆
        function appendLtmIndicator(kind, data) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'tool-indicator ltm-indicator';
            const typeLabels = { semantic: '语义事实', episodic: '情景经历', procedural: '流程规则' };
            if (kind === 'recall_start') {
                div.id = 'ltm-recall';
                div.innerHTML = `<div class="spinner"></div>🗄️ 正在检索长期记忆...`;
            } else if (kind === 'recall_done') {
                let el = document.getElementById('ltm-recall');
                if (el) {
                    // 移除 spinner，替换为完成态
                    el.innerHTML = '';
                    el.className = 'ltm-recall-box';
                } else {
                    el = div;
                    el.className = 'ltm-recall-box';
                }
                const memories = data.memories || [];
                const count = data.count || memories.length;
                let html = '';
                if (count > 0 && memories.length > 0) {
                    html = `<div class="rag-header" onclick="this.parentElement.classList.toggle('collapsed')">
                        <span>🗄️ 长期记忆已召回 ${count} 条相关记忆</span>
                        <span class="rag-toggle">▼</span>
                    </div><div class="rag-body">`;
                    memories.forEach((m, i) => {
                        const scorePct = ((m.score || 0) * 100).toFixed(1);
                        const tLabel = typeLabels[m.type] || m.type || '记忆';
                        html += `<div class="rag-item">
                            <div class="rag-item-header">#${i + 1} · ${tLabel} · 相关度: ${scorePct}%</div>
                            <div class="rag-item-content">${escapeHtml(m.text)}</div>
                        </div>`;
                    });
                    html += '</div>';
                } else if (count > 0) {
                    html = `<div class="icon">🗄️</div>长期记忆已召回 ${count} 条相关记忆`;
                } else {
                    html = `<div class="icon">🗄️</div>长期记忆检索完成（无高相关记忆）`;
                }
                el.innerHTML = html;
                if (el !== div) return el;
            } else if (kind === 'capture') {
                div.innerHTML = `<div class="icon">🗄️</div>本轮对话已沉淀 ${data.count} 条长期记忆`;
            }
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return div;
        }

        function appendRagResults(data) {
            // 性能治理：①默认折叠+懒渲染（点开才把结果内容写进 DOM）
            // ②只保留最近 3 个检索结果框——文档生成期逐小节检索会连续插入几十个
            // 全量结果框，DOM 无限膨胀导致页面卡顿，旧框自动清理
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'rag-results-box collapsed';
            const label = data.tool === 'search_attachment' ? '附件检索' : '知识库检索';
            const header = document.createElement('div');
            header.className = 'rag-header';
            header.innerHTML = `<span>📚 ${label}结果: 「${escapeHtml(data.query)}」 (${data.count}条)</span><span class="rag-toggle">▼</span>`;
            const body = document.createElement('div');
            body.className = 'rag-body';
            header.onclick = function () {
                if (body.style.display !== 'block') {
                    if (!body.childElementCount) _renderRagBody(body, data);  // 懒渲染：首次展开才构建
                    body.style.display = 'block';
                    div.classList.remove('collapsed');
                } else {
                    body.style.display = 'none';
                    div.classList.add('collapsed');
                }
            };
            div.appendChild(header);
            div.appendChild(body);
            area.appendChild(div);
            const boxes = area.querySelectorAll('.rag-results-box');
            if (boxes.length > 3) boxes[0].remove();
            scheduleChatScroll();
            return div;
        }

        function _renderRagBody(body, data) {
            const frag = document.createDocumentFragment();
            data.results.forEach((r, i) => {
                const item = document.createElement('div');
                item.className = 'rag-item';
                const h = document.createElement('div');
                h.className = 'rag-item-header';
                h.textContent = `#${i + 1} · 来源: ${r.source} · 相关度: ${(r.score * 100).toFixed(1)}%`;
                const c = document.createElement('div');
                c.className = 'rag-item-content';
                c.textContent = r.content;
                item.appendChild(h);
                item.appendChild(c);
                frag.appendChild(item);
            });
            body.appendChild(frag);
        }

        function escapeHtml(text) {
            const d = document.createElement('div');
            d.textContent = text;
            return d.innerHTML;
        }

        function showApprovalButtons(data) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'approval-bar';
            div.id = 'approvalBar';
            div.innerHTML = `
                <button class="btn-approve" onclick="resumeAgent('approve')">✓ 确认生成</button>
                <button class="btn-edit" onclick="editAndResume()">✎ 修改指令</button>
                <button class="btn-reject" onclick="resumeAgent('reject')">✗ 跳过</button>
            `;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            waitingApproval = data;
        }

        function showDownloadButton(downloadId, filename, sizeBytes) {
    const area = document.getElementById('chatArea');
    const div = document.createElement('div');
    div.className = 'download-box';
    div.id = 'downloadBox';
    const sizeKB = (sizeBytes / 1024).toFixed(1);
    div.innerHTML = `
        <div class="dl-icon">📄</div>
        <div class="dl-info">
            <strong>${filename}</strong>
            <div class="dl-size">${sizeKB} KB</div>
        </div>
        <button onclick="downloadDocx('${downloadId}')">下载文档</button>
    `;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function downloadDocx(downloadId) {
    _agentDownload(AGENT_BASE + '/api/agent/download/' + downloadId);
}

async function showQuickDownloadBox() {
    // Don't add duplicate download boxes
    if (document.getElementById('quickDownloadBox')) return;
    // 文档类型在对话过程中才确定，这里实时拉取一次，决定是否显示「下载 Excel」按钮
    await refreshCurrentDocType();
    const area = document.getElementById('chatArea');
    const div = document.createElement('div');
    div.className = 'download-box';
    div.id = 'quickDownloadBox';
    div.innerHTML = `
        <div class="dl-icon">📄</div>
        <div class="dl-info">
            <strong>${currentDocLabel || '文档'}.${RISK_EXCEL_DOC_TYPES.includes(currentDocType) ? 'xlsx' : 'docx'}</strong>
            <div class="dl-size">点击按钮下载已生成的文档</div>
        </div>
        <button onclick="downloadDocument()">下载文档</button>
        ${RISK_EXCEL_DOC_TYPES.includes(currentDocType) ? `<button onclick="downloadRiskExcel()" style="background:#388e3c">下载 Excel</button>` : ''}
    `;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

async function refreshCurrentDocType() {
    try {
        const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/state`);
        const data = await resp.json();
        if (data.success) {
            const docType = data.state?.document_generation?.doc_type || '';
            if (docType) currentDocType = docType;
        }
    } catch (e) { /* 静默失败，沿用 currentDocType */ }
    // 同步更新顶部「下载 Excel」链接可见性
    const link = document.getElementById('downloadExcelLink');
    if (link) {
        link.style.display = RISK_EXCEL_DOC_TYPES.includes(currentDocType) ? 'inline' : 'none';
    }
    return currentDocType;
}

function editAndResume() {
            const instruction = prompt('请输入修改后的生成指令:', '');
            if (instruction) {
                resumeAgent('edit:' + instruction);
            }
        }

        function downloadDocument() {
            // 常驻入口（同「下载修改版」模式）：无已生成章节时给提示，避免点击后打开空错误页
            if (!(window._generatedSections || []).length) {
                showToast('暂无已生成的文档，请先生成章节内容', 'info');
                return;
            }
            _agentDownload(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/download');
        }

        function downloadRiskExcel() {
            _agentDownload(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/download-excel');
        }

        // 固定「下载修改版」入口：下载最近一次修改/补全/精简的附件文档
        async function downloadLatestModified() {
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/modified-documents`);
                const data = await resp.json();
                if (!data.success || !data.modifications || data.modifications.length === 0) {
                    showToast('暂无修改/补全/精简的文档结果，请先通过「修改文档」处理一篇文档', 'info');
                    return;
                }
                const latest = data.modifications[data.modifications.length - 1];
                _agentDownload(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/modified-documents/${encodeURIComponent(latest.file_id)}/download`);
            } catch (e) {
                showToast('获取修改结果失败: ' + e.message, 'error');
            }
        }

        // ========== 精简文档功能 ==========
        function showSummarizeDialog() {
            // 动态填充章节列表
            const sel = document.getElementById('sumRange');
            sel.innerHTML = '<option value="">全部章节</option>';
            const sections = window._generatedSections || [];
            sections.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                sel.appendChild(opt);
            });
            document.getElementById('summarizeDialog').style.display = 'flex';
            onSumModeChange();
        }

        function closeSummarizeDialog() {
            document.getElementById('summarizeDialog').style.display = 'none';
        }

        // ========== 修改上传文档功能 ==========
        function openModifyDialog(fileId, filename) {
            document.getElementById('modFileId').value = fileId;
            document.getElementById('modFileName').value = filename || '';
            document.getElementById('modInstruction').value = '';
            document.getElementById('modifyDialog').style.display = 'flex';
            setTimeout(() => document.getElementById('modInstruction').focus(), 50);
        }

        function closeModifyDialog() {
            document.getElementById('modifyDialog').style.display = 'none';
        }

        async function submitModify() {
            const fileId = document.getElementById('modFileId').value;
            const filename = document.getElementById('modFileName').value;
            const instruction = document.getElementById('modInstruction').value.trim();
            if (!instruction) { alert('请输入修改指令'); return; }
            closeModifyDialog();
            // 注入聊天消息，由 Agent 通过 modify_attachment 工具处理
            const input = document.getElementById('userInput');
            input.value = `请修改附件「${filename}」：${instruction}`;
            sendMessage();
        }

        // ========== 补充文档功能 ==========
        function showEnrichDialog() {
            // 动态填充「已上传附件」下拉框
            const sel = document.getElementById('enrichExistingSelect');
            sel.innerHTML = '<option value="">— 从已上传附件中选择（可选）—</option>';
            (uploadedFiles || []).forEach(f => {
                if (f.status !== 'completed' || !f.file_id) return;
                const opt = document.createElement('option');
                opt.value = f.file_id;
                opt.textContent = f.filename || f.file_id;
                sel.appendChild(opt);
            });
            // 重置字段
            document.getElementById('enrichFileInput').value = '';
            document.getElementById('enrichFileName').textContent = '未选择文件';
            sel.value = '';
            document.getElementById('enrichInstruction').value = '';
            document.getElementById('enrichDialog').style.display = 'flex';
            setTimeout(() => document.getElementById('enrichInstruction').focus(), 50);
        }

        function closeEnrichDialog() {
            document.getElementById('enrichDialog').style.display = 'none';
        }

        function handleEnrichFileSelect(event) {
            const file = event.target.files && event.target.files[0];
            if (!file) return;
            document.getElementById('enrichFileName').textContent = file.name;
            // 选择了新上传文件后，清空「已上传附件」选择
            document.getElementById('enrichExistingSelect').value = '';
        }

        function onEnrichExistingChange(value) {
            if (value) {
                // 选择了已上传附件后，清空「上传新文档」选择
                document.getElementById('enrichFileInput').value = '';
                document.getElementById('enrichFileName').textContent = '未选择文件';
            }
        }

        async function submitEnrich() {
            const instruction = document.getElementById('enrichInstruction').value.trim();

            // 1) 优先：上传新文档
            const fileInput = document.getElementById('enrichFileInput');
            let fileId = null;
            let filename = null;

            if (fileInput.files && fileInput.files.length > 0) {
                const file = fileInput.files[0];
                filename = file.name;
                closeEnrichDialog();
                fileId = await uploadFile(file, true);
                if (!fileId) {
                    // 上传失败已在 uploadFile 内提示
                    showEnrichDialog();
                    return;
                }
            } else {
                // 2) 其次：从已上传附件中选择
                const existingId = document.getElementById('enrichExistingSelect').value;
                if (existingId) {
                    const f = (uploadedFiles || []).find(x => x.file_id === existingId);
                    if (!f) { alert('未找到所选附件，请重新选择'); return; }
                    fileId = f.file_id;
                    filename = f.filename || f.file_id;
                }
            }

            if (!fileId || !filename) {
                alert('请先上传新文档，或从已上传附件中选择一篇文档');
                return;
            }

            closeEnrichDialog();

            if (instruction) {
                // 用户已填写处理需求：直接交由 Agent 处理
                const input = document.getElementById('userInput');
                input.value = `请处理附件「${filename}」，处理需求：${instruction}`;
                sendMessage();
            } else {
                // 用户未填写需求：解析完成后追加引导消息，让用户明确选择处理方式
                appendMessage('agent',
                    `文档「${filename}」已解析完成。请告诉我是要 **修改**、**精简** 还是 **补全**，以及具体需求。`);
            }
        }

        function showModifiedDownloadButton(data) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'download-box';
            div.id = 'modifiedDownloadBox_' + (data.file_id || 'x');
            if (document.getElementById(div.id)) return; // 去重
            const kindLabels = {
                modify: { noun: '修改版', done: '修改完成', action: '下载修改版', suffix: '修改后' },
                enrich: { noun: '补全版', done: '补充完成', action: '下载补全版', suffix: '补充后' },
                summarize: { noun: '精简版', done: '精简完成', action: '下载精简版', suffix: '精简后' },
            };
            const k = kindLabels[data.kind] || kindLabels.modify;
            const summaryHtml = (data.summary || '').replace(/\n/g, '<br>');
            div.innerHTML = `
                <div class="dl-icon">📝</div>
                <div class="dl-info">
                    <strong>${escapeHtml(data.filename || (k.noun + '文档'))}</strong>
                    <div class="dl-size">${k.done}${data.modified_chars ? ' · ' + k.suffix + ' ' + data.modified_chars + ' 字符' : ''}</div>
                    ${summaryHtml ? `<div class="dl-summary">${summaryHtml}</div>` : ''}
                </div>
                <button onclick="downloadModifiedDoc('${data.file_id || ''}')">${k.action}</button>
            `;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
        }

        function downloadModifiedDoc(fileId) {
            if (!fileId) { alert('缺少附件ID，无法下载'); return; }
            _agentDownload(AGENT_BASE + '/api/agent/projects/' + PROJECT_ID + '/modified-documents/' + fileId + '/download');
        }

        function onSumModeChange() {
            const mode = document.getElementById('sumMode').value;
            const label = document.getElementById('sumTargetLabel');
            const input = document.getElementById('sumTarget');
            if (mode === 'ratio') {
                label.textContent = '压缩比例 (0.1-1.0，0.5 表示压缩到 50%)';
                input.type = 'number';
                input.value = 0.5;
                input.step = '0.1';
                input.min = '0.1';
                input.max = '1.0';
            } else {
                label.textContent = '目标字数 (每章目标字数，按小节比例分配)';
                input.type = 'number';
                input.value = 2000;
                input.step = '100';
                input.min = '200';
                input.max = '20000';
            }
        }

        async function startSummarize() {
            const mode = document.getElementById('sumMode').value;
            const target = parseFloat(document.getElementById('sumTarget').value);
            const sectionName = document.getElementById('sumRange').value;

            // 参数校验
            if (mode === 'ratio' && (target < 0.1 || target > 1.0)) {
                alert('比例模式下 target 应在 0.1~1.0 之间');
                return;
            }
            if (mode === 'words' && (target < 200)) {
                alert('字数模式下 target 应不小于 200');
                return;
            }

            closeSummarizeDialog();

            // 在聊天区显示精简任务开始
            const summaryLabel = sectionName ? `章节「${sectionName}」` : '全部章节';
            const modeLabel = mode === 'ratio' ? `压缩到 ${target * 100}%` : `每章目标 ${target} 字`;
            appendMessage('user', `✂️ 精简文档：${summaryLabel}，模式：${modeLabel}`);

            const agentDiv = appendMessage('agent', `<div>⏳ 精简任务启动中...</div>`);
            document.getElementById('summarizeBtn').disabled = true;

            try {
                const formData = new FormData();
                formData.append('mode', mode);
                formData.append('target', target);
                formData.append('section_name', sectionName);

                const response = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/summarize`, {
                    method: 'POST',
                    body: formData,
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let progressHtml = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        let data;
                        try { data = JSON.parse(line.slice(6)); } catch (e) { continue; }

                        switch (data.type) {
                            case 'start':
                                progressHtml = `<div style="margin-bottom:8px">📋 精简任务已启动</div>` +
                                    `<div style="font-size:12px;color:#666;margin-bottom:6px">模式: ${data.mode} | 总章节: ${data.total_sections} | 每章目标: ${data.per_section_target}</div>` +
                                    `<div id="sumProgressList"></div>`;
                                agentDiv.innerHTML = progressHtml;
                                break;

                            case 'section_start':
                                const list = document.getElementById('sumProgressList');
                                if (list) {
                                    const item = document.createElement('div');
                                    item.id = `sum-prog-${data.index}`;
                                    item.style.cssText = 'padding:4px 0;font-size:12px;color:#555';
                                    item.innerHTML = `<span style="color:#999">[${data.index}/${data.total}]</span> ⏳ 正在精简「${data.section_name}」...`;
                                    list.appendChild(item);
                                }
                                break;

                            case 'section_done':
                                const item = document.getElementById(`sum-prog-${data.index}`);
                                if (item) {
                                    const ratio = data.orig_chars > 0 ? Math.round(data.new_chars / data.orig_chars * 100) : 0;
                                    const icon = data.status === 'ok' ? '✅' : '⚠️';
                                    const subInfo = data.subsections_count > 0
                                        ? `（${data.success_count}/${data.subsections_count} 小节成功）`
                                        : '';
                                    item.innerHTML = `<span style="color:#999">[${data.index}/${data.total}]</span> ${icon} 「${data.section_name}」 ${data.orig_chars}→${data.new_chars} 字 (${ratio}%) ${subInfo}`;
                                    item.style.color = data.status === 'ok' ? '#2e7d32' : '#d32f2f';
                                }
                                break;

                            case 'done':
                                const totalRatio = data.total_orig_chars > 0
                                    ? Math.round(data.total_new_chars / data.total_orig_chars * 100)
                                    : 0;
                                agentDiv.innerHTML += `<div style="margin-top:10px;padding:8px;background:#e8f5e9;border-radius:6px;font-size:13px">` +
                                    `🎉 精简完成！${data.success_count}/${data.total_sections} 章节成功，` +
                                    `总计 ${data.total_orig_chars} → ${data.total_new_chars} 字 (${totalRatio}%)` +
                                    `</div>`;
                                break;

                            case 'error':
                                agentDiv.innerHTML += `<div style="margin-top:8px;padding:6px;background:#ffebee;color:#c62828;border-radius:4px;font-size:12px">❌ ${data.message}</div>`;
                                break;
                        }
                        document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
                    }
                }
            } catch (e) {
                agentDiv.innerHTML += `<div style="color:#c62828;font-size:12px;margin-top:8px">❌ 精简请求失败: ${e.message}</div>`;
            } finally {
                document.getElementById('summarizeBtn').disabled = false;
                // 刷新状态以反映精简后的章节内容
                setTimeout(() => fetchState(), 500);
            }
        }

        function showError(msg) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'error-msg';
            div.textContent = '⚠ ' + msg;
            // 出错时引导重试：若有可重试的最近操作，附带一键重试按钮
            if (lastAction) {
                const retryBtn = document.createElement('button');
                retryBtn.className = 'retry-btn';
                retryBtn.textContent = '↻ 重试';
                retryBtn.title = '重新执行上一次操作';
                retryBtn.onclick = () => { div.remove(); retryLastAction(); };
                div.appendChild(retryBtn);
            }
            area.appendChild(div);
        }

        // 一键重试：根据最近一次操作重新发起请求
        function retryLastAction() {
            if (isStreaming) return;
            if (lastAction === 'resume' && lastDecision != null) {
                resumeAgent(lastDecision);
            } else if (lastAction === 'send' && lastUserMessage != null) {
                sendMessage(lastUserMessage);
            }
        }

        // 兜底：将 LLM 偶尔输出的 HTML <table> 归一化为 Markdown 管道表格
        // （正常应已由 prompt 禁止 HTML 表格，此处作为前端保险）
        function htmlTableToMarkdown(text) {
            if (!text) return text;
            return text.replace(/<table[\s\S]*?<\/table>/gi, (tableBlock) => {
                const rows = [];
                const trRegex = /<tr[\s\S]*?<\/tr>/gi;
                let trMatch;
                while ((trMatch = trRegex.exec(tableBlock)) !== null) {
                    const cells = [];
                    const cellRegex = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
                    let cellMatch;
                    while ((cellMatch = cellRegex.exec(trMatch[1])) !== null) {
                        cells.push(cellMatch[1].replace(/<[^>]+>/g, '').trim());
                    }
                    if (cells.length) rows.push(cells);
                }
                if (!rows.length) return '';
                const colCount = rows[0].length;
                const lines = [
                    '| ' + rows[0].join(' | ') + ' |',
                    '| ' + rows[0].map(() => '---').join(' | ') + ' |',
                ];
                for (let i = 1; i < rows.length; i++) {
                    const row = rows[i];
                    while (row.length < colCount) row.push('');
                    lines.push('| ' + row.join(' | ') + ' |');
                }
                return '\n' + lines.join('\n') + '\n';
            });
        }

        function formatContent(text) {
            if (!text) return '';
            // 兜底：先把 HTML 表格转成 Markdown 管道表格
            text = htmlTableToMarkdown(text);
            // Basic markdown rendering
            let html = text
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>');
            // 代码块内的换行用哨兵保护，避免被下面的全局 \n→<br> 破坏
            // （否则 mermaid 源码会被拼成一行，渲染报 "Syntax error in text"）
            html = html.replace(/(<pre><code[^>]*>)([\s\S]*?)(<\/code><\/pre>)/g,
                (m, open, body, close) => open + body.replace(/\n/g, '\u0001') + close);
            html = html
                .replace(/^### (.+)$/gm, '<h4>$1</h4>')
                .replace(/^## (.+)$/gm, '<h3>$1</h3>')
                .replace(/^# (.+)$/gm, '<h2>$1</h2>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\n/g, '<br>')
                .replace(/^- (.+)$/gm, '• $1')
                .replace(/\|(.+)\|/g, (match) => {
                    if (match.includes('---')) return '';
                    const cells = match.split('|').filter(c => c.trim());
                    return '<br>' + cells.map(c => `<span style="padding:2px 8px;border:1px solid #ddd">${c.trim()}</span>`).join('') + '<br>';
                });
            // 恢复代码块内被保护的换行
            return html.replace(/\u0001/g, '\n');
        }

        // ── Mermaid 流程图渲染（对话内预览）──
        let _mmSeq = 0;
        async function renderMermaidIn(container) {
            if (typeof mermaid === 'undefined' || !container) return;
            const blocks = container.querySelectorAll('pre code.language-mermaid');
            if (!blocks.length) return;
            try { mermaid.initialize({ startOnLoad: false, theme: 'default' }); } catch (e) {}
            for (const code of blocks) {
                const src = (code.textContent || '').trim();
                if (!src) continue;
                try {
                    const id = 'mm-' + (++_mmSeq);
                    const { svg } = await mermaid.render(id, src);
                    const div = document.createElement('div');
                    div.className = 'mermaid-render';
                    div.innerHTML = svg;
                    const pre = code.closest('pre');
                    if (pre && pre.parentNode) pre.parentNode.replaceChild(div, pre);
                } catch (e) {
                    // 渲染失败：保留源码块，并清理 mermaid 10 残留在 body 上的错误元素
                    const errEl = document.getElementById(id);
                    if (errEl && errEl.parentNode) errEl.parentNode.removeChild(errEl);
                    document.querySelectorAll('#d' + id + ', body > svg[id="' + id + '"]').forEach(el => el.remove());
                }
            }
        }

        // ── 流程图编辑器（mermaid：生成 / 预览 / 修改 / 导出 / 插入文档）──
        let currentFlowchartMermaid = null;

        function showFlowchartDialog() {
            document.getElementById('flowchartDialog').classList.add('active');
            loadFlowchartSections();
        }
        function closeFlowchartDialog() {
            document.getElementById('flowchartDialog').classList.remove('active');
        }

        async function loadFlowchartSections() {
            const sel = document.getElementById('fcSection');
            sel.innerHTML = '<option value="">（新增独立「流程图」章节）</option>';
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/document`);
                if (!resp.ok) return;
                const data = await resp.json();
                const sections = data.sections || [];
                for (const s of sections) {
                    const opt = document.createElement('option');
                    opt.value = s.title;
                    opt.textContent = s.title;
                    sel.appendChild(opt);
                }
            } catch (e) { /* 无已生成章节时保持空列表 */ }
        }

        async function previewFlowchartMermaid(code) {
            const box = document.getElementById('fcPreview');
            if (!box) return;
            if (typeof mermaid === 'undefined' || !code) { box.innerHTML = ''; return; }
            try {
                mermaid.initialize({ startOnLoad: false, theme: 'default' });
                const id = 'fc-mmd-' + Date.now();
                const { svg } = await mermaid.render(id, code);
                box.innerHTML = svg;
            } catch (e) {
                box.innerHTML = '<div style="color:#c00;padding:12px">mermaid 渲染失败，请检查源码语法</div>';
            }
        }

        async function generateFlowchart() {
            const prompt = document.getElementById('fcPrompt').value.trim();
            if (!prompt) { alert('请输入流程描述'); return; }
            const btn = document.getElementById('btnGenerateFlowchart');
            btn.disabled = true; btn.textContent = '生成中...';
            try {
                const resp = await fetch(AGENT_BASE + '/api/agent/flowchart/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt }),
                });
                const data = await resp.json();
                if (!resp.ok || !data.success) { alert(data.detail || '生成失败'); return; }
                currentFlowchartMermaid = data.mermaid;
                document.getElementById('fcMermaid').value = currentFlowchartMermaid;
                await previewFlowchartMermaid(currentFlowchartMermaid);
                document.getElementById('fcEditorWrap').style.display = 'block';
            } catch (e) {
                alert('生成失败: ' + e.message);
            } finally {
                btn.disabled = false; btn.textContent = '生成流程图';
            }
        }

        async function reviseFlowchart() {
            const instruction = document.getElementById('fcRevise').value.trim();
            if (!instruction) { alert('请输入修改指令'); return; }
            const current = document.getElementById('fcMermaid').value.trim() || currentFlowchartMermaid;
            if (!current) { alert('请先生成流程图'); return; }
            const btn = document.getElementById('btnReviseFlowchart');
            btn.disabled = true; btn.textContent = '修改中...';
            try {
                const resp = await fetch(AGENT_BASE + '/api/agent/flowchart/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: instruction, current_mermaid: current }),
                });
                const data = await resp.json();
                if (!resp.ok || !data.success) { alert(data.detail || '修改失败'); return; }
                currentFlowchartMermaid = data.mermaid;
                document.getElementById('fcMermaid').value = currentFlowchartMermaid;
                document.getElementById('fcRevise').value = '';
                await previewFlowchartMermaid(currentFlowchartMermaid);
            } catch (e) {
                alert('修改失败: ' + e.message);
            } finally {
                btn.disabled = false; btn.textContent = 'AI 修改';
            }
        }

        async function exportFlowchartPng() {
            const code = document.getElementById('fcMermaid').value.trim() || currentFlowchartMermaid;
            if (!code) { alert('请先生成流程图'); return; }
            try {
                const resp = await fetch(AGENT_BASE + '/api/agent/flowchart/render', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mermaid: code }),
                });
                if (!resp.ok) {
                    const d = await resp.json().catch(() => ({}));
                    alert(d.detail || '导出失败'); return;
                }
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'flowchart.png';
                document.body.appendChild(a); a.click(); a.remove();
                URL.revokeObjectURL(url);
            } catch (e) {
                alert('导出失败: ' + e.message);
            }
        }

        async function insertFlowchart() {
            const code = document.getElementById('fcMermaid').value.trim() || currentFlowchartMermaid;
            if (!code) { alert('请先生成流程图'); return; }
            const sectionName = document.getElementById('fcSection').value;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/flowchart/insert`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mermaid: code, section_name: sectionName }),
                });
                const data = await resp.json();
                if (!resp.ok) { alert(data.detail || '插入失败'); return; }
                alert(data.message || '已插入文档');
                closeFlowchartDialog();
            } catch (e) {
                alert('插入失败: ' + e.message);
            }
        }

        const COLLAPSE_THRESHOLD = 500;  // chars

        function autoCollapseLongMessage(div) {
            const text = div.textContent || '';
            if (text.length <= COLLAPSE_THRESHOLD) return;

            div.classList.add('collapsed');
            const btn = document.createElement('span');
            btn.className = 'msg-toggle';
            btn.textContent = '▼ 展开全部';
            btn.onclick = function () {
                if (div.classList.contains('collapsed')) {
                    div.classList.remove('collapsed');
                    btn.textContent = '▲ 收起';
                } else {
                    div.classList.add('collapsed');
                    btn.textContent = '▼ 展开全部';
                }
            };
            div.insertAdjacentElement('afterend', btn);
        }

        // ── SSE ──
        async function sendMessage(retryText) {
            if (isStreaming) return;

            const input = document.getElementById('userInput');
            // retryText 传入非空值时表示「一键重试」，复用已显示的用户消息，不重复 append
            const isRetry = (retryText != null && retryText !== '');
            const message = isRetry ? retryText : input.value.trim();
            if (!message) return;

            if (!isRetry) {
                // Show user message
                appendMessage('user', message);
                input.value = '';
                input.style.height = 'auto';
                updateClearBtn();
            }

            // 记录最近操作，供出错时一键重试
            lastAction = 'send';
            lastUserMessage = message;
            lastDecision = null;

            // 新一轮生成：重置对话思维链容器与打字机
            resetChatReasoning();
            resetTypewriter();

            // Disable input during streaming
            isStreaming = true;
            document.getElementById('sendBtn').disabled = true;
            document.getElementById('pauseBtn').style.display = '';

            let agentDiv = null;
            let currentTool = null;
            let busyQueued = false;   // 遇到 busy 时置真，finally 里启动排队重发

            // 创建 AbortController，供撤回消息时中止流
            currentAbortController = new AbortController();

            // 思考中提示：Agent 尚未返回首个 token/工具调用前显示转圈
            let thinkingShown = true;
            appendThinkingIndicator();

            try {
                const formData = new FormData();
                formData.append('message', message);

                const response = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/messages`, {
                    method: 'POST',
                    body: formData,
                    signal: currentAbortController.signal,
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const data = JSON.parse(line.slice(6));
                        trackAgentStatus(data);

                        // 首个事件到达即结束「思考中」提示
                        if (thinkingShown) {
                            removeThinkingIndicator();
                            thinkingShown = false;
                        }

                        switch (data.type) {
                            case 'doc_token':
                                // 文档流式输出已下线：前端只保留对话正文与对话思维链
                                break;
                            case 'chat_reasoning':
                                appendChatReasoning(data.content);
                                break;
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                feedTypewriter(data.content, agentDiv);
                                document.getElementById('chatArea').scrollTop =
                                    document.getElementById('chatArea').scrollHeight;
                                break;
                            case 'context_compressed':
                                showToast('🧹 对话历史较长，已自动压缩较早内容以节省上下文', 'info');
                                break;

                            case 'tool_start':
                                currentTool = data.tool;
                                appendToolIndicator(data.tool, true);
                                break;

                            case 'openviking_recall_start':
                                appendOpenVikingIndicator('recall_start', data);
                                break;
                            case 'openviking_recall_done':
                                appendOpenVikingIndicator('recall_done', data);
                                break;
                            case 'openviking_capture':
                                appendOpenVikingIndicator('capture', data);
                                break;
                            case 'openviking_tool':
                                appendOpenVikingIndicator('tool', data);
                                break;
                            case 'ltm_recall_start':
                                appendLtmIndicator('recall_start', data);
                                break;
                            case 'ltm_recall_done':
                                appendLtmIndicator('recall_done', data);
                                break;
                            case 'ltm_capture':
                                appendLtmIndicator('capture', data);
                                break;

                            case 'tool_end':
                                if (currentTool) {
                                    const el = document.getElementById(`tool-${currentTool}`);
                                    if (el) {
                                        el.innerHTML = `<div class="icon">✅</div>${toolLabel(currentTool)}完成`;
                                    }
                                }
                                currentTool = null;
                                break;

                            case 'rag_results':
                                appendRagResults(data);
                                break;

                            case 'waiting_approval':
                                showApprovalButtons(data.interrupt_data);
                                break;

                            case 'done':
                                // Stream complete — auto-collapse if too long
                                flushTypewriter();
                                if (agentDiv) autoCollapseLongMessage(agentDiv);
                                break;

                            case 'file_ready':
                                showDownloadButton(data.download_id, data.filename, data.size_bytes);
                                break;

                            case 'modified_doc_ready':
                                showModifiedDownloadButton(data);
                                break;

                            case 'sections_ready':
                                showQuickDownloadBox();
                                break;

                            case 'error':
                                if (data.message && data.message.includes('正在进行的生成')) {
                                    busyQueued = true;
                                    showToast('⏳ 当前有任务正在生成，已为你排队，完成后自动发送这条消息', 'info', 5000);
                                } else {
                                    showError(data.message);
                                }
                                break;
                        }
                    }
                }
            } catch (err) {
                // 撤回触发的 abort 不算错误，静默处理
                if (err && err.name !== 'AbortError') {
                    showError('连接失败: ' + err.message);
                }
            } finally {
                removeThinkingIndicator();
                isStreaming = false;
                currentAbortController = null;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('pauseBtn').style.display = 'none';
                document.getElementById('userInput').focus();

                // Refresh state sidebar and attachments
                fetchState();
                fetchAttachments();
                fetchTemplates();

                // busy 排队重发：等当前生成结束后自动重发本条消息（不重复显示用户气泡）
                if (busyQueued) {
                    waitAndResendMessage(lastUserMessage);
                }
            }
        }

        // 排队重发：轮询项目流状态，当前生成结束后自动重新发送消息
        async function waitAndResendMessage(message) {
            for (let i = 0; i < 1600; i++) {   // 最长约 40 分钟
                await new Promise(r => setTimeout(r, 2000));
                try {
                    const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/stream/status`);
                    const st = await resp.json();
                    if (!st.active) {
                        showToast('⏳ 前序生成已完成，正在继续发送你的消息...', 'info', 4000);
                        // 作为 retryText 传入，复用一键重试逻辑（不重复 append 用户气泡）
                        sendMessage(message);
                        return;
                    }
                } catch (e) { /* 继续轮询 */ }
            }
            showError('排队等待超时，请重新发送。');
        }

        async function resumeAgent(decision) {
            if (isStreaming) return;

            // 记录最近操作，供出错时一键重试
            lastAction = 'resume';
            lastDecision = decision;

            // Remove approval bar
            const bar = document.getElementById('approvalBar');
            if (bar) bar.remove();

            isStreaming = true;
            document.getElementById('sendBtn').disabled = true;
            document.getElementById('pauseBtn').style.display = '';

            // 创建 AbortController，供撤回消息时中止流
            currentAbortController = new AbortController();

            // 思考中提示：继续处理（确认/跳过）后，Agent 返回首个事件前显示转圈
            let thinkingShown = true;
            appendThinkingIndicator();

            try {
                const formData = new FormData();
                formData.append('decision', decision);

                const response = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/resume`, {
                    method: 'POST',
                    body: formData,
                    signal: currentAbortController.signal,
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let agentDiv = null;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const data = JSON.parse(line.slice(6));
                        trackAgentStatus(data);

                        // 首个事件到达即结束「思考中」提示
                        if (thinkingShown) {
                            removeThinkingIndicator();
                            thinkingShown = false;
                        }

                        switch (data.type) {
                            case 'doc_token':
                                // 文档流式输出已下线：前端只保留对话正文与对话思维链
                                break;
                            case 'chat_reasoning':
                                appendChatReasoning(data.content);
                                break;
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                feedTypewriter(data.content, agentDiv);
                                break;
                            case 'context_compressed':
                                showToast('🧹 对话历史较长，已自动压缩较早内容以节省上下文', 'info');
                                break;
                            case 'tool_start':
                                appendToolIndicator(data.tool, true);
                                break;
                            case 'openviking_recall_start':
                                appendOpenVikingIndicator('recall_start', data);
                                break;
                            case 'openviking_recall_done':
                                appendOpenVikingIndicator('recall_done', data);
                                break;
                            case 'openviking_capture':
                                appendOpenVikingIndicator('capture', data);
                                break;
                            case 'openviking_tool':
                                appendOpenVikingIndicator('tool', data);
                                break;
                            case 'ltm_recall_start':
                                appendLtmIndicator('recall_start', data);
                                break;
                            case 'ltm_recall_done':
                                appendLtmIndicator('recall_done', data);
                                break;
                            case 'ltm_capture':
                                appendLtmIndicator('capture', data);
                                break;
                            case 'tool_end':
                                const el = document.getElementById(`tool-${data.tool}`);
                                if (el) el.querySelector('.spinner')?.remove();
                                break;
                            case 'rag_results':
                                appendRagResults(data);
                                break;
                            case 'done':
                                waitingApproval = null;
                                flushTypewriter();
                                if (agentDiv) autoCollapseLongMessage(agentDiv);
                                break;

                            case 'file_ready':
                                showDownloadButton(data.download_id, data.filename, data.size_bytes);
                                break;
                            case 'modified_doc_ready':
                                showModifiedDownloadButton(data);
                                break;
                            case 'sections_ready':
                                showQuickDownloadBox();
                                break;
                            case 'error':
                                showError(data.message);
                                break;
                        }
                    }
                }
            } catch (err) {
                showError('恢复失败: ' + err.message);
            } finally {
                removeThinkingIndicator();
                isStreaming = false;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('pauseBtn').style.display = 'none';
                fetchState();
                fetchAttachments();
                fetchTemplates();
            }
        }

        // ── Auto-generate ──
        function showAutoGenDialog() {
            document.getElementById('autoGenDialog').classList.add('active');
        }
        function closeAutoGenDialog() {
            document.getElementById('autoGenDialog').classList.remove('active');
        }

        async function startAutoGenerate() {
            if (isStreaming) return;

            const productName = document.getElementById('agProductName').value.trim();
            const classification = document.getElementById('agClassification').value.trim();
            const intendedUse = document.getElementById('agIntendedUse').value.trim();
            const docType = document.getElementById('agDocType').value;
            if (!productName) { alert('请输入产品名称'); return; }

            closeAutoGenDialog();
            // Clear chat and show starting message
            const area = document.getElementById('chatArea');
            area.innerHTML = '';
            appendMessage('agent', '⚡ 一键生成模式启动...<br><br>Agent将按SOP流程自动执行：<br>① 产品画像 → ② 标准/资料检索 → ③ 策划内容采集 → ④ 章节生成 → ⑤ 导出文档<br><br>请耐心等待，全程无需手动确认。');

            isStreaming = true;
            document.getElementById('sendBtn').disabled = true;
            document.getElementById('pauseBtn').style.display = '';
            document.getElementById('autoGenBtn').disabled = true;

            let agentDiv = null;
            try {
                const formData = new FormData();
                formData.append('product_name', productName);
                formData.append('product_classification', classification);
                formData.append('product_intended_use', intendedUse);
                formData.append('doc_type', docType);

                const response = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/auto-generate`, {
                    method: 'POST',
                    body: formData,
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const data = JSON.parse(line.slice(6));
                        trackAgentStatus(data);

                        switch (data.type) {
                            case 'doc_token':
                                // 文档流式输出已下线：前端只保留对话正文与对话思维链
                                break;
                            case 'chat_reasoning':
                                appendChatReasoning(data.content);
                                break;
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                feedTypewriter(data.content, agentDiv);
                                area.scrollTop = area.scrollHeight;
                                break;
                            case 'tool_start':
                                appendToolIndicator(data.tool, true);
                                break;
                            case 'openviking_recall_start':
                                appendOpenVikingIndicator('recall_start', data);
                                break;
                            case 'openviking_recall_done':
                                appendOpenVikingIndicator('recall_done', data);
                                break;
                            case 'openviking_capture':
                                appendOpenVikingIndicator('capture', data);
                                break;
                            case 'openviking_tool':
                                appendOpenVikingIndicator('tool', data);
                                break;
                            case 'ltm_recall_start':
                                appendLtmIndicator('recall_start', data);
                                break;
                            case 'ltm_recall_done':
                                appendLtmIndicator('recall_done', data);
                                break;
                            case 'ltm_capture':
                                appendLtmIndicator('capture', data);
                                break;
                            case 'tool_end':
                                const el = document.getElementById(`tool-${data.tool}`);
                                if (el) {
                                    el.innerHTML = `<div class="icon">✅</div>${toolLabel(data.tool)}完成`;
                                }
                                break;
                            case 'sections_ready':
                                showQuickDownloadBox();
                                break;
                            case 'file_ready':
                                showDownloadButton(data.download_id, data.filename, data.size_bytes);
                                break;
                            case 'modified_doc_ready':
                                showModifiedDownloadButton(data);
                                break;
                            case 'done':
                                flushTypewriter();
                                if (agentDiv) autoCollapseLongMessage(agentDiv);
                                break;
                            case 'error':
                                showError(data.message);
                                break;
                        }
                    }
                }
            } catch (err) {
                showError('一键生成失败: ' + err.message);
            } finally {
                isStreaming = false;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('pauseBtn').style.display = 'none';
                document.getElementById('autoGenBtn').disabled = false;
                fetchState();
                fetchAttachments();
                fetchTemplates();
            }
        }

        async function fetchState() {
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/state`);
                const data = await resp.json();
                if (data.success) {
                    renderSteps(data.state);
                    // 同步刷新侧边栏聊天任务列表（新任务发首条消息后会出现在列表中）
                    loadChatList();
                    // 文档风格选择：恢复当前项目的语言风格状态
                    writingStyle = data.state?.writing_style || 'concise';
                    setStyleSelectUI();
                    // Show review link if sections have been generated
                    // （下载文档入口已改为常驻，不再随状态隐藏）
                    const sections = data.state?.document_generation?.sections_generated || [];
                    const hasSections = sections.length > 0;
                    document.getElementById('reviewLink').style.display = hasSections ? 'inline' : 'none';
                    // 精简按钮：仅在有已生成章节时显示
                    document.getElementById('summarizeBtn').style.display = hasSections ? 'inline-block' : 'none';
                    // 缓存当前章节列表供精简对话框使用
                    window._generatedSections = sections;
                    // Capture current doc_type label for quick download box
                    const docType = data.state?.document_generation?.doc_type || 'design_development_plan';
                    const docLabels = {
                        'design_development_plan': '项目开发计划书',
                        'risk_management_plan': '风险管理计划',
                        'market_research_product_definition': '市场调研与产品定义报告',
                        'project_feasibility_study': '项目可行性研究报告',
                        'patent_analysis_report': '专利分析报告',
                        'project_approval_review': '立项评审记录',
                        'regulatory_strategy_document': '注册路径策略',
                    };
                    currentDocLabel = docLabels[docType] || '文档';
                    currentDocType = docType;
                    // 风险分析总表类文档显示「下载 Excel」入口
                    document.getElementById('downloadExcelLink').style.display =
                        (hasSections && RISK_EXCEL_DOC_TYPES.includes(docType)) ? 'inline' : 'none';
                }
            } catch (e) { /* Silently fail */ }
        }

        // ── 回退到上一次修改/生成/精简/附件修改之前 ──
        async function undoLast() {
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/undo`, { method: 'POST' });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || 'HTTP ' + resp.status);
                if (!data.success) {
                    showToast(data.message || '没有可回退的操作', 'info');
                    return;
                }
                // 清理被回退的附件修改/补全下载按钮（如有）
                const removedFileIds = data.removed_file_ids || [];
                removedFileIds.forEach(fid => {
                    const box = document.getElementById('modifiedDownloadBox_' + fid);
                    if (box) box.remove();
                });
                showToast(data.message || '已回退', 'success');
                fetchState();
                fetchAttachments();
            } catch (e) {
                showToast('回退失败: ' + e.message, 'error');
            }
        }

        // ── 文档语言风格选择 ──
        function setStyleSelectUI() {
            const sel = document.getElementById('styleSelect');
            if (sel) sel.value = writingStyle;
        }

        async function changeWritingStyle() {
            const sel = document.getElementById('styleSelect');
            const target = sel ? sel.value : writingStyle;
            const prev = writingStyle;
            writingStyle = target;        // 乐观更新 UI
            setStyleSelectUI();
            try {
                const formData = new FormData();
                formData.append('style', target);
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/mode`, {
                    method: 'POST',
                    body: formData,
                });
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                if (!data.success) throw new Error(data.detail || '设置失败');
                showToast(target === 'concise' ? '已切换为「精炼简洁」风格' : '已切换为「严谨详细」风格', 'success');
            } catch (e) {
                writingStyle = prev;      // 失败回滚
                setStyleSelectUI();
                showToast('文档风格设置失败: ' + e.message, 'error');
            }
        }

        // ── Knowledge Base Upload (独立上传到 upload 向量知识库) ──
        // 复用后端 POST /api/upload?persist=true + GET /api/extract-status/{file_id}，
        // 上传不绑定任何项目会话，入库后任意对话的 RAG 检索均可命中。
        const KB_MAX_SIZE_BYTES = 20 * 1024 * 1024;
        // 与后端 SUPPORTED_UPLOAD_FORMATS 保持一致（含 MinerU 启用时的扩展格式）
        const KB_ALLOWED_FORMATS = ['.docx', '.pdf', '.txt', '.doc', '.ppt', '.pptx', '.xls', '.xlsx',
            '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.html', '.htm'];

        function showToast(msg, type = 'info', duration = 4000) {
            const container = document.getElementById('toastContainer');
            const t = document.createElement('div');
            t.className = 'toast toast-' + (type === 'uploading' ? 'uploading' : type);
            if (type === 'uploading') {
                t.innerHTML = '<span class="toast-spinner"></span><span class="toast-text">' + escapeHtml(msg) + '</span>';
            } else {
                t.innerHTML = '<span class="toast-text">' + escapeHtml(msg) + '</span>';
                setTimeout(() => t.remove(), duration);
            }
            container.appendChild(t);
            return t;
        }

        function updateToast(el, msg) {
            const textEl = el.querySelector('.toast-text');
            if (textEl) textEl.textContent = msg;
        }

        function dismissToast(el) {
            if (el && el.parentNode) el.parentNode.removeChild(el);
        }

        function triggerKbUpload() {
            document.getElementById('kbFileInput').click();
        }

        async function handleKbFileSelect(event) {
            const files = Array.from(event.target.files || []);
            event.target.value = '';  // 允许重复选择同一文件
            if (!files.length) return;

            const btn = document.getElementById('kbUploadBtn');
            btn.disabled = true;
            let successCount = 0, failCount = 0;
            for (const file of files) {
                if (await uploadFileToKb(file)) successCount++; else failCount++;
            }
            btn.disabled = false;
            showToast(`知识库上传完成：成功 ${successCount} 个，失败 ${failCount} 个`,
                failCount ? 'error' : 'success', 6000);
        }

        function validateKbFile(file) {
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            if (!KB_ALLOWED_FORMATS.includes(ext)) {
                return `不支持的文件格式「${ext}」。支持: ${KB_ALLOWED_FORMATS.join(' ')}`;
            }
            if (file.size > KB_MAX_SIZE_BYTES) {
                return `文件「${file.name}」超过 20MB 限制 (${(file.size / 1024 / 1024).toFixed(1)}MB)`;
            }
            if (file.size === 0) {
                return '文件为空，请上传有效文件';
            }
            return '';
        }

        // ── 上传任务登记表（localStorage）：跨页面刷新/任务切换恢复进度 ──
        // 任务切换是整页刷新（location.href），内存中的轮询与进度 UI 会全部丢失；
        // 登记表记录进行中的上传任务，页面加载时恢复进度显示并续接轮询。
        const UPLOAD_REG_KEY = 'activeUploads_v1';

        function _loadUploadReg() {
            try { return JSON.parse(localStorage.getItem(UPLOAD_REG_KEY) || '[]'); }
            catch (e) { return []; }
        }
        function _saveUploadReg(list) {
            try { localStorage.setItem(UPLOAD_REG_KEY, JSON.stringify(list)); } catch (e) { /* ignore */ }
        }
        function registerUpload(entry) {
            const list = _loadUploadReg().filter(e => e.taskId !== entry.taskId);
            list.push(entry);
            _saveUploadReg(list);
        }
        function unregisterUpload(taskId) {
            _saveUploadReg(_loadUploadReg().filter(e => e.taskId !== taskId));
        }

        // ── 知识库上传进度卡片 ──
        function _kbCard() {
            let card = document.getElementById('kbUploadProgress');
            if (!card || !card.isConnected) {
                card = document.createElement('div');
                card.id = 'kbUploadProgress';
                card.className = 'upload-progress-card';
                card.innerHTML = '<div class="upc-title">📚 知识库上传进度</div><div class="upc-rows"></div>';
                const area = document.getElementById('chatArea');
                const empty = area.querySelector('.empty-state');
                if (empty) empty.remove();
                area.appendChild(card);
            }
            return card;
        }
        function _kbRow(taskId, filename) {
            const card = _kbCard();
            let row = document.getElementById('kbrow-' + taskId);
            if (!row) {
                row = document.createElement('div');
                row.id = 'kbrow-' + taskId;
                row.className = 'upc-row';
                row.innerHTML = `<span class="upc-name">📄 ${escapeHtml(filename)}</span>` +
                                `<span class="upc-stage">上传中...</span>`;
                card.querySelector('.upc-rows').appendChild(row);
            }
            return row;
        }
        function _kbRowUpdate(taskId, text, state) {
            const row = document.getElementById('kbrow-' + taskId);
            if (!row) return;
            const st = row.querySelector('.upc-stage');
            if (st) st.textContent = text;
            row.className = 'upc-row' + (state && state !== 'running' ? ' ' + state : '');
        }

        // ── 可恢复的轮询：知识库上传 ──
        async function pollKbUpload(taskId, filename, startedAt) {
            for (let i = 0; i < 1600; i++) {
                await new Promise(r => setTimeout(r, 1500));
                let st;
                try {
                    const resp = await fetch(AGENT_BASE + '/api/extract-status/' + taskId);
                    if (resp.status === 404) throw new Error('任务已丢失（服务可能重启）');
                    if (!resp.ok) throw new Error('查询状态失败');
                    st = await resp.json();
                } catch (e) {
                    _kbRowUpdate(taskId, `⚠ ${e.message}`, 'error');
                    showToast(`✗「${filename}」提取失败: ${e.message}`, 'error', 6000);
                    unregisterUpload(taskId);
                    return false;
                }
                if (st.status === 'failed') {
                    _kbRowUpdate(taskId, `✗ ${st.message || '提取失败'}`, 'error');
                    showToast(`✗「${filename}」提取失败: ${st.message || '原因未知'}`, 'error', 6000);
                    unregisterUpload(taskId);
                    return false;
                }
                if (st.status === 'completed') {
                    const msg = st.persisted
                        ? `✓ 已入库知识库（${st.char_count} 字符）`
                        : `✓ 提取完成（${st.char_count} 字符，未入库）`;
                    _kbRowUpdate(taskId, msg, 'done');
                    unregisterUpload(taskId);
                    return true;
                }
                const elapsed = Math.round((Date.now() - (startedAt || Date.now())) / 1000);
                _kbRowUpdate(taskId, `${st.message || '提取中'} · 已用 ${elapsed}s`, 'running');
            }
            // 超时≠失败：后台仍在提取，保留登记，刷新后自动恢复
            _kbRowUpdate(taskId, '⏳ 仍在后台提取（已超40分钟），完成后可刷新查看', 'running');
            return false;
        }

        // ── 可恢复的轮询：模板上传（完成后 finalize 写入 Agent 状态）──
        async function pollTemplateUpload(taskId, projectId, chipId, startedAt, signal) {
            for (let i = 0; i < 1600; i++) {
                if (signal && signal.aborted) {
                    unregisterUpload(taskId);
                    throw new DOMException('已取消', 'AbortError');
                }
                await new Promise(r => setTimeout(r, 1500));
                let st;
                try {
                    const resp = await fetch(AGENT_BASE + '/api/extract-status/' + taskId);
                    if (resp.status === 404) throw new Error('提取任务已丢失（服务可能重启），请重试');
                    if (!resp.ok) throw new Error('查询提取状态失败');
                    st = await resp.json();
                } catch (e) {
                    unregisterUpload(taskId);
                    throw e;
                }
                if (st.status === 'failed') {
                    unregisterUpload(taskId);
                    throw new Error(st.message || '提取失败');
                }
                // 更新 chip 的阶段与耗时
                const tEntry = templates.find(t => t.template_id === chipId || t.template_id === taskId);
                if (tEntry) {
                    tEntry.stage = st.message || '提取中';
                    tEntry.elapsed = Math.round((Date.now() - (startedAt || Date.now())) / 1000);
                    renderTemplateChips();
                }
                if (st.status === 'completed') {
                    const finResp = await fetch(`${AGENT_BASE}/api/agent/projects/${projectId}/templates/${taskId}/finalize`, { method: 'POST' });
                    const finData = await finResp.json().catch(() => ({}));
                    if (!finData.success) {
                        unregisterUpload(taskId);
                        throw new Error(finData.detail || '模板状态写入失败');
                    }
                    unregisterUpload(taskId);
                    templates = templates.filter(t => t.template_id !== chipId && t.template_id !== taskId);
                    templates.push({
                        template_id: taskId, name: finData.name, filename: finData.filename,
                        doc_type: finData.doc_type, char_count: finData.char_count, status: 'completed'
                    });
                    renderTemplateChips();
                    return true;
                }
            }
            // 超时≠失败：保留登记，刷新/切回后自动恢复并最终 finalize
            throw new Error('暂时提取超时（后台可能仍在提取中），无需重试上传；稍后刷新页面，已完成的模板会自动找回并显示');
        }

        // ── 页面加载时恢复进行中的上传（进度 UI + 续接轮询）──
        async function restoreActiveUploads() {
            const reg = _loadUploadReg();
            for (const e of reg) {
                // 模板任务只在其所属项目页面恢复；知识库任务全局，任意页面恢复
                if (e.type === 'template' && e.projectId && e.projectId !== PROJECT_ID) continue;
                let st;
                try {
                    const resp = await fetch(AGENT_BASE + '/api/extract-status/' + e.taskId);
                    if (resp.status === 404) { unregisterUpload(e.taskId); continue; }
                    if (!resp.ok) continue;  // 网络问题：保留登记，下次再试
                    st = await resp.json();
                } catch (err) { continue; }

                if (st.status === 'completed') {
                    if (e.type === 'template') {
                        try {
                            const finResp = await fetch(`${AGENT_BASE}/api/agent/projects/${e.projectId}/templates/${e.taskId}/finalize`, { method: 'POST' });
                            const finData = await finResp.json().catch(() => ({}));
                            if (finData.success) {
                                await fetchTemplates();
                                showToast(`✓ 模板「${finData.name || e.filename}」已恢复并完成`, 'success', 4000);
                            }
                        } catch (err) { /* finalize 失败保留登记，下次再试 */ continue; }
                    } else {
                        showToast(`✓「${e.filename}」已入库知识库（${st.char_count || 0} 字符）`, 'success', 5000);
                    }
                    unregisterUpload(e.taskId);
                } else if (st.status === 'failed') {
                    showToast(`「${e.filename}」处理失败: ${st.message || ''}`, 'error', 6000);
                    unregisterUpload(e.taskId);
                } else {
                    // 仍在处理 → 恢复进度 UI 并续接轮询
                    if (e.type === 'template') {
                        if (!templates.some(t => t.template_id === e.taskId)) {
                            templates.push({
                                template_id: e.taskId, name: e.name || e.filename,
                                filename: e.filename, doc_type: e.docType || '',
                                char_count: 0, status: 'uploading',
                            });
                        }
                        renderTemplateChips();
                        pollTemplateUpload(e.taskId, e.projectId, e.taskId, e.startedAt)
                            .catch(err => {
                                templates = templates.filter(t => t.template_id !== e.taskId);
                                renderTemplateChips();
                                if (err && err.message) showToast(`模板「${e.filename}」: ${err.message}`, 'error', 6000);
                            });
                    } else {
                        _kbRow(e.taskId, e.filename);
                        _kbRowUpdate(e.taskId, `${st.message || '提取中'}（已恢复进度跟踪）`, 'running');
                        pollKbUpload(e.taskId, e.filename, e.startedAt);
                    }
                }
            }
        }

        async function uploadFileToKb(file) {
            const err = validateKbFile(file);
            if (err) {
                showToast(err, 'error', 6000);
                return false;
            }
            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('persist', 'true');  // 独立入库 uploads 向量库

                const resp = await fetch(AGENT_BASE + '/api/upload', { method: 'POST', body: formData });
                if (!resp.ok) {
                    const errData = await resp.json().catch(() => ({}));
                    throw new Error(errData.detail || `上传失败 (HTTP ${resp.status})`);
                }
                const result = await resp.json();
                const taskId = result.file_id;
                const startedAt = Date.now();
                // 登记 + 进度卡片（跨刷新/任务切换可恢复）
                registerUpload({ type: 'kb', taskId, filename: file.name, startedAt });
                _kbRow(taskId, file.name);
                return await pollKbUpload(taskId, file.name, startedAt);
            } catch (e) {
                showToast(`✗「${file.name}」上传失败: ${e.message}`, 'error', 6000);
                return false;
            }
        }

        // ── KB Files List (查看知识库文件列表) ──
        // 跳转到知识库独立页面（携带当前 project 以便在知识库页面"批量添加附件"）
        function gotoKbPage() {
            window.open(_agentPageUrl(AGENT_BASE + '/kb?project=' + encodeURIComponent(PROJECT_ID)), '_blank');
        }

        async function showKbFilesDialog() {
            const overlay = document.getElementById('kbFilesDialog');
            overlay.classList.add('active');
            const content = document.getElementById('kbFilesContent');
            content.innerHTML = '<p style="color:#999;text-align:center;padding:20px">加载中...</p>';
            try {
                const resp = await fetch(AGENT_BASE + '/api/kb/files');
                if (!resp.ok) {
                    const errData = await resp.json().catch(() => ({}));
                    throw new Error(errData.detail || `请求失败 (HTTP ${resp.status})`);
                }
                const data = await resp.json();
                if (data.status !== 'ok') {
                    throw new Error(data.detail || '未知错误');
                }
                if (!data.files || data.files.length === 0) {
                    content.innerHTML = '<p style="color:#999;text-align:center;padding:40px">知识库中暂无文件，请先上传。</p>';
                    return;
                }
                let html = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
                html += '<thead><tr style="border-bottom:2px solid #e0e0e0;text-align:left;color:#666">';
                html += '<th style="padding:8px;width:32px;text-align:center"><input type="checkbox" id="kbSelectAll" onchange="toggleKbSelectAll(this)" title="全选/取消全选"></th>';
                html += '<th style="padding:8px">文件名</th>';
                html += '<th style="padding:8px;width:80px;text-align:right">分块数</th>';
                html += '<th style="padding:8px;width:130px;text-align:center">操作</th>';
                html += '</tr></thead><tbody>';
                for (const f of data.files) {
                    const hasOriginal = f.original_filename && f.original_filename !== f.source_file;
                    const displayName = hasOriginal ? f.original_filename : f.source_file;
                    const note = hasOriginal ? '' : ' <span style="color:#ff9800;font-size:11px">(旧文件，原始文件名已丢失)</span>';
                    html += '<tr style="border-bottom:1px solid #f0f0f0">';
                    html += `<td style="padding:8px;text-align:center"><input type="checkbox" class="kb-file-check" data-source="${escapeHtml(f.source_file)}" data-file-id="${escapeHtml(f.file_id || '')}" data-name="${escapeHtml(displayName)}" onchange="updateKbSelectAllState()"></td>`;
                    html += `<td style="padding:8px;word-break:break-all"><span>${escapeHtml(displayName)}</span>${note}</td>`;
                    html += `<td style="padding:8px;text-align:right;color:#888">${f.chunk_count}</td>`;
                    html += `<td style="padding:8px;text-align:center;white-space:nowrap"><button style="border:1px solid #00897b;background:#fff;color:#00897b;border-radius:4px;padding:3px 10px;font-size:12px;cursor:pointer;margin-right:4px" data-source="${escapeHtml(f.source_file)}" data-file-id="${escapeHtml(f.file_id || '')}" data-name="${escapeHtml(displayName)}" onclick="addKbFileToAttachment(this)" title="将该文件加入当前会话附件">添加</button><button style="border:1px solid #e57373;background:#fff;color:#e53935;border-radius:4px;padding:3px 10px;font-size:12px;cursor:pointer" data-source="${escapeHtml(f.source_file)}" data-name="${escapeHtml(displayName)}" onclick="deleteKbFile(this)" title="从知识库删除该文件">删除</button></td>`;
                    html += '</tr>';
                }
                html += '</tbody></table>';
                html += `<p style="font-size:11px;color:#999;margin-top:8px;display:flex;align-items:center;gap:8px">`
                    + `<span>共 ${data.files.length} 个文件，已选 <span id="kbSelectedCount">0</span> 个</span>`
                    + `<button id="kbBatchAddBtn" onclick="addSelectedKbFiles()" style="border:none;background:#00897b;color:#fff;border-radius:4px;padding:4px 12px;font-size:12px;cursor:pointer" title="将勾选的文件批量加入当前会话附件">批量添加到附件</button>`
                    + `</p>`;
                content.innerHTML = html;
            } catch (e) {
                content.innerHTML = `<p style="color:#e53935;text-align:center;padding:20px">加载失败: ${escapeHtml(e.message)}</p>`;
            }
        }

        function closeKbFilesDialog() {
            document.getElementById('kbFilesDialog').classList.remove('active');
        }

        // ── KB File Delete (从知识库删除文件) ──
        async function deleteKbFile(btn) {
            const sourceFile = btn.getAttribute('data-source');
            const displayName = btn.getAttribute('data-name') || sourceFile;
            if (!sourceFile) return;
            if (!confirm(`确定要从知识库删除「${displayName}」吗？\n删除后该文件内容将不再参与 RAG 检索。`)) return;
            btn.disabled = true;
            btn.textContent = '删除中...';
            try {
                const resp = await fetch(AGENT_BASE + '/api/kb/files/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_file: sourceFile }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    throw new Error(data.detail || `删除失败 (HTTP ${resp.status})`);
                }
                showToast(`✓ 已删除「${displayName}」`, 'success', 4000);
                showKbFilesDialog(); // 刷新列表
            } catch (e) {
                btn.disabled = false;
                btn.textContent = '删除';
                showToast(`删除失败: ${e.message}`, 'error', 5000);
            }
        }

        // ── KB File → Attachment (将知识库文件加入当前会话附件) ──
        async function addKbFileToAttachment(btn) {
            const sourceFile = btn.getAttribute('data-source');
            const fileId = btn.getAttribute('data-file-id') || '';
            const displayName = btn.getAttribute('data-name') || sourceFile;
            if (!sourceFile) return;
            const orig = btn.textContent;
            btn.disabled = true;
            btn.textContent = '添加中...';
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/attachments/from-kb`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_file: sourceFile, file_id: fileId, filename: displayName }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    throw new Error(data.detail || `添加失败 (HTTP ${resp.status})`);
                }
                showToast(data.message || `✓ 已添加到附件「${displayName}」`, 'success', 4000);
                await fetchAttachments();  // 刷新附件 chips
            } catch (e) {
                showToast(`添加失败: ${e.message}`, 'error', 5000);
            } finally {
                btn.disabled = false;
                btn.textContent = orig;
            }
        }

        // ── KB 文件多选批量添加到附件 ──
        function toggleKbSelectAll(master) {
            document.querySelectorAll('.kb-file-check').forEach(cb => { cb.checked = master.checked; });
            updateKbSelectAllState();
        }

        function updateKbSelectAllState() {
            const boxes = Array.from(document.querySelectorAll('.kb-file-check'));
            const checked = boxes.filter(cb => cb.checked);
            const master = document.getElementById('kbSelectAll');
            if (master) master.checked = boxes.length > 0 && checked.length === boxes.length;
            const cnt = document.getElementById('kbSelectedCount');
            if (cnt) cnt.textContent = checked.length;
        }

        async function addSelectedKbFiles() {
            const boxes = Array.from(document.querySelectorAll('.kb-file-check:checked'));
            if (boxes.length === 0) {
                showToast('请先勾选要添加的文件', 'info', 3000);
                return;
            }
            const files = boxes.map(cb => ({
                source_file: cb.getAttribute('data-source'),
                file_id: cb.getAttribute('data-file-id') || '',
                filename: cb.getAttribute('data-name') || '',
            }));
            const btn = document.getElementById('kbBatchAddBtn');
            btn.disabled = true;
            btn.textContent = `添加中 (${files.length})...`;
            try {
                const resp = await fetch(`${AGENT_BASE}/api/agent/projects/${PROJECT_ID}/attachments/from-kb/batch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ files }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    throw new Error(data.detail || `添加失败 (HTTP ${resp.status})`);
                }
                showToast(data.message || `✓ 已添加 ${data.added_count} 个文件到附件`, 'success', 4000);
                await fetchAttachments();   // 刷新附件 chips
                showKbFilesDialog();        // 刷新列表（重置勾选）
            } catch (e) {
                showToast(`批量添加失败: ${e.message}`, 'error', 5000);
                btn.disabled = false;
                btn.textContent = '批量添加到附件';
            }
        }

        // 点击遮罩层关闭（[PORT] 顶层绑定 → 具名函数，由 _doInit 首次调用）
        function setupKbDialogMask() {
            document.getElementById('kbFilesDialog').addEventListener('click', function(e) {
                if (e.target === this) closeKbFilesDialog();
            });
        }

        // ── Init（[PORT] 原为脚本尾部立即执行；改为 activate() 首次触发，一次性执行。
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

    // ── 内联事件处理器导出（自动生成）──
    // agent HTML（静态 + JS 动态生成）使用 onclick="fn()" 原生全局解析，
    // IIFE 内必须显式挂到 window。清单 = 内联引用 ∩ JS 函数声明。
    window.addKbFileToAttachment = addKbFileToAttachment;
    window.addSelectedKbFiles = addSelectedKbFiles;
    window.cancelUpload = cancelUpload;
    window.changeWritingStyle = changeWritingStyle;
    window.clearConversation = clearConversation;
    window.clearInput = clearInput;
    window.closeAutoGenDialog = closeAutoGenDialog;
    window.closeEnrichDialog = closeEnrichDialog;
    window.closeFlowchartDialog = closeFlowchartDialog;
    window.closeKbFilesDialog = closeKbFilesDialog;
    window.closeModifyDialog = closeModifyDialog;
    window.closeSkillsDialog = closeSkillsDialog;
    window.closeSummarizeDialog = closeSummarizeDialog;
    window.closeTemplateDialog = closeTemplateDialog;
    window.compressContext = compressContext;
    window.deleteKbFile = deleteKbFile;
    window.deleteSkill = deleteSkill;
    window.downloadDocument = downloadDocument;
    window.downloadDocx = downloadDocx;
    window.downloadLatestModified = downloadLatestModified;
    window.downloadModifiedDoc = downloadModifiedDoc;
    window.downloadRiskExcel = downloadRiskExcel;
    window.editAndResume = editAndResume;
    window.editSkill = editSkill;
    window.exportFlowchartPng = exportFlowchartPng;
    window.generateFlowchart = generateFlowchart;
    window.gotoKbPage = gotoKbPage;
    window.handleEnrichFileSelect = handleEnrichFileSelect;
    window.handleFileSelect = handleFileSelect;
    window.handleFolderSelect = handleFolderSelect;
    window.handleKbFileSelect = handleKbFileSelect;
    window.handleTemplateFileSelect = handleTemplateFileSelect;
    window.insertFlowchart = insertFlowchart;
    window.onEnrichExistingChange = onEnrichExistingChange;
    window.onSumModeChange = onSumModeChange;
    window.openModifyDialog = openModifyDialog;
    window.openSkillsDialog = openSkillsDialog;
    window.pauseGeneration = pauseGeneration;
    window.previewFlowchartMermaid = previewFlowchartMermaid;
    window.removeAttachment = removeAttachment;
    window.removeSelectedTemplateFile = removeSelectedTemplateFile;
    window.removeTemplate = removeTemplate;
    window.resumeAgent = resumeAgent;
    window.reviseFlowchart = reviseFlowchart;
    window.saveSkill = saveSkill;
    window.sendMessage = sendMessage;
    window.showAutoGenDialog = showAutoGenDialog;
    window.showEnrichDialog = showEnrichDialog;
    window.showFlowchartDialog = showFlowchartDialog;
    window.showSummarizeDialog = showSummarizeDialog;
    window.showTemplateDialog = showTemplateDialog;
    window.startAutoGenerate = startAutoGenerate;
    window.startNewChat = startNewChat;
    window.startSummarize = startSummarize;
    window.submitEnrich = submitEnrich;
    window.submitModify = submitModify;
    window.submitTemplate = submitTemplate;
    window.toggleKbSelectAll = toggleKbSelectAll;
    window.triggerKbUpload = triggerKbUpload;
    window.undoLast = undoLast;
    window.updateClearBtn = updateClearBtn;
    window.updateKbSelectAllState = updateKbSelectAllState;
    window.useSkillInsert = useSkillInsert;
    window.useSkillSend = useSkillSend;

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
