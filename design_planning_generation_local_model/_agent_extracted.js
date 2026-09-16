
        // ── State ──
        // 从URL参数恢复已有项目，或创建新项目ID
        const urlParams = new URLSearchParams(window.location.search);
        const existingProject = urlParams.get('project');
        const PROJECT_ID = existingProject || ('project_' + Date.now());
        // 更新URL以保持PROJECT_ID一致（支持页面刷新后恢复）
        if (!existingProject) {
            const newUrl = window.location.pathname + '?project=' + PROJECT_ID;
            window.history.replaceState({}, '', newUrl);
        }
        let isStreaming = false;
        let waitingApproval = null;
        let currentDocLabel = '文档';

        document.getElementById('projectBadge').textContent =
            '项目: ' + (existingProject ? '已恢复会话' : new Date().toLocaleDateString());
        // Set up review link
        const reviewLink = document.getElementById('reviewLink');
        reviewLink.href = '/agent/review/' + PROJECT_ID;
        reviewLink.style.display = 'inline';

        // ── Attachments ──
        let uploadedFiles = [];  // {file_id, filename, char_count, preview, status}

        async function handleFileSelect(event) {
            const files = event.target.files;
            if (!files.length) return;
            for (const file of files) {
                await uploadFile(file);
            }
            event.target.value = '';  // reset input
        }

        async function uploadFile(file) {
            // Validate size (10MB)
            const maxSize = 10 * 1024 * 1024;
            if (file.size > maxSize) {
                showError(`文件「${file.name}」超过10MB限制 (${(file.size/1024/1024).toFixed(1)}MB)`);
                return;
            }
            // Validate format
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            const allowed = ['.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls', '.md'];
            if (!allowed.includes(ext)) {
                showError(`不支持的文件格式「${ext}」`);
                return;
            }

            // Add uploading chip
            const tempId = 'uploading_' + Date.now();
            uploadedFiles.push({ file_id: tempId, filename: file.name, char_count: 0, status: 'uploading' });
            renderAttachmentChips();

            try {
                const formData = new FormData();
                formData.append('file', file);

                const resp = await fetch(`/api/agent/upload/${PROJECT_ID}`, {
                    method: 'POST',
                    body: formData,
                });
                const data = await resp.json();

                if (data.success) {
                    // Replace temp with real entry
                    uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                    uploadedFiles.push({
                        file_id: data.file_id,
                        filename: data.filename,
                        char_count: data.char_count,
                        preview: data.preview,
                        status: 'completed',
                    });
                    // Brief success indicator in chat
                    appendMessage('agent', `📎 已上传「${data.filename}」(${data.char_count} 字符)。我可以在对话中检索此文件内容。`);
                } else {
                    uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                    showError(data.message || '上传失败');
                }
            } catch (err) {
                uploadedFiles = uploadedFiles.filter(f => f.file_id !== tempId);
                showError('上传失败: ' + err.message);
            }
            renderAttachmentChips();
            fetchState();  // refresh sidebar
        }

        async function removeAttachment(fileId) {
            try {
                await fetch(`/api/agent/projects/${PROJECT_ID}/attachments/${fileId}`, {
                    method: 'DELETE',
                });
            } catch (err) {
                // Still remove locally even if server fails
            }
            uploadedFiles = uploadedFiles.filter(f => f.file_id !== fileId);
            renderAttachmentChips();
            fetchState();
        }

        function renderAttachmentChips() {
            const area = document.getElementById('attachmentArea');
            // Clear all chips but keep the upload button
            const uploadBtn = document.getElementById('attUploadBtn');
            const fileInput = document.getElementById('fileInput');
            area.innerHTML = '';
            area.appendChild(fileInput);
            area.appendChild(uploadBtn);

            uploadedFiles.forEach(f => {
                const chip = document.createElement('span');
                chip.className = 'att-chip' + (f.status === 'uploading' ? ' uploading' : '');
                if (f.status === 'uploading') {
                    chip.innerHTML = `
                        <span class="att-spinner"></span>
                        <span class="att-name">${escapeHtml(f.filename)}</span>
                        <span class="att-size">上传中...</span>
                    `;
                } else {
                    const sizeKB = (f.char_count / 1024).toFixed(1);
                    chip.innerHTML = `
                        <span class="att-name" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</span>
                        <span class="att-size">${sizeKB}KB</span>
                        <span class="att-modify" onclick="openModifyDialog('${f.file_id}', '${f.filename.replace(/'/g, "\\'")}')" title="修改文档">✏️</span>
                        <span class="att-remove" onclick="removeAttachment('${f.file_id}')" title="移除附件">×</span>
                    `;
                }
                area.appendChild(chip);
            });
        }

        async function fetchAttachments() {
            try {
                const resp = await fetch(`/api/agent/projects/${PROJECT_ID}/attachments`);
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

        // Drag-and-drop on chat area
        (function setupDragDrop() {
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
        })();

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

        // ── Chat ──
        function appendMessage(role, content) {
            const area = document.getElementById('chatArea');
            // Remove empty state
            const empty = area.querySelector('.empty-state');
            if (empty) empty.remove();

            const div = document.createElement('div');
            div.className = `msg ${role}`;
            div.innerHTML = formatContent(content);
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return div;
        }

        function toolLabel(tool) {
            if (tool === 'search_kb') return '检索知识库';
            if (tool === 'search_attachment') return '检索附件';
            if (tool === 'generate_section') return '生成章节';
            if (tool === 'modify_attachment') return '修改附件';
            if (tool === 'revise_section') return '修改章节';
            if (tool === 'build_docx') return '构建文档';
            if (tool === 'design_outline' || tool === 'outline_from_attachment') return '设计文档框架';
            if (tool === 'write_chapter') return '编写章节';
            if (tool === 'summarize_section' || tool === 'summarize_document') return '精简章节';
            return '处理';
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

        function appendRagResults(data) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'rag-results-box';
            const label = data.tool === 'search_attachment' ? '附件检索' : '知识库检索';
            let html = `<div class="rag-header" onclick="this.parentElement.classList.toggle('collapsed')">
                <span>📚 ${label}结果: 「${escapeHtml(data.query)}」 (${data.count}条)</span>
                <span class="rag-toggle">▼</span>
            </div><div class="rag-body">`;
            data.results.forEach((r, i) => {
                html += `<div class="rag-item">
                    <div class="rag-item-header">#${i+1} · 来源: ${escapeHtml(r.source)} · 相关度: ${(r.score*100).toFixed(1)}%</div>
                    <div class="rag-item-content">${escapeHtml(r.content)}</div>
                </div>`;
            });
            html += '</div></div>';
            div.innerHTML = html;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return div;
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
    window.open('/api/agent/download/' + downloadId, '_blank');
}

function showQuickDownloadBox() {
    // Don't add duplicate download boxes
    if (document.getElementById('quickDownloadBox')) return;
    const area = document.getElementById('chatArea');
    const div = document.createElement('div');
    div.className = 'download-box';
    div.id = 'quickDownloadBox';
    div.innerHTML = `
        <div class="dl-icon">📄</div>
        <div class="dl-info">
            <strong>${currentDocLabel || '文档'}.docx</strong>
            <div class="dl-size">点击按钮下载已生成的文档</div>
        </div>
        <button onclick="downloadDocument()">下载文档</button>
    `;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function editAndResume() {
            const instruction = prompt('请输入修改后的生成指令:', '');
            if (instruction) {
                resumeAgent('edit:' + instruction);
            }
        }

        function downloadDocument() {
            window.open('/api/agent/projects/' + PROJECT_ID + '/download', '_blank');
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

        function showModifiedDownloadButton(data) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = 'download-box';
            div.id = 'modifiedDownloadBox_' + (data.file_id || 'x');
            if (document.getElementById(div.id)) return; // 去重
            const summaryHtml = (data.summary || '').replace(/\n/g, '<br>');
            div.innerHTML = `
                <div class="dl-icon">📝</div>
                <div class="dl-info">
                    <strong>${escapeHtml(data.filename || '修改版文档')}</strong>
                    <div class="dl-size">修改完成${data.modified_chars ? ' · 修改后 ' + data.modified_chars + ' 字符' : ''}</div>
                    ${summaryHtml ? `<div class="dl-summary">${summaryHtml}</div>` : ''}
                </div>
                <button onclick="downloadModifiedDoc('${data.file_id || ''}')">下载修改版</button>
            `;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
        }

        function downloadModifiedDoc(fileId) {
            if (!fileId) { alert('缺少附件ID，无法下载'); return; }
            window.open('/api/agent/projects/' + PROJECT_ID + '/modified-documents/' + fileId + '/download', '_blank');
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

                const response = await fetch(`/api/agent/projects/${PROJECT_ID}/summarize`, {
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
            area.appendChild(div);
        }

        function formatContent(text) {
            if (!text) return '';
            // Basic markdown rendering
            return text
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
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
        async function sendMessage() {
            if (isStreaming) return;

            const input = document.getElementById('userInput');
            const message = input.value.trim();
            if (!message) return;

            // Show user message
            appendMessage('user', message);
            input.value = '';
            input.style.height = 'auto';

            // Disable input during streaming
            isStreaming = true;
            document.getElementById('sendBtn').disabled = true;

            let agentDiv = null;
            let currentTool = null;

            try {
                const formData = new FormData();
                formData.append('message', message);

                const response = await fetch(`/api/agent/projects/${PROJECT_ID}/messages`, {
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

                        switch (data.type) {
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                agentDiv.innerHTML += data.content
                                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                                    .replace(/\n/g, '<br>');
                                document.getElementById('chatArea').scrollTop =
                                    document.getElementById('chatArea').scrollHeight;
                                break;

                            case 'tool_start':
                                currentTool = data.tool;
                                appendToolIndicator(data.tool, true);
                                break;

                            case 'tool_end':
                                if (currentTool) {
                                    const el = document.getElementById(`tool-${currentTool}`);
                                    if (el) {
                                        el.innerHTML = `<div class="icon">✅</div>${currentTool === 'search_kb' ? '知识库检索完成' : currentTool === 'generate_section' ? '章节生成完成' : '修改完成'}`;
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
                showError('连接失败: ' + err.message);
            } finally {
                isStreaming = false;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('userInput').focus();

                // Refresh state sidebar and attachments
                fetchState();
                fetchAttachments();
            }
        }

        async function resumeAgent(decision) {
            if (isStreaming) return;

            // Remove approval bar
            const bar = document.getElementById('approvalBar');
            if (bar) bar.remove();

            isStreaming = true;
            document.getElementById('sendBtn').disabled = true;

            try {
                const formData = new FormData();
                formData.append('decision', decision);

                const response = await fetch(`/api/agent/projects/${PROJECT_ID}/resume`, {
                    method: 'POST',
                    body: formData,
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

                        switch (data.type) {
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                agentDiv.innerHTML += data.content
                                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                                    .replace(/\n/g, '<br>');
                                break;
                            case 'tool_start':
                                appendToolIndicator(data.tool, true);
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
                isStreaming = false;
                document.getElementById('sendBtn').disabled = false;
                fetchState();
                fetchAttachments();
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
            document.getElementById('autoGenBtn').disabled = true;

            let agentDiv = null;
            try {
                const formData = new FormData();
                formData.append('product_name', productName);
                formData.append('product_classification', classification);
                formData.append('product_intended_use', intendedUse);
                formData.append('doc_type', docType);

                const response = await fetch(`/api/agent/projects/${PROJECT_ID}/auto-generate`, {
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

                        switch (data.type) {
                            case 'token':
                                if (!agentDiv) agentDiv = appendMessage('agent', '');
                                agentDiv.innerHTML += data.content
                                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                                    .replace(/\n/g, '<br>');
                                area.scrollTop = area.scrollHeight;
                                break;
                            case 'tool_start':
                                appendToolIndicator(data.tool, true);
                                break;
                            case 'tool_end':
                                const el = document.getElementById(`tool-${data.tool}`);
                                if (el) {
                                    el.innerHTML = `<div class="icon">✅</div>${data.tool === 'search_kb' ? '知识库检索完成' : data.tool === 'generate_section' ? '章节生成完成' : data.tool === 'build_docx' ? '文档构建完成' : '工具执行完成'}`;
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
                document.getElementById('autoGenBtn').disabled = false;
                fetchState();
                fetchAttachments();
            }
        }

        async function fetchState() {
            try {
                const resp = await fetch(`/api/agent/projects/${PROJECT_ID}/state`);
                const data = await resp.json();
                if (data.success) {
                    renderSteps(data.state);
                    // Show download/review links if sections have been generated
                    const sections = data.state?.document_generation?.sections_generated || [];
                    const hasSections = sections.length > 0;
                    document.getElementById('downloadLink').style.display = hasSections ? 'inline' : 'none';
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
                }
            } catch (e) { /* Silently fail */ }
        }

        // ── Knowledge Base Upload (独立上传到 upload 向量知识库) ──
        // 复用后端 POST /api/upload?persist=true + GET /api/extract-status/{file_id}，
        // 上传不绑定任何项目会话，入库后任意对话的 RAG 检索均可命中。
        const KB_MAX_SIZE_BYTES = 10 * 1024 * 1024;
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
            if (files.length > 1) {
                showToast(`知识库上传完成：成功 ${successCount} 个，失败 ${failCount} 个`,
                    failCount ? 'error' : 'success', 6000);
            }
        }

        function validateKbFile(file) {
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            if (!KB_ALLOWED_FORMATS.includes(ext)) {
                return `不支持的文件格式「${ext}」。支持: ${KB_ALLOWED_FORMATS.join(' ')}`;
            }
            if (file.size > KB_MAX_SIZE_BYTES) {
                return `文件「${file.name}」超过 10MB 限制 (${(file.size / 1024 / 1024).toFixed(1)}MB)`;
            }
            if (file.size === 0) {
                return '文件为空，请上传有效文件';
            }
            return '';
        }

        async function uploadFileToKb(file) {
            const err = validateKbFile(file);
            if (err) {
                showToast(err, 'error', 6000);
                return false;
            }

            const toast = showToast(`正在上传「${file.name}」...`, 'uploading');

            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('persist', 'true');  // 独立入库 uploads 向量库

                const resp = await fetch('/api/upload', { method: 'POST', body: formData });
                if (!resp.ok) {
                    const errData = await resp.json().catch(() => ({}));
                    throw new Error(errData.detail || `上传失败 (HTTP ${resp.status})`);
                }
                const result = await resp.json();
                const fileId = result.file_id;

                // 轮询提取/入库状态（最长约 15 分钟，适配 MinerU 首次加载 + 多页推理耗时）
                for (let i = 0; i < 600; i++) {
                    updateToast(toast, `正在提取「${file.name}」...`);
                    await new Promise(r => setTimeout(r, 1500));
                    const statusResp = await fetch('/api/extract-status/' + fileId);
                    if (!statusResp.ok) {
                        if (statusResp.status === 404) {
                            throw new Error('提取任务已丢失（服务可能重启），请重试');
                        }
                        throw new Error('查询提取状态失败');
                    }
                    const status = await statusResp.json();
                    if (status.status === 'failed') {
                        throw new Error(status.message || '提取失败');
                    }
                    if (status.status === 'completed') {
                        dismissToast(toast);
                        if (status.persisted) {
                            showToast(`✓「${file.name}」已入库知识库 (${status.char_count} 字符)，可供 RAG 检索使用`, 'success', 5000);
                        } else {
                            showToast(`「${file.name}」文本提取完成 (${status.char_count} 字符)，但未写入向量库`, 'info', 5000);
                        }
                        return true;
                    }
                }
                throw new Error('提取超时（超过 15 分钟），请重试或使用更小的文档');
            } catch (e) {
                dismissToast(toast);
                showToast(`✗「${file.name}」上传失败: ${e.message}`, 'error', 6000);
                return false;
            }
        }

        // ── Init ──
        if (existingProject) {
            // 恢复已有项目：清除空状态，显示恢复提示
            const area = document.getElementById('chatArea');
            area.innerHTML = '';
            appendMessage('agent', '已恢复之前的会话。文档生成进度已加载，可继续操作或直接下载。');
            fetchState();
        }
        // 始终从服务端加载附件列表（新项目也可能已有上传记录）
        fetchAttachments();
        renderSteps({});
        document.getElementById('userInput').focus();
    