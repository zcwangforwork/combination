"""
Mermaid 流程图渲染服务

用 Playwright + 本地 mermaid.min.js 将 mermaid 源码渲染为 PNG 图片，
供 template.py 在 Markdown → Word 转换时把 ```mermaid 代码块插入为真实图片。

设计要点:
- mermaid.js 来自本地 node_modules（npm install mermaid），离线可用，数据不出企业。
- ★ 必须在【专用线程 + 显式 ProactorEventLoop】中运行，原因见 _render_in_dedicated_thread。
- 渲染失败会打印真实原因后返回 None，由调用方降级为代码文本，不中断文档生成。

★ 关于事件循环（历史坑，勿改回 sync_playwright）:
  app/main.py:16 为 psycopg（langgraph-checkpoint-postgres 驱动）设置了进程全局的
  WindowsSelectorEventLoopPolicy。而 Windows 的 SelectorEventLoop **不支持创建子进程**，
  Playwright（sync / async API 皆然）必须 asyncio.create_subprocess_exec 拉起 Node 驱动，
  于是必然在 asyncio/base_events.py subprocess_exec 处抛 NotImplementedError。

  asyncio.to_thread **无法**规避：set_event_loop_policy 是进程全局的，Playwright 在工作
  线程内 new_event_loop() 仍按该策略产出 SelectorEventLoop。

  解法：直接实例化 asyncio.ProactorEventLoop()（不经过 policy.new_event_loop()），
  并在专用线程内 set_event_loop —— 线程局部，不污染全局策略。
"""

import asyncio
import os
import sys
import threading
import traceback

# node_modules 相对本文件定位到项目根: app/services/ -> 项目根
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MERMAID_JS_CANDIDATES = [
    os.path.join(_PROJECT_ROOT, "node_modules", "mermaid", "dist", "mermaid.min.js"),
    os.path.join(_PROJECT_ROOT, "node_modules", "mermaid", "dist", "mermaid.js"),
]

# 页面模板：用占位符替换，避免 f-string 与 mermaid 源码中的 {} 冲突
_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<pre class="mermaid">__CODE__</pre>
<script>__MERMAID_JS__</script>
<script>
(function () {
  try {
    mermaid.initialize({startOnLoad: false, theme: 'default', flowchart: {useMaxWidth: true, htmlLabels: true}});
    mermaid.run({querySelector: '.mermaid'}).then(function () {
      document.body.setAttribute('data-render', 'ok');
    }).catch(function (err) {
      document.body.setAttribute('data-render', 'error');
      document.body.setAttribute('data-error', String(err && err.message || err));
    });
  } catch (e) {
    document.body.setAttribute('data-render', 'error');
    document.body.setAttribute('data-error', String(e && e.message || e));
  }
})();
</script>
</body>
</html>
"""


def _find_mermaid_js() -> str | None:
    """返回本地 mermaid.min.js 的绝对路径；不存在返回 None。"""
    for path in _MERMAID_JS_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _new_proactor_loop():
    """显式构造 ProactorEventLoop，绕过进程全局的 Selector 策略。

    Windows 上必须用 Proactor 才能创建子进程（Playwright 的 Node 驱动）；
    其他平台沿用默认事件循环即可。
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


async def _render_async(code: str, timeout_ms: int) -> bytes:
    """在 ProactorEventLoop 上用 async_playwright 渲染，返回 PNG 字节。

    失败时抛异常（不静默返回 None），由 _render_in_dedicated_thread 统一记录。
    """
    from playwright.async_api import async_playwright

    mermaid_js_path = _find_mermaid_js()
    with open(mermaid_js_path, encoding="utf-8") as f:
        mermaid_js = f.read()

    html = (_HTML_TEMPLATE
            .replace("__CODE__", code.strip())
            .replace("__MERMAID_JS__", mermaid_js))

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": 1400, "height": 900},
                device_scale_factor=2,
            )
            await page.set_content(html)
            # 等待渲染完成（成功或失败标志置位）
            await page.wait_for_function(
                "document.body.getAttribute('data-render') === 'ok' || "
                "document.body.getAttribute('data-render') === 'error'",
                timeout=timeout_ms,
            )
            if await page.get_attribute("body", "data-render") != "ok":
                # data-error 由页面脚本写入，此前从未被读取过，导致 mermaid
                # 语法错误完全不可见 —— 这里把它带出来
                err = await page.get_attribute("body", "data-error") or "(无错误信息)"
                raise RuntimeError(f"mermaid 渲染失败: {err[:500]}")
            svg = page.locator(".mermaid svg").first
            return await svg.screenshot(type="png")
        finally:
            await browser.close()


def _render_in_dedicated_thread(code: str, timeout_ms: int):
    """在专用线程中用显式 ProactorEventLoop 执行渲染。

    总是新建线程（而非复用调用线程），以保证：
    1. 该线程内没有正在运行的事件循环；
    2. 事件循环由本函数显式创建为 Proactor，不受全局 Selector 策略影响；
    3. 调用方无论处于事件循环线程（如 generator.py 直接调用）还是 to_thread
       工作线程（如 agent_tools.build_docx / routes.py 下载端点），行为一致。

    Returns:
        (png_bytes 或 None, 错误信息 或 None)
    """
    result: dict = {}

    def _worker():
        loop = _new_proactor_loop()
        asyncio.set_event_loop(loop)          # 线程局部，不影响其他线程/全局策略
        try:
            result["png"] = loop.run_until_complete(_render_async(code, timeout_ms))
        except BaseException as e:            # noqa: BLE001 - 需要把真实原因带出去
            result["error"] = e
        finally:
            try:
                loop.close()
            except Exception:
                pass
            asyncio.set_event_loop(None)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    return result.get("png"), result.get("error")


def render_mermaid_to_png(code: str, timeout_ms: int = 15000) -> bytes | None:
    """将 mermaid 源码渲染为 PNG 图片字节流。

    Args:
        code: mermaid 语法源码（不含 ```mermaid 围栏），如 "flowchart TD; A-->B;"。
        timeout_ms: 等待渲染完成的超时（毫秒）。

    Returns:
        PNG 图片 bytes；失败返回 None（失败原因会打印到日志，不再静默吞掉）。
    """
    if not code or not code.strip():
        return None

    if _find_mermaid_js() is None:
        print("[MERMAID] 渲染跳过: 未找到本地 mermaid.min.js，请检查 node_modules "
              f"(查找路径: {_MERMAID_JS_CANDIDATES})")
        return None

    try:
        import playwright  # noqa: F401
    except ImportError as e:
        print(f"[MERMAID] 渲染跳过: playwright 未安装 ({e})")
        return None

    png, error = _render_in_dedicated_thread(code, timeout_ms)
    if error is not None:
        # 不再静默返回 None：把真实原因暴露出来，否则此类故障无法定位
        print(f"[MERMAID] 渲染失败: {type(error).__name__}: {error}")
        if not isinstance(error, RuntimeError):
            # RuntimeError 是我们主动抛的 mermaid 语法错误，已含足够信息；
            # 其它异常附带堆栈便于排查环境类问题
            traceback.print_exception(type(error), error, error.__traceback__)
        return None

    return png
