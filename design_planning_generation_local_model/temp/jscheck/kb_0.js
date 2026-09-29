
        const KB_MAX_SIZE_BYTES = 20 * 1024 * 1024;
        const KB_ALLOWED_FORMATS = ['.docx', '.pdf', '.txt', '.doc', '.ppt', '.pptx', '.xls', '.xlsx',
            '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.html', '.htm'];
        // 从 agent 页跳转时带上 project，用于"批量添加到附件"
        const urlParams = new URLSearchParams(window.location.search);
        const PROJECT_ID = urlParams.get('project') || '';
        // [KB-ISO] 当前登录用户名（JWT sub），用于 ADMIN 视角标注文件归属
        // [SEC 2026-09-29] 同时解析 role / sec_level claim（上传密级选择 + 保密管理入口）
        let CURRENT_USER = '';
        let KB_IS_ADMIN = false;
        let KB_MY_SEC = null;   // 无 claim（旧 token）时为 null → 视同 0（fail-closed）
        try {
            const _t = sessionStorage.getItem('agent_token') || '';
            const _p = _t.split('.')[1];
            if (_p) {
                let _b = _p.replace(/-/g, '+').replace(/_/g, '/');
                while (_b.length % 4) _b += '=';
                const _claims = JSON.parse(decodeURIComponent(escape(atob(_b))));
                CURRENT_USER = _claims.sub || '';
                KB_IS_ADMIN = (_claims.role === 'ADMIN');
                if (typeof _claims.sec_level === 'number' && _claims.sec_level >= 0 && _claims.sec_level <= 3) {
                    KB_MY_SEC = _claims.sec_level;
                }
            }
        } catch (e) { /* ignore */ }
        let kbFiles = [];   // 缓存当前列表，供多选批量添加
        let asking = false;

        function esc(s) {
            if (!s) return '';
            return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // ── Toast ──
        let toastEl = null;
        function showToast(text, ms = 3500) {
            if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'toast'; document.body.appendChild(toastEl); }
            toastEl.textContent = text;
            toastEl.classList.add('show');
            setTimeout(() => toastEl.classList.remove('show'), ms);
        }

        // ── 上传登记表（与 Agent 主页 agent.html 共用同一 localStorage key）──
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

        // ── 上传进度面板行 ──
        function _kbRow(taskId, filename) {
            document.getElementById('kbUploadPanel').style.display = 'block';
            let row = document.getElementById('kbrow-' + taskId);
            if (!row) {
                row = document.createElement('div');
                row.id = 'kbrow-' + taskId;
                row.style.cssText = 'display:flex;justify-content:space-between;gap:8px;font-size:12px;color:#555';
                row.innerHTML = `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📄 ${esc(filename)}</span>` +
                                `<span class="kb-stage" style="color:#1565c0;flex-shrink:0">上传中...</span>`;
                document.getElementById('kbUploadRows').appendChild(row);
            }
            return row;
        }
        function _kbRowUpdate(taskId, text, state) {
            const row = document.getElementById('kbrow-' + taskId);
            if (!row) return;
            const st = row.querySelector('.kb-stage');
            if (st) {
                st.textContent = text;
                st.style.color = state === 'done' ? '#2e7d32' : (state === 'error' ? '#c62828' : '#1565c0');
            }
        }

        // ── 可恢复轮询：阶段+耗时实时刷新 ──
        async function pollKbUpload(taskId, filename, startedAt) {
            for (let i = 0; i < 1600; i++) {
                await new Promise(r => setTimeout(r, 1500));
                let st;
                try {
                    const resp = await fetch('/api/extract-status/' + taskId);
                    if (resp.status === 404) throw new Error('任务已丢失（服务可能重启）');
                    if (!resp.ok) throw new Error('查询状态失败');
                    st = await resp.json();
                } catch (e) {
                    _kbRowUpdate(taskId, `⚠ ${e.message}`, 'error');
                    unregisterUpload(taskId);
                    return false;
                }
                if (st.status === 'failed') {
                    _kbRowUpdate(taskId, `✗ ${st.message || '提取失败'}`, 'error');
                    unregisterUpload(taskId);
                    return false;
                }
                if (st.status === 'completed') {
                    const msg = st.persisted
                        ? `✓ 已入库（${st.char_count} 字符）`
                        : `✓ 提取完成（${st.char_count} 字符，未入库）`;
                    _kbRowUpdate(taskId, msg, 'done');
                    unregisterUpload(taskId);
                    return true;
                }
                const elapsed = Math.round((Date.now() - (startedAt || Date.now())) / 1000);
                _kbRowUpdate(taskId, `${st.message || '提取中'} · ${elapsed}s`, 'running');
            }
            // 超时≠失败：后台仍在提取，保留登记（刷新后自动恢复）
            _kbRowUpdate(taskId, '⏳ 仍在后台提取，可稍后刷新查看', 'running');
            return false;
        }

        // ── 页面加载恢复：登记表中进行中的 KB 上传（含 Agent 主页发起的）──
        async function restoreKbUploads() {
            const reg = _loadUploadReg().filter(e => e.type === 'kb');
            let anyCompleted = false;
            for (const e of reg) {
                let st;
                try {
                    const resp = await fetch('/api/extract-status/' + e.taskId);
                    if (resp.status === 404) { unregisterUpload(e.taskId); continue; }
                    if (!resp.ok) continue;  // 网络问题：保留登记，下次再试
                    st = await resp.json();
                } catch (err) { continue; }

                if (st.status === 'completed') {
                    _kbRow(e.taskId, e.filename);
                    _kbRowUpdate(e.taskId, `✓ 已入库（${st.char_count || 0} 字符）`, 'done');
                    unregisterUpload(e.taskId);
                    anyCompleted = true;
                } else if (st.status === 'failed') {
                    _kbRow(e.taskId, e.filename);
                    _kbRowUpdate(e.taskId, `✗ ${st.message || '提取失败'}`, 'error');
                    showToast(`✗「${e.filename}」处理失败: ${st.message || '原因未知'}`, 6000);
                    unregisterUpload(e.taskId);
                } else {
                    _kbRow(e.taskId, e.filename);
                    _kbRowUpdate(e.taskId, `${st.message || '提取中'}（已恢复进度跟踪）`, 'running');
                    pollKbUpload(e.taskId, e.filename, e.startedAt).then(ok => { if (ok) loadFiles(); });
                }
            }
            if (anyCompleted) await loadFiles();
        }

        // ── 文件上传 ──
        function triggerKbUpload() { document.getElementById('kbFileInput').click(); }

        async function handleKbFileSelect(event) {
            const files = Array.from(event.target.files || []);
            event.target.value = '';
            if (!files.length) return;
            const btn = document.getElementById('kbUploadBtn');
            btn.disabled = true;
            let ok = 0, fail = 0;
            for (const f of files) { (await uploadFileToKb(f)) ? ok++ : fail++; }
            btn.disabled = false;
            showToast(`上传完成：成功 ${ok} 个，失败 ${fail} 个`, fail ? 5000 : 3500);
            if (ok > 0) await loadFiles();
        }

        function validateKbFile(file) {
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            if (!KB_ALLOWED_FORMATS.includes(ext)) return `不支持的文件格式「${ext}」`;
            if (file.size > KB_MAX_SIZE_BYTES) return `文件「${file.name}」超过 20MB 限制`;
            if (file.size === 0) return '文件为空';
            return '';
        }

        // ── [SEC 2026-09-29] 密级工具：徽章渲染 / 上传下拉初始化 / 保密管理入口 ──
        const SEC_LABELS = ['公开', '内部', '秘密', '机密'];

        function secBadgeHtml(f) {
            if (f.mixed_sec) return '<span class="kb-sec-badge kb-sec-mixed" title="各分块密级不一致，请在保密管理中修复">不一致</span>';
            const lvl = f.sec_level;
            if (lvl === null || lvl === undefined) {
                return '<span class="kb-sec-badge kb-sec-null" title="未标注，按机密处理">未标注</span>';
            }
            return `<span class="kb-sec-badge kb-sec-${lvl}">${SEC_LABELS[lvl]}</span>`;
        }

        (function initSecSelect() {
            const sel = document.getElementById('kbSecSelect');
            let html = '<option value="">密级：自动（继承我的密级）</option>';
            for (let i = 0; i <= 3; i++) {
                // 防投毒：普通用户只能标注到本人密级（服务端 403 双重校验）
                const disabled = (!KB_IS_ADMIN && (KB_MY_SEC === null || i > KB_MY_SEC)) ? ' disabled title="高于本人密级，需管理员"' : '';
                html += `<option value="${i}"${disabled}>${i} ${SEC_LABELS[i]}</option>`;
            }
            sel.innerHTML = html;
            sel.title = KB_MY_SEC !== null
                ? `上传文件的保密密级。默认继承你的密级（当前 L${KB_MY_SEC} ${SEC_LABELS[KB_MY_SEC]}）`
                : '上传文件的保密密级。当前凭证未携带密级信息（旧令牌），如需指定请重新登录';
        })();

        function openSecAdmin() {
            // 凭证经 #jwt= 片段中转到新标签页（与 review/kb 页同机制）
            const t = sessionStorage.getItem('agent_token') || '';
            window.open('/sec-admin' + (t ? '#jwt=' + encodeURIComponent(t) : ''), '_blank');
        }
        if (KB_IS_ADMIN) document.getElementById('kbSecAdminBtn').style.display = '';

        async function uploadFileToKb(file) {
            const err = validateKbFile(file);
            if (err) { showToast(err); return false; }
            try {
                // [KB-ISO] 用户隔离：上传到当前用户个人知识库（服务端定向 chroma_db_users/<user>）
                const fd = new FormData();
                fd.append('file', file);
                // [SEC] 显式密级（下拉选择；空=继承上传者密级）
                const secVal = document.getElementById('kbSecSelect').value;
                if (secVal !== '') fd.append('sec_level', secVal);
                const resp = await fetch('/api/kb/upload', { method: 'POST', body: fd });
                if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`);
                const fileId = (await resp.json()).file_id;
                const startedAt = Date.now();
                // 登记 + 进度行（跨页面刷新/在 Agent 主页与知识库页之间切换均可恢复）
                registerUpload({ type: 'kb', taskId: fileId, filename: file.name, startedAt });
                _kbRow(fileId, file.name);
                return await pollKbUpload(fileId, file.name, startedAt);
            } catch (e) {
                showToast(`✗「${file.name}」上传失败: ${e.message}`);
                return false;
            }
        }

        // ── 文件列表 ──
        async function loadFiles() {
            const list = document.getElementById('filesList');
            list.innerHTML = '<div class="empty">加载中...</div>';
            try {
                const resp = await fetch('/api/kb/files');
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
                kbFiles = data.files || [];
                document.getElementById('fileCount').textContent = kbFiles.length ? `（共 ${kbFiles.length} 个）` : '';
                if (!kbFiles.length) {
                    list.innerHTML = '<div class="empty">知识库中暂无文件，请先上传。</div>';
                    updateBatchAddBtn();
                    return;
                }
                let html = '<table><thead><tr><th style="width:30px;text-align:center"><input type="checkbox" id="kbSelectAll" onchange="toggleSelectAll(this)"></th><th>文件名</th><th style="width:86px">密级</th><th style="text-align:right;width:70px">分块</th><th style="text-align:center;width:90px">操作</th></tr></thead><tbody>';
                for (const f of kbFiles) {
                    const hasOrig = f.original_filename && f.original_filename !== f.source_file;
                    const name = hasOrig ? f.original_filename : f.source_file;
                    const note = hasOrig ? '' : ' <span style="color:#ff9800;font-size:11px">(旧文件)</span>';
                    html += '<tr>';
                    const ownerTag = (f.owner && f.owner !== CURRENT_USER) ? `<span style="color:#999;font-size:11px">（${esc(f.owner)}）</span>` : '';
                    html += `<td style="text-align:center"><input type="checkbox" class="kb-file-check" data-source="${esc(f.source_file)}" data-file-id="${esc(f.file_id || '')}" data-name="${esc(name)}" data-owner="${esc(f.owner || '')}" onchange="updateSelectedCount()"></td>`;
                    html += `<td style="word-break:break-all">${esc(name)}${note}${ownerTag}</td>`;
                    html += `<td>${secBadgeHtml(f)}</td>`;
                    html += `<td style="text-align:right;color:#888">${f.chunk_count}</td>`;
                    html += `<td style="text-align:center;white-space:nowrap"><button class="mini-btn" data-source="${esc(f.source_file)}" data-file-id="${esc(f.file_id || '')}" data-name="${esc(name)}" title="将此文件加入当前对话的参考资料（附件区）" onclick="referenceKbFile(this)">💬 引用</button> <button class="mini-btn danger" data-source="${esc(f.source_file)}" data-name="${esc(name)}" data-owner="${esc(f.owner || '')}" onclick="deleteKbFile(this)">删除</button></td>`;
                    html += '</tr>';
                }
                html += '</tbody></table>';
                list.innerHTML = html;
                updateBatchAddBtn();
                updateSelectedCount();
            } catch (e) {
                list.innerHTML = `<div class="empty" style="color:#e53935">加载失败: ${esc(e.message)}</div>`;
            }
        }

        function toggleSelectAll(master) {
            document.querySelectorAll('.kb-file-check').forEach(cb => cb.checked = master.checked);
            updateSelectedCount();
        }
        // 批量添加按钮状态：无项目上下文时置灰并提示（需从 Agent 对话页带 project 进入）
        function updateBatchAddBtn() {
            const btn = document.getElementById('kbBatchAddBtn');
            if (!PROJECT_ID) {
                btn.disabled = true;
                btn.title = '请从 Agent 对话页（查看知识库）进入以启用批量添加附件';
            } else {
                btn.disabled = false;
                btn.title = '将勾选的文件批量加入当前会话附件';
            }
        }
        function updateSelectedCount() {
            const boxes = Array.from(document.querySelectorAll('.kb-file-check'));
            const checked = boxes.filter(cb => cb.checked);
            const master = document.getElementById('kbSelectAll');
            if (master) master.checked = boxes.length > 0 && checked.length === boxes.length;
            document.getElementById('selectedCount').textContent = `已选 ${checked.length} 个`;
        }

        async function deleteKbFile(btn) {
            const sourceFile = btn.getAttribute('data-source');
            const name = btn.getAttribute('data-name') || sourceFile;
            const owner = btn.getAttribute('data-owner') || '';
            if (!confirm(`确定从知识库删除「${name}」吗？删除后不再参与检索。`)) return;
            btn.disabled = true;
            try {
                const resp = await fetch('/api/kb/files/delete', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_file: sourceFile, owner: owner }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
                showToast(`✓ 已删除「${name}」`);
                await loadFiles();
            } catch (e) {
                btn.disabled = false;
                showToast(`删除失败: ${e.message}`);
            }
        }

        // ── 多选批量添加到附件（需 project 参数） ──
        async function addSelectedKbFiles() {
            if (!PROJECT_ID) { showToast('缺少项目上下文，无法添加附件'); return; }
            const boxes = Array.from(document.querySelectorAll('.kb-file-check:checked'));
            if (!boxes.length) { showToast('请先勾选要添加的文件'); return; }
            const files = boxes.map(cb => ({
                source_file: cb.getAttribute('data-source'),
                file_id: cb.getAttribute('data-file-id') || '',
                filename: cb.getAttribute('data-name') || '',
            }));
            const btn = document.getElementById('kbBatchAddBtn');
            btn.disabled = true;
            btn.textContent = `添加中 (${files.length})...`;
            try {
                const resp = await fetch(`/api/agent/projects/${PROJECT_ID}/attachments/from-kb/batch`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ files }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
                showToast(data.message || `✓ 已添加 ${data.added_count} 个文件到附件`);
                await loadFiles();   // loadFiles 会经 updateBatchAddBtn 复位按钮
            } catch (e) {
                showToast(`批量添加失败: ${e.message}`);
            } finally {
                btn.disabled = false;
                btn.textContent = '批量添加到附件';
            }
        }

        // ── 单文件引用到知识库对话框（点击「💬 引用」按钮）──
        function referenceKbFile(btn) {
            addChatRefFile({
                source_file: btn.getAttribute('data-source'),
                file_id: btn.getAttribute('data-file-id') || '',
                filename: btn.getAttribute('data-name') || '',
            });
        }

        // ── 对话参考文件（点击「引用」按钮加入，提问时限定检索范围）──
        let chatRefFiles = [];   // [{source_file, file_id, filename}]

        // ── 对话参考文件管理 ──
        function addChatRefFile(file) {
            if (chatRefFiles.some(f => f.source_file === file.source_file)) {
                showToast(`「${file.filename || file.source_file}」已在参考列表中`);
                return;
            }
            chatRefFiles.push(file);
            renderRefChips();
            showToast(`✓ 已引用「${file.filename || file.source_file}」，提问时将在该文件内精确检索`);
        }

        function removeChatRefFile(sourceFile) {
            chatRefFiles = chatRefFiles.filter(f => f.source_file !== sourceFile);
            renderRefChips();
        }

        function clearChatRefFiles() {
            chatRefFiles = [];
            renderRefChips();
        }

        function renderRefChips() {
            const bar = document.getElementById('chatRefBar');
            const hint = document.getElementById('chatRefHint');
            if (!chatRefFiles.length) {
                bar.innerHTML = '';
                hint.textContent = '';
                return;
            }
            bar.innerHTML = chatRefFiles.map(f =>
                `<span class="ref-chip"><span class="chip-name" title="${esc(f.filename || f.source_file)}">📎 ${esc(f.filename || f.source_file)}</span><span class="chip-x" onclick="removeChatRefFile('${esc(f.source_file)}')" title="移除">×</span></span>`
            ).join('') + `<span class="ref-chip" style="background:#fff3e0;border-color:#ffcc80;color:#e65100;cursor:pointer" onclick="clearChatRefFiles()" title="清空全部参考文件">清空</span>`;
            hint.textContent = `💡 当前提问将在以上 ${chatRefFiles.length} 个文件内精确检索相关段落`;
        }

        // ── 知识库问答 ──
        function handleChatKeydown(e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askKb(); }
        }
        function autoGrow(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'; }

        function appendMsg(role, text, sources, scoped) {
            const box = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.className = 'chat-msg ' + role;
            div.innerHTML = esc(text).replace(/\n/g, '<br>');
            if (sources && sources.length) {
                const label = scoped ? '📎 引用文件精确定位：' : '参考来源：';
                const items = sources.map(s => {
                    let loc = '';
                    if (s.section_title) loc = `「${esc(s.section_title)}」`;
                    else if (s.chunk_index >= 0) loc = `第${s.chunk_index + 1}段`;
                    return `${esc(s.source_file)}${loc}`;
                });
                div.innerHTML += `<div class="sources"><b>${label}</b>${items.join('、')}</div>`;
            }
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
            return div;
        }

        async function askKb() {
            if (asking) return;
            const input = document.getElementById('chatInput');
            const q = input.value.trim();
            if (!q) return;
            input.value = ''; input.style.height = 'auto';
            appendMsg('user', q);
            asking = true;
            document.getElementById('btnSend').disabled = true;
            try {
                const body = { question: q };
                // 拖拽引用的文件 → 限定检索范围（精确定位段落）
                if (chatRefFiles.length) {
                    body.source_files = chatRefFiles.map(f => f.source_file);
                }
                const resp = await fetch('/api/kb/chat', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
                appendMsg('agent', data.answer || '（无回答）', data.sources || [], data.scoped);
            } catch (e) {
                appendMsg('agent', '❌ 问答失败：' + e.message);
            } finally {
                asking = false;
                document.getElementById('btnSend').disabled = false;
            }
        }

        // ── Init ──
        loadFiles();
        restoreKbUploads();
    