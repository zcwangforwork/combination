
        // ── 常量与工具 ──────────────────────────────────────────
        const SEC_LABELS = ['公开', '内部', '秘密', '机密'];
        const MODE_LABELS = { shadow: 'shadow 影子', enforce: 'enforce 强制', off: 'off 关闭' };

        function esc(s) {
            if (s === null || s === undefined) return '';
            return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }
        function fmtTs(ts) { return ts ? String(ts).slice(0, 19).replace('T', ' ') : '—'; }

        let toastTimer = null;
        function showToast(text, ms = 3500) {
            const t = document.getElementById('toast');
            t.textContent = text;
            t.classList.add('show');
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => t.classList.remove('show'), ms);
        }

        async function apiFetch(url, options) {
            const resp = await fetch(url, options);
            let data = {};
            try { data = await resp.json(); } catch (e) { /* 非 JSON */ }
            if (!resp.ok) {
                const msg = (resp.status === 403)
                    ? (data.detail || '无管理员权限') : (data.detail || `HTTP ${resp.status}`);
                throw new Error(msg);
            }
            return data;
        }

        // ── 管理员门禁（客户端提示；服务端 /api/sec/* 仍强制 403） ──
        let IS_ADMIN = false;
        try {
            const _t = sessionStorage.getItem('agent_token') || '';
            const _p = _t.split('.')[1];
            if (_p) {
                let _b = _p.replace(/-/g, '+').replace(/_/g, '/');
                while (_b.length % 4) _b += '=';
                IS_ADMIN = (JSON.parse(decodeURIComponent(escape(atob(_b)))).role === 'ADMIN');
            }
        } catch (e) { /* ignore */ }
        if (!IS_ADMIN) {
            document.body.classList.add('not-admin');
            document.getElementById('adminGate').classList.add('show');
        }

        // ── Tab 切换 ────────────────────────────────────────────
        function switchTab(name) {
            document.querySelectorAll('.tab-btn').forEach(b =>
                b.classList.toggle('active', b.dataset.tab === name));
            document.querySelectorAll('.panel').forEach(p =>
                p.classList.toggle('active', p.id === 'panel-' + name));
            if (name === 'ledger' && !ledgerCache) loadLedger();
            if (name === 'denied' && !deniedLoaded) loadDeniedTop();
            if (name === 'mode') loadMode();
        }

        function secBadge(lvl) {
            if (lvl === null || lvl === undefined) {
                return '<span class="sec-badge sec-null">未标注</span>';
            }
            return `<span class="sec-badge sec-${lvl}">${lvl} ${SEC_LABELS[lvl]}</span>`;
        }

        // ── Tab 1：密级台账 ─────────────────────────────────────
        let ledgerCache = null;   // 全量缓存，筛选在前端做

        async function loadLedger() {
            const body = document.getElementById('ledgerBody');
            body.innerHTML = '<tr><td colspan="8" class="empty-hint">加载中…</td></tr>';
            try {
                const data = await apiFetch('/api/sec/ledger');
                ledgerCache = data.files || [];
                renderLedger();
            } catch (e) {
                body.innerHTML = `<tr><td colspan="8" class="empty-hint" style="color:#c62828">加载失败: ${esc(e.message)}</td></tr>`;
            }
        }

        function ledgerFiltered() {
            if (!ledgerCache) return [];
            const kw = document.getElementById('ledgerSearch').value.trim().toLowerCase();
            const lv = document.getElementById('ledgerLevel').value;
            const st = document.getElementById('ledgerState').value;
            return ledgerCache.filter(f => {
                if (kw && !(f.source_file || '').toLowerCase().includes(kw)) return false;
                const unlabeled = (f.sec_label === '未标注' || f.sec_level === null || f.sec_level === undefined);
                if (lv === 'unlabeled' ? !unlabeled : (lv !== '' && String(f.sec_level) !== lv)) return false;
                if (st === 'mixed' && !f.mixed) return false;
                if (st === 'unlabeled' && !unlabeled) return false;
                if (st === 'ok' && (f.mixed || unlabeled)) return false;
                return true;
            });
        }

        function renderLedger() {
            const body = document.getElementById('ledgerBody');
            if (!ledgerCache) return;
            const rows = ledgerFiltered();
            document.getElementById('ledgerCount').textContent = `共 ${rows.length} / ${ledgerCache.length} 个文件`;
            if (!rows.length) {
                body.innerHTML = '<tr><td colspan="8" class="empty-hint">无匹配文件</td></tr>';
                updateBatchBtn();
                return;
            }
            let html = '';
            for (const f of rows) {
                const unlabeled = (f.sec_label === '未标注' || f.sec_level === null || f.sec_level === undefined);
                const state = f.mixed
                    ? '<span class="state-tag state-mixed">不一致·需修复</span>'
                    : (unlabeled ? '<span class="state-tag state-unlabeled">未标注</span>' : '<span class="state-tag state-ok">正常</span>');
                const src = { manual: '手动', inherit: '继承', script: '脚本' }[f.sec_source] || (f.sec_source || '—');
                const cols = Array.isArray(f.collections) ? f.collections.join('、') : (f.collections || '');
                html += `<tr>
                    <td style="text-align:center"><input type="checkbox" class="ledger-check" value="${esc(f.source_file)}" onchange="updateBatchBtn()"></td>
                    <td title="${esc(cols)}">${esc(f.source_file)}</td>
                    <td>${secBadge(unlabeled ? null : f.sec_level)}</td>
                    <td>${esc(src)}</td>
                    <td style="text-align:right;color:#888">${f.chunk_count}</td>
                    <td>${state}</td>
                    <td style="color:#888;white-space:nowrap">${fmtTs(f.sec_updated_at)}</td>
                    <td><button class="mini-btn" onclick="openLevelModal('${esc(f.source_file)}')">修改密级</button></td>
                </tr>`;
            }
            body.innerHTML = html;
            updateBatchBtn();
        }

        function toggleLedgerSelAll(master) {
            document.querySelectorAll('.ledger-check').forEach(cb => cb.checked = master.checked);
            updateBatchBtn();
        }
        function selectedLedgerFiles() {
            return Array.from(document.querySelectorAll('.ledger-check:checked')).map(cb => cb.value);
        }
        function updateBatchBtn() {
            const n = selectedLedgerFiles().length;
            const btn = document.getElementById('batchLevelBtn');
            btn.disabled = n === 0;
            btn.textContent = n ? `批量修改密级（${n} 个文件）` : '批量修改密级';
        }

        // ── 密级变更弹窗（target=null 表示批量） ──
        let levelModalTarget = null;   // 单个 source_file 或 null=批量

        function openLevelModal(sourceFile) {
            levelModalTarget = sourceFile || null;
            document.getElementById('levelModalTitle').textContent = sourceFile
                ? `修改密级 — ${sourceFile}` : `批量修改密级（已选 ${selectedLedgerFiles().length} 个文件）`;
            document.getElementById('levelModalSelect').value = '3';
            document.getElementById('levelModalReason').value = '';
            document.getElementById('levelModalMask').classList.add('show');
        }
        function closeLevelModal() { document.getElementById('levelModalMask').classList.remove('show'); }

        async function submitLevelChange() {
            const files = levelModalTarget ? [levelModalTarget] : selectedLedgerFiles();
            if (!files.length) { closeLevelModal(); return; }
            const payload = {
                source_files: files,
                new_level: parseInt(document.getElementById('levelModalSelect').value, 10),
                reason: document.getElementById('levelModalReason').value.trim(),
            };
            const btn = document.getElementById('levelModalSubmit');
            btn.disabled = true;
            try {
                const data = await apiFetch('/api/sec/level', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const okN = (data.ok || []).length, failN = (data.failed || []).length;
                if (failN) showToast(`完成：成功 ${okN} 个，失败 ${failN} 个（${(data.failed[0] || {}).error || ''}）`, 6000);
                else showToast(`✓ 已将 ${okN} 个文件密级变更为 ${payload.new_level} ${SEC_LABELS[payload.new_level]}`);
                closeLevelModal();
                await loadLedger();
            } catch (e) {
                showToast(`变更失败: ${e.message}`, 5000);
            } finally {
                btn.disabled = false;
            }
        }

        // ── Tab 2：高频拦截 ─────────────────────────────────────
        let deniedLoaded = false;

        async function loadDeniedTop() {
            const body = document.getElementById('deniedBody');
            body.innerHTML = '<tr><td colspan="4" class="empty-hint">加载中…</td></tr>';
            try {
                const limit = document.getElementById('deniedLimit').value;
                const data = await apiFetch(`/api/sec/denied-top?limit=${limit}`);
                const items = data.items || [];
                deniedLoaded = true;
                if (!items.length) {
                    body.innerHTML = '<tr><td colspan="4" class="empty-hint">暂无拦截记录（shadow/enforce 模式下使用后产生）</td></tr>';
                    return;
                }
                let html = '';
                items.forEach((it, i) => {
                    html += `<tr>
                        <td style="color:#999">${i + 1}</td>
                        <td>${esc(it.source_file)}</td>
                        <td style="text-align:right"><b style="color:#c62828">${it.denied_count}</b></td>
                        <td style="color:#888;white-space:nowrap">${fmtTs(it.last_denied_at)}</td>
                    </tr>`;
                });
                body.innerHTML = html;
            } catch (e) {
                body.innerHTML = `<tr><td colspan="4" class="empty-hint" style="color:#c62828">加载失败: ${esc(e.message)}</td></tr>`;
            }
        }

        // ── Tab 3：检索审计 ─────────────────────────────────────
        async function loadAudit() {
            const body = document.getElementById('auditBody');
            body.innerHTML = '<tr><td colspan="9" class="empty-hint">查询中…</td></tr>';
            const q = new URLSearchParams();
            const u = document.getElementById('auditUser').value.trim();
            if (u) q.set('username', u);
            const s = document.getElementById('auditStart').value;
            if (s) q.set('start', s);
            const e2 = document.getElementById('auditEnd').value;
            if (e2) q.set('end', e2 + 'T23:59:59');
            const ml = document.getElementById('auditMinLevel').value;
            if (ml !== '-1') q.set('min_level', ml);
            const lk = document.getElementById('auditLeak').value;
            if (lk !== '-1') q.set('leak_blocked', lk);
            q.set('limit', '200');
            try {
                const data = await apiFetch('/api/sec/audit?' + q.toString());
                const items = data.items || [];
                document.getElementById('auditCount').textContent = `${items.length} 条`;
                if (!items.length) {
                    body.innerHTML = '<tr><td colspan="9" class="empty-hint">无匹配审计记录</td></tr>';
                    return;
                }
                let html = '';
                for (const r of items) {
                    html += `<tr>
                        <td style="color:#888;white-space:nowrap">${fmtTs(r.ts)}</td>
                        <td>${esc(r.username)}</td>
                        <td>L${r.sec_level_at_query ?? '—'}</td>
                        <td title="${esc(r.scope_summary || '')}">${esc(r.query_preview || '')}</td>
                        <td>${esc(r.mode)}</td>
                        <td style="text-align:right">${r.returned_count}</td>
                        <td style="text-align:right;color:#c62828">${r.denied_count}</td>
                        <td>${r.max_hit_level !== null && r.max_hit_level !== undefined ? secBadge(r.max_hit_level) : '—'}</td>
                        <td>${r.leak_blocked ? '✅ 已拦' : ''}</td>
                    </tr>`;
                }
                body.innerHTML = html;
            } catch (e) {
                body.innerHTML = `<tr><td colspan="9" class="empty-hint" style="color:#c62828">查询失败: ${esc(e.message)}</td></tr>`;
            }
        }

        // ── Tab 4：模式管理 ─────────────────────────────────────
        let currentMode = '';

        async function loadMode() {
            try {
                const data = await apiFetch('/api/sec/mode');
                currentMode = data.mode;
                renderMode(data);
            } catch (e) {
                document.getElementById('modeNowBig').textContent = '加载失败';
                document.getElementById('modeMeta').textContent = e.message;
            }
        }

        function renderMode(data) {
            const big = document.getElementById('modeNowBig');
            big.textContent = MODE_LABELS[data.mode] || data.mode;
            big.className = 'mode-now mode-' + data.mode;
            const over = data.runtime_override_by
                ? `运行时覆盖（由 ${data.runtime_override_by} 切换）` : '未设置运行时覆盖';
            document.getElementById('modeMeta').innerHTML =
                `环境变量缺省：<b>${esc(data.env_default)}</b><br>${esc(over)}`;
            ['shadow', 'enforce', 'off'].forEach(m => {
                const card = document.getElementById('modeCard-' + m);
                card.classList.toggle('current', m === data.mode);
                card.querySelector('.cur-mark').textContent = m === data.mode ? '·当前' : '';
            });
        }

        const MODE_TIPS = {
            shadow: '切换到 shadow：不实际过滤，仅记录本应拦截的内容。用于观察评估。',
            enforce: '⚠ 切换到 enforce 后立即生效：无权限用户检索将直接过滤掉保密内容，输出侧启用 L3 兜底拦截。请确认已完成存量回填与精标，避免未标注内容（按机密处理）大面积不可见。',
            off: '⚠ 切换到 off 将完全关闭密级过滤（回退改造前行为）。仅用于紧急回滚，请填写原因。',
        };

        function openModeModal(mode) {
            if (mode === currentMode) { showToast('当前已是该模式'); return; }
            document.getElementById('modeModalTitle').textContent = `切换到 ${MODE_LABELS[mode] || mode}`;
            document.getElementById('modeModalTip').textContent = MODE_TIPS[mode] || '';
            document.getElementById('modeModalReason').value = '';
            document.getElementById('modeModalMask').classList.add('show');
            window._pendingMode = mode;
        }
        function closeModeModal() { document.getElementById('modeModalMask').classList.remove('show'); }

        async function submitModeSwitch() {
            const mode = window._pendingMode;
            if (!mode) return;
            const reason = document.getElementById('modeModalReason').value.trim();
            if ((mode === 'enforce' || mode === 'off') && !reason) {
                showToast('切换到 enforce/off 必须填写原因（审计留痕）', 4000);
                return;
            }
            const btn = document.getElementById('modeModalSubmit');
            btn.disabled = true;
            try {
                const data = await apiFetch('/api/sec/mode', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode, reason }),
                });
                showToast(`✓ 模式已切换：${data.previous} → ${data.mode}`);
                closeModeModal();
                await loadMode();
                await refreshModeChip();
            } catch (e) {
                showToast(`切换失败: ${e.message}`, 5000);
            } finally {
                btn.disabled = false;
            }
        }

        // ── 顶栏模式徽章 ──
        async function refreshModeChip() {
            try {
                const data = await apiFetch('/api/sec/mode');
                const chip = document.getElementById('modeChip');
                const color = { shadow: '#e65100', enforce: '#c62828', off: '#666' }[data.mode] || '#999';
                chip.innerHTML = `当前过滤模式：<b style="color:${color}">${MODE_LABELS[data.mode] || data.mode}</b>`;
            } catch (e) { /* 顶栏徽章失败不阻断 */ }
        }

        // ── Init ──
        if (IS_ADMIN) {
            loadLedger();
            refreshModeChip();
        }
    