/*
 * token-relay.js — 新标签页（review/kb）JWT 凭证中转（用户隔离配套，combination 新增）
 *
 * SPA(:3000) 的 window.open 无法给跨源页面带 Authorization 头，凭证改经 URL
 * #jwt= 片段传递（fragment 不发给服务器、不进服务端访问日志）。本脚本：
 *   1. 读取 location.hash 中的 jwt → 存 sessionStorage（:8002 源，仅本标签页有效）
 *   2. 清除地址栏 hash（history.replaceState，避免残留在本机浏览器历史）
 *   3. 包装 fetch：同源 /api/** 请求自动注入 Authorization: Bearer 头
 *   4. 401 → 顶部横幅提示（token 过期，或未经 SPA 直接打开本页）
 *
 * 引用方：app/static/review.html、app/static/kb.html（<head> 内最先加载，
 * 必须先于页面自身的内联脚本执行，否则首屏 API 调用拿不到凭证）
 */
(function () {
    var m = /[#&]jwt=([^&]+)/.exec(location.hash);
    if (m) {
        try { sessionStorage.setItem('agent_token', decodeURIComponent(m[1])); } catch (e) { /* ignore */ }
        try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { /* ignore */ }
    }

    function _token() {
        try { return sessionStorage.getItem('agent_token') || ''; } catch (e) { return ''; }
    }

    function _showAuthError() {
        var box = document.getElementById('agentAuthError');
        if (!box) {
            box = document.createElement('div');
            box.id = 'agentAuthError';
            box.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;'
                + 'background:#c62828;color:#fff;padding:10px 16px;font-size:14px;'
                + 'text-align:center;';
            box.textContent = '登录凭证缺失或已过期：请从体系管理系统「AI 文档写作」页面重新打开本页';
            (document.body || document.documentElement).appendChild(box);
        }
    }

    if (!_token()) {
        // 无凭证（直接输 URL 打开/书签进入）：页面 API 调用将 401，先给出可读提示
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', _showAuthError);
        } else {
            _showAuthError();
        }
    }

    var _rawFetch = window.fetch.bind(window.fetch);
    window.fetch = function (input, init) {
        var p;
        try {
            var url = (typeof input === 'string') ? input : ((input && input.url) || '');
            var t = _token();
            // 本页与 Agent 服务同源，API 均为相对路径 /api/**；
            // 端口直连形态（:8002-8004）一并覆盖
            var isApi = url.indexOf('/api/') === 0 || /:800[234]\/api\//.test(url);
            if (t && isApi) {
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
