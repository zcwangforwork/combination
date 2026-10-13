/*
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
        return /^\/api\//.test(url) || /:801[234]\//.test(url);
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

let selectedFile = null;
let sessionId = null;
// [PORT-AUTH] 原为 EventSource；无法携带 Authorization 头 → fetch 流式 reader
// （sseController 控制断开，sseAlive 标记连接存活性，对齐原 readyState 语义）
let sseController = null;
let sseAlive = false;
let isAwaitingInput = false;
let lastReport = '';
let lastFilename = '';
let currentStage = '';
let agentMode = 'single';  // 'single' | 'multi' — 启动会话时确定
function apiBase() { return agentMode === 'multi' ? REVIEW_BASE + '/api/multi-agent' : REVIEW_BASE + '/api/agent'; }

// DOM elements（[PORT] 原为顶层 const 立即取值 + 顶层事件绑定；SPA 登录前
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
}

function handleFileSelect(e) { if (e.target.files.length) handleFile(e.target.files[0]); }
function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['docx', 'pdf'].includes(ext)) { alert('仅支持 .docx 和 .pdf 文件'); return; }
  selectedFile = file;
  document.getElementById('ar-fileName').textContent = file.name;
  document.getElementById('ar-fileSize').textContent = formatSize(file.size);
  fileInfo.style.display = 'block';
  uploadZone.style.display = 'none';
  // 无文件也可启动（自由对话），有文件后切换为审核模式按钮文案
  startConvBtn.disabled = false;
  startConvBtn.textContent = '开始文档审核';
}
function removeFile() {
  selectedFile = null;
  fileInfo.style.display = 'none';
  uploadZone.style.display = 'block';
  // 无文件也能启动自由对话，按钮保持可点击
  startConvBtn.disabled = false;
  startConvBtn.textContent = '开始对话审核';
  fileInput.value = '';
}
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Start conversation
async function startConversation() {
  startConvBtn.disabled = true;
  agentMode = document.getElementById('ar-agentMode').value;  // 'single' | 'multi'

  const formData = new FormData();
  if (selectedFile) {
    formData.append('file', selectedFile);
  }
  formData.append('audit_type', document.getElementById('ar-auditType').value);
  formData.append('doc_type', '');
  formData.append('session_id', 'conv-' + _newSessionId());

  // 立即切换到对话界面，避免上传/分析期间卡在上传覆盖层
  uploadOverlay.classList.add('hidden');
  inputArea.style.display = 'block';
  enableInput(false);

  // 有文件时显示上传/分析进度消息
  if (selectedFile) {
    progressBarWrap.style.display = 'block';
    updateStage('intake');
    const modeLabel = agentMode === 'multi' ? '多 Agent 协作' : '单 Agent';
    addMessage('agent', `正在上传并分析文档 **${escapeHtml(selectedFile.name)}**（${modeLabel}），请稍候...`);
  }

  try {
    const resp = await fetch(`${apiBase()}/conversation/start`, { method: 'POST', body: formData });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || 'Request failed');
    }
    const data = await resp.json();
    sessionId = data.session_id;
    lastFilename = data.filename || '';

    if (data.mode === 'free_chat') {
      // 自由对话模式：不展示进度条，header 显示上传入口
      progressBarWrap.style.display = 'none';
      document.getElementById('ar-uploadDocBtn').classList.remove('hidden');
      addMessage('agent', `已进入**自由对话模式**（未上传文档）。你可以直接提问医疗器械法规、体系文件、审核标准等问题。\n\n💡 如需审核具体文档，可点击右上角「📄 上传文档审核」按钮上传文件开始审核。`);
      updateStage('intake');
      connectSSE();
      enableInput(true);
    } else {
      // 文档审核模式：隐藏上传入口，显示会话创建成功消息
      document.getElementById('ar-uploadDocBtn').classList.add('hidden');
      const modeLabel = agentMode === 'multi' ? '多 Agent 协作（章节级并行）' : '单 Agent';
      addMessage('agent', `会话已创建（${modeLabel}）。文档 **${escapeHtml(data.filename)}** 包含 **${data.section_count}** 个章节，类型为 **${data.audit_type}**。Agent 正在分析文档结构...`);
      updateStage('intake');
      connectSSE();
      // 多 Agent 模式现已支持完整对话循环（分章确认 / 重审 / 报告后对话）
      enableInput(true);
    }

  } catch (err) {
    // 在对话界面显示错误，并提供重试入口
    addMessage('system', '启动失败: ' + err.message + '。请点击右上角「📄 上传文档审核」重新尝试。');
    document.getElementById('ar-uploadDocBtn').classList.remove('hidden');
    startConvBtn.disabled = false;
  }
}

// 从自由对话模式返回上传界面，开始文档审核
function returnToUpload() {
  // 关闭 SSE 连接
  if (sseController) { try { sseController.abort(); } catch (e) {} sseController = null; }
  sseAlive = false;
  // 重置会话状态
  sessionId = null;
  lastReport = '';
  lastFilename = '';
  currentStage = '';
  isAwaitingInput = false;
  // 清空聊天消息
  chatMessages.innerHTML = '';
  // 隐藏聊天 UI 与上传入口按钮
  inputArea.style.display = 'none';
  progressBarWrap.style.display = 'none';
  document.getElementById('ar-uploadDocBtn').classList.add('hidden');
  // 按钮文案恢复为"开始对话审核"（无文件状态）
  startConvBtn.textContent = '开始对话审核';
  startConvBtn.disabled = false;
  // 重新显示上传覆盖层
  uploadOverlay.classList.remove('hidden');
  // 保留已选的审核领域与 Agent 模式，清空文件选择
  if (selectedFile) {
    selectedFile = null;
    fileInfo.style.display = 'none';
    uploadZone.style.display = 'block';
    fileInput.value = '';
  }
}

// SSE connection（[PORT-AUTH] 原为 EventSource——无法携带 Authorization 头，
// 服务端流端点已挂 require_session_access 鉴权 → 改 fetch 流式读取：
// 逐块解析 data: 行语义等价；正常结束/网络错误 3s 重连保持原行为）
function connectSSE() {
  if (sseController) { try { sseController.abort(); } catch (e) {} }
  sseAlive = false;
  const url = `${apiBase()}/conversation/stream/${sessionId}`;
  sseController = new AbortController();
  const ctl = sseController;
  const _fail = () => {
    if (sseController === ctl) sseController = null;
    sseAlive = false;
    console.warn('SSE connection lost, reconnecting in 3s...');
    setTimeout(connectSSE, 3000);
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
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data:')) {
            try {
              handleSSEEvent(JSON.parse(line.slice(5).trim()));
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
}

function handleSSEEvent(event) {
  switch (event.event) {
    case 'token':
      handleToken(event);
      break;
    case 'node_complete':
      handleNodeComplete(event);
      break;
    case 'checkpoint':
      handleCheckpoint(event);
      break;
    case 'awaiting_input':
      handleAwaitingInput(event);
      break;
    case 'agent_message':
      handleAgentMessage(event);
      break;
    case 'resuming':
      handleResuming(event);
      break;
    case 'complete':
      handleComplete(event);
      break;
    case 'chapter_done':
      handleChapterDone(event);
      break;
    case 'tool_call':
      handleToolCall(event);
      break;
    case 'tool_result':
      handleToolResult(event);
      break;
    case 'error':
      handleError(event);
      break;
    case 'heartbeat':
      break;
  }
}

// 多 Agent 模式专属：章节级并行审核完成单个章节
function handleChapterDone(event) {
  const idx = event.chapter_idx ?? '?';
  const title = event.chapter_title || '';
  const pct = event.progress_pct ?? 0;
  const summary = event.chapter_summary ? `\n\n${event.chapter_summary}` : '';
  addMessage('progress', `**章节审核完成**: 第 ${idx} 章 ${escapeHtml(title)} (进度 ${pct}%)${summary}`);
}

// Stage mapping
const STAGE_MAP = {
  'intake': 0, 'strategy': 0, 'audit': 1, 'cross_validate': 2,
  'report': 3, 'revision': 4
};

function updateStage(stage) {
  if (stage === currentStage) return;
  currentStage = stage;

  const stages = document.querySelectorAll('.progress-stage');
  stages.forEach(s => s.classList.remove('active', 'done'));

  // Mark done up to current stage
  let found = false;
  stages.forEach(s => {
    const ds = s.dataset.stage;
    if (ds === stage) {
      s.classList.add('active');
      found = true;
    } else if (!found) {
      s.classList.add('done');
    }
  });

  if (stage === 'complete') {
    stages.forEach(s => { s.classList.remove('active'); s.classList.add('done'); });
  }
}

function handleNodeComplete(event) {
  const node = event.node;
  // 节点切换：完结当前流式气泡，让下一节点的 token 进入新气泡
  finalizeStreamingBubble();
  // Map node names to stages
  if (node === 'plan_strategy') updateStage('strategy');
  else if (node === 'batched_audit') updateStage('audit');
  else if (node === 'cross_validate') updateStage('cross_validate');
  else if (node === 'generate_report') updateStage('report');
  else if (node === 're_audit_sections') updateStage('audit');
}

// ---------- Token-level streaming ----------
// LangGraph 'messages' stream → 增量 token，逐字渲染到一个气泡内。
// 节点切换 / checkpoint / 审核完成时关闭当前气泡。
let streamingBubbleEl = null;     // <div class="bubble"> 当前活动气泡
let streamingText = '';            // 累积的原文文本
let streamingNode = '';            // 该气泡所属节点名（用于节点切换检测）

function handleToken(event) {
  const tokenText = event.content || '';
  if (!tokenText) return;
  const node = event.node || '';

  // 同节点连续 token：追加；节点切换：换新气泡
  if (!streamingBubbleEl || streamingNode !== node) {
    finalizeStreamingBubble();
    streamingNode = node;
    streamingText = '';
    const div = document.createElement('div');
    div.className = 'msg agent streaming';
    div.innerHTML = '<div class="avatar">🤖</div><div class="bubble"></div>';
    chatMessages.appendChild(div);
    streamingBubbleEl = div.querySelector('.bubble');
  }

  streamingText += tokenText;
  streamingBubbleEl.innerHTML = renderMarkdown(streamingText);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function finalizeStreamingBubble() {
  if (streamingBubbleEl) {
    // 移除"正在流式输出"的标记类，但保留内容
    const wrap = streamingBubbleEl.closest('.msg');
    if (wrap) wrap.classList.remove('streaming');
  }
  streamingBubbleEl = null;
  streamingText = '';
  streamingNode = '';
}

let autoResumeTimer = null;
let autoResumeCountdown = 0;

async function handleCheckpoint(event) {
  isAwaitingInput = true;
  finalizeStreamingBubble();
  const summary = event.summary || '';
  const structured = event.structured || null;

  // 自由对话模式：startConversation 已显示欢迎语，这里仅启用输入
  if (event.checkpoint === 'free_chat') {
    enableInput(true);
    return;
  }

  if (event.checkpoint === 'strategy_review' || event.checkpoint === 'structure_review') {
    updateStage('strategy');
    addMessage('agent', `**结构分析完成**\n\n${summary}\n\n请确认分章策略，或告诉我需要调整的地方。`);
    addCheckpointCard(event.checkpoint, structured);
    addQuickActions(['approve']);
    enableInput(true);
  } else if (event.checkpoint === 'progress') {
    // Progress checkpoint — auto-continue, user can interrupt
    updateStage('audit');
    const completed = event.completed || 0;
    const total = event.total || 0;
    const pct = total > 0 ? Math.round(completed / total * 100) : 0;
    addMessage('progress', `**审核进度**: ${completed}/${total} 章节 (${pct}%)${summary ? '\n\n' + summary : ''}`);
    // Auto-continue — no quick actions needed, but user can type anytime
    enableInput(true);
  } else if (event.checkpoint === 'post_audit') {
    updateStage('audit');
    const reauditHint = agentMode === 'multi'
      ? '回复"重审第X章"对特定章节重新审核'
      : '回复"重审第X节"对特定章节重新审核';
    addMessage('agent', `**章节审核完成**\n\n${summary}\n\n你可以：\n- 回复"继续"生成最终报告\n- ${reauditHint}\n- 或者问我任何问题`);
    addCheckpointCard('post_audit', structured);
    addQuickActions(['approve', 'reaudit', 'export']);
    enableInput(true);
  } else if (event.checkpoint === 'report_review') {
    updateStage('report');
    addMessage('agent', `**报告已生成**\n\n${summary}\n\n你可以要求修改报告格式或内容，或确认完成。`);
    addQuickActions(['approve', 'regenerate', 'export']);
    enableInput(true);
  } else if (event.checkpoint === 'post_completion') {
    // Phase 1.4: 审核完成后进入自由对话模式
    updateStage('complete');
    addMessage('agent', `${summary || '审核报告已生成。'}\n\n你可以继续提问、要求调整报告、或导出报告。回复"结束"关闭会话。`);
    addCheckpointCard('post_completion', structured);
    // 拉取并展示完整审核报告
    try {
      const rptBase = agentMode === 'multi' ? REVIEW_BASE + '/api/multi-agent' : REVIEW_BASE + '/api/agent';
      const r = await fetch(`${rptBase}/conversation/report/${sessionId}`);
      if (r.ok) {
        const rd = await r.json();
        const rpt = rd.report || rd.final_report || '';
        if (rpt) { lastReport = rpt; addMessage('agent', renderMarkdown(rpt)); }
      }
    } catch (_) { /* 报告拉取失败不阻塞对话 */ }
    addQuickActions(['export']);
    enableInput(true);
  } else {
    addMessage('agent', `${summary || 'Agent 正在等待你的指令...'}`);
    addQuickActions(['approve']);
    enableInput(true);
  }
}

function handleComplete(event) {
  updateStage('complete');
  isAwaitingInput = false;
  finalizeStreamingBubble();
  lastReport = event.report || '';

  if (lastReport) {
    addMessage('agent', renderMarkdown(lastReport));
  }
  addMessage('system', '审核已完成。你可以导出报告或开始新的审核。');
  addQuickActions(['export']);
  // Keep input enabled — user can still chat with agent after completion
  enableInput(true);
  if (sseController) { try { sseController.abort(); } catch (e) {} sseController = null; }
  sseAlive = false;
}

function handleError(event) {
  addMessage('system', '错误: ' + (event.message || '未知错误'));
  enableInput(false);
}

function handleAwaitingInput(event) {
  isAwaitingInput = true;
  // Clear any existing auto-resume timer
  if (autoResumeTimer) { clearInterval(autoResumeTimer); autoResumeTimer = null; }

  if (event.auto_resume) {
    // Show countdown for auto-resume
    autoResumeCountdown = Math.ceil(event.auto_resume_timeout || 3);
    const cdEl = showAutoResumeCountdown(autoResumeCountdown);

    autoResumeTimer = setInterval(() => {
      autoResumeCountdown--;
      if (autoResumeCountdown <= 0) {
        clearInterval(autoResumeTimer);
        autoResumeTimer = null;
        cdEl.textContent = 'Agent 正在继续...';
      } else {
        cdEl.textContent = `${autoResumeCountdown}秒后自动继续（输入消息可打断）`;
      }
    }, 1000);
  }
}

function handleResuming(event) {
  // Graph is resuming after a checkpoint — clean up
  if (autoResumeTimer) { clearInterval(autoResumeTimer); autoResumeTimer = null; }
  removeAutoResumeCountdown();
}

function showAutoResumeCountdown(countdown) {
  removeAutoResumeCountdown();
  const cd = document.createElement('div');
  cd.id = 'ar-autoResumeCountdown';
  cd.style.cssText = 'text-align:center;color:var(--text-secondary);font-size:12px;padding:4px 0;';
  cd.textContent = `${countdown}秒后自动继续（输入消息可打断）`;
  const inputArea = document.getElementById('ar-inputArea');
  inputArea.insertBefore(cd, inputArea.firstChild);
  return cd;
}

function removeAutoResumeCountdown() {
  const cd = document.getElementById('ar-autoResumeCountdown');
  if (cd) cd.remove();
}

function handleAgentMessage(event) {
  // Agent sent a message (e.g., answering a question or acknowledging queued message)
  const content = event.content || '';
  addMessage('agent', renderMarkdown(content));
}

// Chat messages
function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const avatarEmoji = role === 'agent' ? '🤖' : role === 'user' ? '👤' : '⚠';
  div.innerHTML = `<div class="avatar">${avatarEmoji}</div><div class="bubble">${content}</div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Phase 2.5: 渲染 checkpoint 结构化卡片（策略/审核概览/完成总结）
function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function addCheckpointCard(checkpoint, structured) {
  if (!structured || typeof structured !== 'object') return;
  const wrap = document.createElement('div');
  wrap.className = 'msg agent';
  const avatar = '<div class="avatar">📋</div>';
  let body = '';

  if (checkpoint === 'strategy_review' && structured.strategy) {
    const s = structured.strategy;
    const rows = (s.plan_preview || []).map(p =>
      `<tr><td>${p.section_idx}</td><td>${escapeHtml(p.title || '').slice(0, 40)}</td><td><span class="badge depth-${escapeHtml(p.depth)}">${escapeHtml(p.depth)}</span></td></tr>`
    ).join('');
    body = `
      <div class="card">
        <div class="card-title">审核策略概览</div>
        <div class="card-stats">
          <span>章节总数：<b>${s.section_count}</b></span>
          <span class="badge depth-deep">deep ${s.deep}</span>
          <span class="badge depth-standard">standard ${s.standard}</span>
          <span class="badge depth-quick">quick ${s.quick}</span>
        </div>
        ${rows ? `<table class="card-table"><thead><tr><th>#</th><th>章节</th><th>深度</th></tr></thead><tbody>${rows}</tbody></table>` : ''}
      </div>`;
  } else if (checkpoint === 'post_audit' && structured.overview) {
    const o = structured.overview;
    const rows = (o.sections || []).map(r => {
      const sev = r.critical_count > 0 ? 'critical' : (r.findings_count > 0 ? 'warn' : 'ok');
      return `<tr><td>${r.section_idx}</td><td>${escapeHtml(r.title || '').slice(0, 40)}</td><td>${escapeHtml(r.depth || '')}</td><td>${r.score ?? '-'}</td><td><span class="badge sev-${sev}">${r.findings_count}</span></td><td>${r.critical_count > 0 ? `<span class="badge sev-critical">${r.critical_count}</span>` : '-'}</td></tr>`;
    }).join('');
    body = `
      <div class="card">
        <div class="card-title">章节审核结果</div>
        <div class="card-stats">
          <span>已审核：<b>${o.audited}/${o.total}</b></span>
          <span>问题总数：<b>${o.total_findings}</b></span>
          <span class="badge sev-critical">严重 ${o.critical}</span>
          ${o.contradictions_count > 0 ? `<span class="badge sev-warn">矛盾 ${o.contradictions_count}</span>` : ''}
        </div>
        ${rows ? `<table class="card-table"><thead><tr><th>#</th><th>标题</th><th>深度</th><th>分</th><th>问题</th><th>严重</th></tr></thead><tbody>${rows}</tbody></table>` : ''}
      </div>`;
  } else if (checkpoint === 'post_completion' && structured.completion) {
    const c = structured.completion;
    body = `
      <div class="card">
        <div class="card-title">审核完成</div>
        <div class="card-stats">
          <span>章节：<b>${c.audited_count}/${c.section_count}</b></span>
          ${c.has_report ? '<span class="badge sev-ok">报告已生成</span>' : '<span class="badge sev-warn">无报告</span>'}
        </div>
      </div>`;
  } else {
    return;
  }

  wrap.innerHTML = avatar + '<div class="bubble">' + body + '</div>';
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Phase 3.4: 工具调用状态卡（Agent tool-call 实时反馈）
const _toolCallEls = {};   // tool_id → DOM element

function handleToolCall(event) {
  finalizeStreamingBubble();
  const tid = event.tool_id || ('t_' + Date.now());
  const name = event.tool_name || 'unknown';
  const argsPreview = event.tool_args ? JSON.stringify(event.tool_args).slice(0, 120) : '';

  const wrap = document.createElement('div');
  wrap.className = 'msg agent tool-msg';
  wrap.innerHTML = `
    <div class="avatar">🔧</div>
    <div class="bubble">
      <div class="tool-call">
        <span class="badge sev-warn">调用工具</span>
        <code>${escapeHtml(name)}</code>
        ${argsPreview ? `<span class="tool-args">${escapeHtml(argsPreview)}</span>` : ''}
        <span class="tool-status" data-status="pending">⏳ 执行中…</span>
      </div>
    </div>`;
  chatMessages.appendChild(wrap);
  _toolCallEls[tid] = wrap;
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function handleToolResult(event) {
  const tid = event.tool_id;
  const preview = event.result_preview || '';
  const el = _toolCallEls[tid];
  if (el) {
    const status = el.querySelector('.tool-status');
    if (status) {
      status.dataset.status = 'done';
      status.textContent = '✓ 完成';
    }
    if (preview) {
      const out = document.createElement('div');
      out.className = 'tool-output';
      out.textContent = preview;
      el.querySelector('.tool-call')?.appendChild(out);
    }
    delete _toolCallEls[tid];
  } else {
    // 没找到对应的 tool_call，作为独立消息渲染
    const wrap = document.createElement('div');
    wrap.className = 'msg agent tool-msg';
    wrap.innerHTML = `
      <div class="avatar">🔧</div>
      <div class="bubble">
        <div class="tool-call">
          <span class="badge sev-ok">工具结果</span>
          <code>${escapeHtml(event.tool_name || '')}</code>
          <div class="tool-output">${escapeHtml(preview)}</div>
        </div>
      </div>`;
    chatMessages.appendChild(wrap);
  }
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addQuickActions(types) {
  // Remove existing quick actions
  document.querySelectorAll('.quick-actions').forEach(el => el.remove());

  const actions = document.createElement('div');
  actions.className = 'quick-actions';

  if (types.includes('approve')) {
    const btn = document.createElement('button');
    btn.className = 'primary';
    btn.textContent = '继续';
    btn.onclick = () => sendMessage('继续');
    actions.appendChild(btn);
  }
  if (types.includes('reaudit')) {
    const btn = document.createElement('button');
    btn.textContent = '重审指定章节';
    btn.onclick = () => {
      messageInput.value = '重审第';
      messageInput.focus();
    };
    actions.appendChild(btn);
  }
  if (types.includes('skip')) {
    const btn = document.createElement('button');
    btn.textContent = '跳过章节';
    btn.onclick = () => {
      messageInput.value = '跳过第';
      messageInput.focus();
    };
    actions.appendChild(btn);
  }
  if (types.includes('regenerate')) {
    const btn = document.createElement('button');
    btn.textContent = '修改报告';
    btn.onclick = () => {
      messageInput.value = '请修改报告：';
      messageInput.focus();
    };
    actions.appendChild(btn);
  }
  if (types.includes('export')) {
    const btn = document.createElement('button');
    btn.className = 'export-btn';
    btn.textContent = '导出 Word 报告';
    btn.onclick = exportReport;
    actions.appendChild(btn);
  }

  chatMessages.appendChild(actions);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function enableInput(enabled) {
  messageInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
  if (enabled) messageInput.focus();
}

// Send message — can be called at any time (checkpoint or mid-audit)
async function sendMessage(text) {
  const content = text || messageInput.value.trim();
  if (!content || !sessionId) return;

  addMessage('user', escapeHtml(content));
  messageInput.value = '';
  // Input stays enabled — user can send messages at any time

  // Remove quick actions
  document.querySelectorAll('.quick-actions').forEach(el => el.remove());

  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('message', content);

  try {
    const msgBase = agentMode === 'multi' ? REVIEW_BASE + '/api/multi-agent' : REVIEW_BASE + '/api/agent';
    const resp = await fetch(`${msgBase}/conversation/message`, { method: 'POST', body: formData });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || 'Request failed');
    }
    // SSE stays connected across checkpoints — events flow automatically.
    // Only reconnect if the SSE was actually dropped (network issue, etc.)
    if (!sseAlive && sessionId) {
      console.warn('SSE unexpectedly closed, reconnecting...');
      connectSSE();
    }
  } catch (err) {
    addMessage('system', '发送失败: ' + err.message);
  }
}

// Export
async function exportReport() {
  if (!lastReport) {
    // 尝试从服务端获取报告
    try {
      const resp = await fetch(`${apiBase()}/conversation/state/${sessionId}`);
      const state = await resp.json();
      // 单 Agent state: final_report 字段；多 Agent state: has_final_report 标记（无 final_report 字段）
      const hasReport = state.final_report || state.has_final_report;
      if (state.finished && state.final_report) {
        lastReport = state.final_report;
      } else if (state.finished && hasReport) {
        addMessage('system', '正在从服务端获取报告...');
        // 重新从图状态拉取完整报告
        const reportResp = await fetch(`${apiBase()}/conversation/report/${sessionId}`);
        if (reportResp.ok) {
          const reportData = await reportResp.json();
          lastReport = reportData.report || reportData.final_report || '';
        }
        if (!lastReport) {
          alert('报告数据暂未生成，请稍后再试');
          return;
        }
      } else {
        alert('报告尚未生成，请等待审核完成');
        return;
      }
    } catch (e) {
      alert('报告尚未生成，请等待审核完成');
      return;
    }
  }
  try {
    const resp = await fetch(REVIEW_BASE + '/api/export-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: lastReport, filename: lastFilename || 'agent_audit' })
    });
    if (!resp.ok) throw new Error('导出失败');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (lastFilename || 'agent_audit').replace(/\.[^.]+$/, '') + '_conversation_audit_report.docx';
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert('导出失败: ' + err.message);
  }
}

// Simple markdown renderer
function renderMarkdown(md) {
  if (!md) return '';
  let html = md;
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/^\|(.+)\|$/gm, function(m) {
    const cells = m.split('|').filter(c => c.trim());
    if (m.match(/^[\|\s\-:]+$/)) return '';
    const isHeader = !m.match(/^\|[\s\-:]+\|$/);
    const tag = isHeader ? 'th' : 'td';
    return '<tr>' + cells.map(c => '<' + tag + '>' + c.trim() + '</' + tag + '>').join('') + '</tr>';
  });
  html = html.replace(/(<tr>[\s\S]*?<\/tr>)+/g, '<table>$&</table>');
  html = html.replace(/^---+$/gm, '<hr>');
  html = html.replace(/^(\s*)- (.+)$/gm, '<li>$2</li>');
  html = html.replace(/^(\s*)\d+\. (.+)$/gm, '<li>$2</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)+/g, '<ul>$&</ul>');
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/<\/ul>\s*<ul>/g, '');
  return html;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Init（[PORT] 原为脚本尾顶层立即调用；改为 activate() 首次触发，一次性执行。
// 后续菜单切换不重跑——v-show 视图与页面共存亡，等价于原页面持续打开）──
let _inited = false;
function _doInit() {
  if (_inited) return;
  _inited = true;
  _bindDom();
  // 原语义：页面加载即进入自由对话模式（无上传覆盖层），可随时点「上传文档审核」
  startConversation();
}

    // ── 内联事件处理器导出（自动生成）──
    // 审核 HTML（静态 + JS 动态生成）使用 onclick="fn()" 原生全局解析，
    // IIFE 内必须显式挂到 window。清单 = 内联引用 ∩ JS 函数声明。
    window.handleFileSelect = handleFileSelect;
    window.removeFile = removeFile;
    window.returnToUpload = returnToUpload;
    window.sendMessage = sendMessage;
    window.startConversation = startConversation;

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
