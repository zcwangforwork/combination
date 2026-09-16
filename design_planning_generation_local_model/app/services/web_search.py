"""
WebSearchService - 网页搜索服务

用于在生成文档章节时搜索相关法规标准信息。
支持多种搜索后端：duckduckgo_search 库（首选）、Playwright 浏览器（备用）。
"""
import os
import sys
import re
import asyncio
import tempfile
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from urllib.parse import urljoin, urlparse, quote as url_quote

# 后端可用性检查（延迟导入）
_playwright_available = None
_ddg_library_available = None

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def _check_ddg_library():
    """检查 ddgs 库是否可导入（不做实时网络探测，避免瞬时网络/限流失败永久禁用该后端）"""
    global _ddg_library_available
    if _ddg_library_available is None:
        try:
            import ddgs  # 仅检查包可导入
            _ddg_library_available = True
        except ImportError:
            _ddg_library_available = False
    return _ddg_library_available


def _check_playwright():
    """检查 Playwright 是否可用"""
    global _playwright_available
    if _playwright_available is None:
        try:
            from playwright.async_api import async_playwright
            _playwright_available = True
        except ImportError:
            _playwright_available = False
    return _playwright_available


# 章节 → 搜索查询映射
CHAPTER_SEARCH_QUERIES = {
    "概述": [
        "{product_type} 医疗器械 法规要求 注册",
        "ISO 14971 医疗器械风险管理 概述",
    ],
    "风险分析": [
        "{product_type} 危害分析 风险评估 危害判定",
        "ISO 14971 危害识别 安全性特征",
    ],
    "风险评估": [
        "医疗器械 严重度 频度数 探测度 评价准则",
        "GB 42062 风险评估 风险等级",
    ],
    "风险控制": [
        "医疗器械 风险控制措施 ALARP 最优化原则",
        "ISO 14971 风险控制 防护措施",
    ],
    "剩余风险评价": [
        "医疗器械 剩余风险 综合评价 受益分析",
        "ISO 14971 残余风险 风险受益比",
    ],
    "风险管理评审结论": [
        "医疗器械 风险管理评审 文档批准 结论",
        "ISO 14971 风险管理报告 评审",
    ],
    "目的和范围": [
        "{product_type} 风险管理目的 适用范围 适用性",
        "ISO 14971 风险管理计划 范围定义",
    ],
    "产品描述": [
        "{product_type} 产品描述 结构组成 技术参数",
        "医疗器械 产品技术要求 规格型号",
    ],
    "人员资格和职责": [
        "医疗器械 人员资格 职责分配 风险管理团队",
        "ISO 14971 人员能力 职责要求",
    ],
    "风险可接受性准则": [
        "医疗器械 风险可接受准则 严重度 频度数",
        "GB 42062 风险可接受准则 RPN",
    ],
    "风险管理活动计划": [
        "医疗器械 风险管理活动 计划 评审安排",
        "ISO 14971 风险管理计划 活动安排",
    ],
    "生产和生产后信息收集": [
        "医疗器械 生产后信息 信息收集 上市后监督",
        "ISO 14971 上市后信息 生产后信息",
    ],
    "FMEA概述": [
        "FMEA 失效模式与效应分析 概述 目的 范围",
        "GB 42062 FMEA 分析方法",
    ],
    "严重度频度数探测度评价准则": [
        "FMEA 严重度 频度数 探测度 评价准则",
        "严重度等级 频度数等级 探测度等级",
    ],
    "FMEA分析表": [
        "FMEA分析表 失效模式 失效效应 失效原因",
        "FMEA分析 风险数 RPN 计算",
    ],
    "高风险项目改进措施": [
        "FMEA 高风险项目 改进措施 RPN阈值",
        "FMEA 风险控制 改进措施跟踪",
    ],
    "风险可接受性判定": [
        "FMEA 风险可接受性 RPN判定 阈值",
        "FMEA 风险评估 接受准则",
    ],
    "FMEA分析结论": [
        "FMEA分析结论 建议 文档批准",
        "FMEA 总结 改进建议",
    ],
    "型号规格": [
        "{product_type} 型号规格 结构组成",
        "医疗器械技术要求 规格参数",
    ],
    "性能指标": [
        "{product_type} 性能指标 物理性能 化学性能",
        "医疗器械性能指标 检验指标",
    ],
    "检验方法": [
        "{product_type} 检验方法 检验规则 型式试验",
        "医疗器械检验方法 出厂检验 型式检验",
    ],
    "标志包装运输贮存": [
        "医疗器械 标志 包装 运输 贮存",
        "医疗器械标签 说明书 包装要求",
    ],
    "产品信息": [
        "{product_type} 产品信息 名称 型号 生产企业",
        "医疗器械注册 名称 型号 规格",
    ],
    "适用范围": [
        "{product_type} 适用范围 适应症 禁忌症",
        "医疗器械 预期用途 临床使用",
    ],
    "使用方法": [
        "{product_type} 使用方法 操作步骤 使用前准备",
        "医疗器械使用说明书 操作指南",
    ],
    "注意事项": [
        "{product_type} 注意事项 警示 警告 警告说明",
        "医疗器械 警告 警示 注意事项",
    ],
    "维护保养": [
        "{product_type} 维护保养 故障排除 维修",
        "医疗器械 维护保养 清洁 校准",
    ],
    "目的和范围_SOP": [
        "SOP 目的 范围 引用文件 适用范围",
        "作业指导书 标准操作规程 编写要求",
        "{product_type} 生产作业指导书 目的范围",
    ],
    "职责_SOP": [
        "SOP 职责 部门 人员资质 权限",
        "作业指导书 职责分配 人员要求",
        "{product_type} 生产操作 岗位职责",
    ],
    "操作步骤_SOP": [
        "SOP 操作步骤 工艺流程 质量控制点",
        "标准操作规程 操作步骤 作业流程",
        "{product_type} 生产工艺 操作程序",
        "医疗器械 生产过程 作业指导书 步骤",
    ],
    "安全注意事项_SOP": [
        "SOP 安全注意事项 防护措施 应急处理",
        "作业指导书 安全注意事项 风险防护",
        "{product_type} 生产安全 操作规程 防护",
    ],
    "SOP目的和范围": [
        "医疗器械 作业指导书 SOP 目的范围",
        "标准操作规程 编写规范 适用范围",
        "{product_type} 生产 SOP 目的",
    ],
    "SOP职责": [
        "医疗器械 SOP 人员职责 岗位责任",
        "作业指导书 权限分配 资质要求",
        "{product_type} 生产 人员职责",
    ],
    "SOP操作步骤": [
        "医疗器械 生产工艺 详细操作步骤",
        "作业指导书 流程 质量控制点",
        "{product_type} 生产过程 操作方法",
    ],
    "SOP安全注意事项": [
        "医疗器械 生产安全 防护措施 应急",
        "作业指导书 安全规程 注意事项",
        "{product_type} 操作安全 防护要求",
    ],
}

# SOP专用搜索查询 - 更专业的作业指导书相关搜索
SOP_SPECIFIC_QUERIES = [
    "{product_type} 医疗器械 生产作业指导书 模板",
    "{product_type} 标准操作规程 SOP 完整版",
    "{product_type} 生产工艺 作业指导书 详细",
    "医疗器械 生产质量管理规范 作业指导书",
    "ISO 13485 生产过程 作业指导书",
    "{product_type} 操作手册 维护保养 规程",
    "医疗器械 洁净区 作业指导书 清洁消毒",
    "{product_type} 工艺规程 生产流程 质量控制",
]

# 文件下载相关搜索
FILE_SEARCH_QUERIES = [
    "{product_type} 作业指导书 filetype:doc",
    "{product_type} SOP template filetype:docx",
    "{product_type} 操作规程 filetype:pdf",
    "医疗器械 作业指导书 模板 filetype:doc",
    "{product_type} 生产工艺规程 filetype:pdf",
]

# 可下载的文件扩展名
DOWNLOADABLE_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx']


class EnhancedWebSearchService:
    """增强版网页搜索服务 - 支持多后端、深度抓取、文件下载、知识库更新"""

    def __init__(self, download_dir: Optional[str] = None):
        self.ddg_available = _check_ddg_library()
        self.playwright_available = _check_playwright()
        self._browser = None
        self.download_dir = download_dir or str(project_root / "downloads" / "web")
        os.makedirs(self.download_dir, exist_ok=True)

    async def search_regulations(
        self,
        chapter_name: str,
        product_type: str,
        product_params: str = "",
        max_results: int = 3,
        enable_deep_scrape: bool = True,
        enable_file_download: bool = True,
        doc_type: str = "sop"
    ) -> Tuple[str, List[str]]:
        """
        搜索相关法规标准信息

        Args:
            chapter_name: 章节名称
            product_type: 产品类型
            product_params: 产品参数
            max_results: 最大搜索结果数
            enable_deep_scrape: 是否启用深度网页抓取
            enable_file_download: 是否启用文件下载
            doc_type: 文档类型（用于决定知识库）

        Returns:
            (formatted_text, downloaded_files) 元组
        """
        # 构建搜索查询
        queries = self._build_search_queries(chapter_name, product_type, doc_type)
        if not queries:
            return "", []

        all_results = []
        downloaded_files = []

        try:
            for query in queries[:2]:  # 只执行前2个查询避免超时
                results, files = await self._search_with_best_backend(
                    query, max_results, enable_deep_scrape,
                    enable_file_download, doc_type
                )
                all_results.extend(results)
                downloaded_files.extend(files)

            formatted_text = self._format_results(all_results[:max_results * 2])
            return formatted_text, downloaded_files

        except Exception as e:
            print(f"    [WEB SEARCH] 搜索失败: {e}")
            return "", []

    async def search_general(
        self,
        query: str,
        max_results: int = 3,
        enable_deep_scrape: bool = True,
    ) -> Tuple[str, List[str]]:
        """通用搜索：直接用原始关键词搜索互联网，不做医疗法规查询改写。

        用于 agent 回答天气、新闻等实时性问题时检索即时信息。
        走 ddgs 优先 + 重试 + Playwright 备用的通用后端，返回格式化文本。
        """
        try:
            results, files = await self._search_with_best_backend(
                query, max_results, enable_deep_scrape,
                enable_file_download=False, doc_type="general"
            )
            if not results:
                return "", []
            return self._format_results(results[: max_results * 2]), files
        except Exception as e:
            print(f"    [WEB SEARCH] 通用搜索失败: {e}")
            return "", []

    async def _search_with_best_backend(
        self, query: str, max_results: int,
        enable_deep_scrape: bool, enable_file_download: bool, doc_type: str
    ) -> Tuple[List[Dict], List[str]]:
        """选择最佳可用后端执行搜索"""
        # 首选: duckduckgo_search 库（无浏览器，不会被检测）。
        # 瞬时网络波动/限流可能导致偶发失败或空结果，重试一次再降级到 Playwright，
        # 避免单一瞬时失败直接丢掉最可靠的 ddgs 后端。
        if self.ddg_available:
            for attempt in range(2):
                try:
                    results = await self._search_ddg_library(query, max_results)
                    if results:
                        return results, []
                    if attempt == 0:
                        print("    [WEB SEARCH] DDG库返回空结果，重试一次")
                except Exception as e:
                    print(f"    [WEB SEARCH] DDG库搜索失败(第{attempt + 1}次): {e}")
                if attempt == 0:
                    await asyncio.sleep(1.5)

        # 备用: Playwright 浏览器爬虫
        if self.playwright_available:
            try:
                return await self._search_deep(
                    query, max_results, enable_deep_scrape,
                    enable_file_download, doc_type
                )
            except Exception as e:
                print(f"    [WEB SEARCH] Playwright搜索失败: {e}")

        return [], []

    async def _search_ddg_library(self, query: str, max_results: int) -> List[Dict]:
        """使用 ddgs 库搜索（推荐方式，无浏览器检测问题）"""
        import concurrent.futures

        def _do_search():
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")[:300],
                        "deep_content": ""
                    })
            return results

        # DDGS 是同步的，用线程池执行避免阻塞事件循环
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = await loop.run_in_executor(executor, _do_search)

        if results:
            print(f"    [DDG LIB] 搜索 '{query[:50]}...' 返回 {len(results)} 条结果")
        return results

    def _build_search_queries(
        self,
        chapter_name: str,
        product_type: str,
        doc_type: str
    ) -> List[str]:
        """根据章节名构建搜索查询"""
        queries = []

        # 标准化章节名
        normalized_name = chapter_name.replace("第X章 ", "").strip()

        # SOP文档使用特殊查询
        if doc_type == "sop":
            # 添加SOP专用查询
            for q in SOP_SPECIFIC_QUERIES:
                queries.append(q.format(product_type=product_type))

        # 尝试精确匹配章节
        if normalized_name in CHAPTER_SEARCH_QUERIES:
            chapter_queries = CHAPTER_SEARCH_QUERIES[normalized_name]
            queries.extend([q.format(product_type=product_type) for q in chapter_queries])
        else:
            # 尝试模糊匹配
            for key, chapter_queries in CHAPTER_SEARCH_QUERIES.items():
                if normalized_name in key or key in normalized_name:
                    queries.extend([q.format(product_type=product_type) for q in chapter_queries])
                    break

        # 默认查询
        if not queries:
            queries.append(f"{product_type} 医疗器械 法规标准 {normalized_name}")

        # 添加文件搜索查询（如果是SOP）
        if doc_type == "sop":
            for q in FILE_SEARCH_QUERIES[:2]:
                queries.append(q.format(product_type=product_type))

        return queries

    async def _search_deep(
        self,
        query: str,
        max_results: int = 3,
        enable_deep_scrape: bool = True,
        enable_file_download: bool = True,
        doc_type: str = "sop"
    ) -> Tuple[List[Dict], List[str]]:
        """执行深度搜索并抓取内容。

        ★ Playwright 必须在「专用线程 + 显式 ProactorEventLoop」中运行：
        app/main.py:16 为 psycopg（langgraph-checkpoint-postgres 驱动）设置了进程全局的
        WindowsSelectorEventLoopPolicy，而 Windows 的 SelectorEventLoop 不支持创建子进程，
        Playwright 拉起 Node 驱动时会在 asyncio create_subprocess_exec 处抛
        NotImplementedError。asyncio.to_thread 本身不能规避（全局策略对工作线程内新建的
        loop 同样生效），故须在 _search_deep_sync 中显式构造 ProactorEventLoop ——
        线程局部，不污染全局策略。详见 app/services/mermaid_render.py 模块 docstring。
        """
        return await asyncio.to_thread(
            self._search_deep_sync,
            query, max_results, enable_deep_scrape, enable_file_download, doc_type,
        )

    def _search_deep_sync(
        self,
        query: str,
        max_results: int,
        enable_deep_scrape: bool,
        enable_file_download: bool,
        doc_type: str,
    ) -> Tuple[List[Dict], List[str]]:
        """在工作线程内用显式 ProactorEventLoop 驱动 _search_deep_impl（同步入口）。"""
        loop = (asyncio.ProactorEventLoop() if sys.platform == "win32"
                else asyncio.new_event_loop())
        asyncio.set_event_loop(loop)      # 线程局部，不影响其他线程与全局策略
        try:
            return loop.run_until_complete(
                self._search_deep_impl(
                    query, max_results, enable_deep_scrape,
                    enable_file_download, doc_type,
                )
            )
        finally:
            try:
                loop.close()
            except Exception:
                pass
            asyncio.set_event_loop(None)

    async def _search_deep_impl(
        self,
        query: str,
        max_results: int = 3,
        enable_deep_scrape: bool = True,
        enable_file_download: bool = True,
        doc_type: str = "sop"
    ) -> Tuple[List[Dict], List[str]]:
        """深度搜索的实际实现（在 ProactorEventLoop 中执行）"""
        from playwright.async_api import async_playwright

        results = []
        downloaded_files = []

        async with async_playwright() as p:
            # 启动浏览器 — 使用更真实的指纹避免被搜索引擎拦截
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            # 隐藏自动化特征
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            """)
            page = await context.new_page()

            try:
                # 使用 Bing 搜索（比 DuckDuckGo 中文结果更好）
                # 必须 URL 编码中文查询，否则 Bing 收到乱码返回无关结果
                search_url = f"https://www.bing.com/search?q={url_quote(query)}"

                await page.goto(search_url, timeout=20000, wait_until="domcontentloaded")

                # 等待结果加载
                await page.wait_for_selector("li.b_algo", timeout=10000)

                # 使用 JS 提取搜索结果（textContent 比 inner_text() 更可靠，
                # 因为 Bing 的 CSS 渲染可能导致 inner_text() 返回空字符串）
                extracted = await page.evaluate(f"""
                    () => {{
                        const items = [];
                        document.querySelectorAll('li.b_algo').forEach(li => {{
                            const h2 = li.querySelector('h2');
                            const a = h2 ? h2.querySelector('a') : null;
                            const snippetEl = li.querySelector('.b_lineclamp2')
                                || li.querySelector('.b_caption p')
                                || li.querySelector('p');
                            // 优先使用 cite 中的真实 URL，回退到 a.href
                            const citeEl = li.querySelector('cite');
                            const realUrl = citeEl ? citeEl.textContent.trim() : (a ? a.href : '');
                            if (a && a.textContent.trim()) {{
                                items.push({{
                                    title: a.textContent.trim(),
                                    href: realUrl,
                                    snippet: snippetEl ? snippetEl.textContent.trim() : ''
                                }});
                            }}
                        }});
                        return items.slice(0, {max_results});
                    }}
                """)

                for item in extracted:
                    title = item.get("title", "")
                    url = item.get("href", "")
                    snippet = item.get("snippet", "")

                    if title and url:
                        # 检查是否是可下载文件
                        is_downloadable = any(
                            ext.lower() in url.lower()
                            for ext in DOWNLOADABLE_EXTENSIONS
                        )

                        if is_downloadable and enable_file_download:
                            downloaded = await self._try_download_file(
                                page, url, title, doc_type
                            )
                            if downloaded:
                                downloaded_files.append(downloaded)

                        # 深度抓取网页内容
                        deep_content = ""
                        if enable_deep_scrape and not is_downloadable:
                            deep_content = await self._scrape_page_content(
                                context, url
                            )

                        results.append({
                            "title": title.strip(),
                            "url": url.strip(),
                            "snippet": snippet.strip()[:300],
                            "deep_content": deep_content
                        })

            except Exception as e:
                print(f"    [WEB SEARCH] 页面加载失败: {e}")
                # 回退到DuckDuckGo
                try:
                    results = await self._search_duckduckgo(context, query, max_results)
                except Exception as e2:
                    print(f"    [WEB SEARCH] DuckDuckGo 也失败: {e2}")
            finally:
                await browser.close()

        return results, downloaded_files

    async def _search_duckduckgo(self, context, query: str, max_results: int) -> List[Dict]:
        """备用搜索：DuckDuckGo"""
        page = await context.new_page()
        results = []

        try:
            search_url = f"https://duckduckgo.com/?q={url_quote(query)}&ia=web"
            await page.goto(search_url, timeout=15000, wait_until="domcontentloaded")

            # 等待搜索结果渲染
            await asyncio.sleep(2)

            # 使用 JS 提取（DDG 的 DOM 结构经常变化，JS 更可靠）
            extracted = await page.evaluate(f"""
                () => {{
                    const items = [];
                    // 尝试多种 DDG 选择器
                    const selectors = [
                        'article[data-testid="result"]',
                        'div[data-result]',
                        '.result__body',
                        '.result',
                        'li[data-layout="organic"]'
                    ];
                    let resultElements = [];
                    for (const sel of selectors) {{
                        resultElements = document.querySelectorAll(sel);
                        if (resultElements.length > 0) break;
                    }}
                    resultElements.forEach((el, i) => {{
                        if (i >= {max_results}) return;
                        const a = el.querySelector('h2 a') || el.querySelector('a[data-testid="result-title-a"]');
                        const snippetEl = el.querySelector('[data-snippet]') || el.querySelector('.result__snippet') || el.querySelector('p');
                        if (a && a.textContent.trim()) {{
                            items.push({{
                                title: a.textContent.trim(),
                                href: a.href,
                                snippet: snippetEl ? snippetEl.textContent.trim() : ''
                            }});
                        }}
                    }});
                    return items;
                }}
            """)

            for item in extracted:
                title = item.get("title", "")
                url = item.get("href", "")
                snippet = item.get("snippet", "")
                if title and snippet:
                    results.append({
                        "title": title.strip(),
                        "url": url.strip(),
                        "snippet": snippet.strip()[:300],
                        "deep_content": ""
                    })
        except Exception as e:
            print(f"    [WEB SEARCH] DuckDuckGo 搜索失败: {e}")
        finally:
            await page.close()

        return results

    async def _scrape_page_content(self, context, url: str) -> str:
        """深度抓取单个网页内容"""
        # 跳过搜索引擎中转/追踪链接（如 Bing /ck/a 重定向），这类页面无实质内容
        if any(pat in url for pat in ["bing.com/ck/a", "google.com/url?", "r.duckduckgo.com"]):
            return ""

        # 如果 URL 不含 scheme，添加 https://
        if not url.startswith("http"):
            url = "https://" + url

        page = await context.new_page()
        content = ""

        try:
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)  # 等待页面渲染

            # 提取主要文本内容
            # 尝试多个选择器
            selectors = [
                "main", "article", "div.content", "div.main-content",
                "section", ".post", ".article", "#content"
            ]

            for selector in selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    for elem in elements[:3]:
                        try:
                            text = await elem.inner_text()
                            if text and len(text) > 100:
                                content += "\n" + text
                        except Exception:
                            pass
                    if content:
                        break

            # 如果没有找到特定选择器，获取整个body文本
            if not content:
                body = await page.query_selector("body")
                if body:
                    content = await body.inner_text()

            # 清理和截断
            content = re.sub(r'\n\s*\n', '\n\n', content)
            content = content.strip()[:4000]  # 限制长度

        except Exception as e:
            print(f"    [WEB SCRAPE] 抓取页面失败 {url}: {e}")
        finally:
            await page.close()

        return content

    async def _try_download_file(
        self,
        page,
        url: str,
        title: str,
        doc_type: str
    ) -> Optional[str]:
        """尝试下载文件"""
        try:
            # 创建doc_type专用目录
            doc_dir = os.path.join(self.download_dir, doc_type)
            os.makedirs(doc_dir, exist_ok=True)

            # 生成文件名
            parsed = urlparse(url)
            ext = os.path.splitext(parsed.path)[1] or ".pdf"
            safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title[:50])
            filename = f"{safe_title}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
            filepath = os.path.join(doc_dir, filename)

            # 下载文件
            print(f"    [DOWNLOAD] 尝试下载: {title}")

            # 启动新页面下载
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(accept_downloads=True)
                dl_page = await context.new_page()

                # 设置下载路径
                download_path = None
                download_future = asyncio.Future()

                async def handle_download(download):
                    nonlocal download_path
                    download_path = filepath
                    await download.save_as(download_path)
                    download_future.set_result(True)

                dl_page.on("download", handle_download)

                try:
                    await dl_page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    # 等待一小段时间看是否有下载触发
                    await asyncio.sleep(2)

                    if download_path and os.path.exists(download_path):
                        print(f"    [DOWNLOAD] 成功: {filename}")
                        return download_path
                except Exception as e:
                    print(f"    [DOWNLOAD] 下载失败: {e}")
                finally:
                    await browser.close()

        except Exception as e:
            print(f"    [DOWNLOAD] 下载异常: {e}")

        return None

    def _format_results(self, results: List[Dict]) -> str:
        """格式化搜索结果"""
        if not results:
            return ""

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r['title']}")
            lines.append(f"    来源: {r['url']}")
            lines.append(f"    摘要: {r['snippet']}")
            if r.get('deep_content'):
                content = r['deep_content'][:1000]
                lines.append(f"    详细内容: {content}")
            lines.append("")

        return "\n".join(lines)


class WebSearchService:
    """网页搜索服务 - 简化版接口（向后兼容）"""

    def __init__(self):
        self.enhanced = EnhancedWebSearchService()
        self.playwright_available = self.enhanced.playwright_available

    async def search_regulations(
        self,
        chapter_name: str,
        product_type: str,
        product_params: str = "",
        max_results: int = 3
    ) -> str:
        """搜索相关法规标准信息（简化版）"""
        text, _ = await self.enhanced.search_regulations(
            chapter_name, product_type, product_params, max_results,
            enable_deep_scrape=True, enable_file_download=True
        )
        return text


# 同步包装器
class SyncWebSearchService:
    """同步包装器，用于非 async 上下文"""

    def __init__(self, download_dir: Optional[str] = None):
        self.async_service = EnhancedWebSearchService(download_dir)
        # 只要有任一后端可用即可
        self.playwright_available = self.async_service.playwright_available or self.async_service.ddg_available

    def search_regulations(
        self,
        chapter_name: str,
        product_type: str,
        product_params: str = "",
        max_results: int = 3,
        enable_deep_scrape: bool = True,
        enable_file_download: bool = True,
        doc_type: str = "sop"
    ) -> Tuple[str, List[str]]:
        """同步搜索（内部使用独立线程避免事件循环冲突）"""
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.async_service.search_regulations(
                        chapter_name, product_type, product_params, max_results,
                        enable_deep_scrape, enable_file_download, doc_type
                    )
                )
                return future.result(timeout=60)
        except Exception as e:
            print(f"    [WEB SEARCH] 同步调用失败: {e}")
            return "", []

    def search_general(
        self,
        query: str,
        max_results: int = 3,
        enable_deep_scrape: bool = True,
    ) -> Tuple[str, List[str]]:
        """通用搜索（同步包装，内部使用独立线程避免事件循环冲突）"""
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.async_service.search_general(query, max_results, enable_deep_scrape)
                )
                return future.result(timeout=60)
        except Exception as e:
            print(f"    [WEB SEARCH] 同步通用搜索失败: {e}")
            return "", []
