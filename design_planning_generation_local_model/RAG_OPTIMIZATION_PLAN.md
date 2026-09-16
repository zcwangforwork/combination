# RAG 文档生成系统优化方案

## 背景

当前 `project_0430_02` 的文档生成系统已实现分章节生成，但在 RAG 增强和参考资料利用方面存在优化空间：
- 向量库已有 251 chunks，来自 54 个文档
- RAG 默认关闭，需手动启用
- Chunk size 500 字符偏小
- 仅支持语义检索，无关键词匹配
- 无网页搜索补充能力

---

## 优化目标

1. **更多依据 develop_documents 资料生成** - 增大 chunk、优化检索策略
2. **RAG 效果优化** - 多路召回、重排序、查询扩展
3. **网页信息补充** - 集成 Playwright 搜索相关法规标准

---

## 方案设计

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    _generate_by_chapters()                      │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐    │
│  │  DOC_CHAPTERS │───▶│  章节N Query  │───▶│               │    │
│  └───────────────┘    └───────────────┘    │  1. RAG检索   │    │
│                                              │  2. Web搜索   │    │
│                                              │  3. 结果合并   │    │
│                                              │  4. Prompt组装│    │
└──────────────────────────────────────────────│               │    │
                                               └───────┬───────┘    │
                                                       │            │
                               ┌───────────────────────┼────────┐   │
                               ▼                       ▼        ▼   │
                    ┌─────────────────┐    ┌──────────────┐  ┌──┐  │
                    │  ChromaDB       │    │  Playwright   │  │AI│  │
                    │  向量检索       │    │  网页搜索     │  │   │  │
                    │  + BM25        │    │  法规标准查询 │  └──┘  │
                    └─────────────────┘    └──────────────┘       │
                              │                                        │
                              ▼                                        │
                    ┌─────────────────┐                               │
                    │  Rerank (可选)  │                               │
                    │  Cross-Encoder  │                               │
                    └─────────────────┘                               │
```

---

## 1. RAG 检索优化

### 1.1 增大 Chunk Size

**当前**: `CHUNK_SIZE = 500` (字符)

**优化**: `CHUNK_SIZE = 1000`

**理由**:
- 500字符会切断表格、列表等结构
- 1000字符保留更完整的语义单元
- ChromaDB 不限制向量维度，影响不大

### 1.2 增加 Top_K

**当前**: `top_k=3`

**优化**: `top_k=5`

**理由**:
- 3条太少，可能遗漏相关段落
- 5条给后续重排序留出选择空间
- API token 预算可控（单章节max_tokens=8000）

### 1.3 多路召回 (Hybrid Search)

```python
# 伪代码 - vector_store.py 新增方法
def retrieve_hybrid(
    query: str,
    doc_type: str = None,
    top_k: int = 5,
    similarity_threshold: float = 0.3
) -> list[dict]:
    """
    混合检索：语义向量检索 + BM25关键词检索
    """
    # 1. 向量检索
    vector_results = self.retrieve(query, doc_type, top_k * 2, similarity_threshold)

    # 2. BM25关键词检索（基于文本相似度）
    bm25_results = self._bm25_search(query, doc_type, top_k * 2)

    # 3. 合并去重，按分数排序
    merged = merge_results(vector_results, bm25_results, weight_vector=0.6, weight_bm25=0.4)

    return merged[:top_k]
```

**实现方案**:
- 使用 `rank_bm25` 库计算 BM25 分数
- ChromaDB 原生支持，不引入新依赖
- 权重可配置

---

## 2. Web 搜索集成

### 2.1 架构设计

```python
class WebSearchService:
    """网页搜索服务 - 使用 Playwright"""

    def __init__(self):
        self.browser_available = self._check_browser()

    async def search_regulations(
        self,
        chapter_name: str,
        product_type: str,
        product_params: str = ""
    ) -> str:
        """
        搜索相关法规标准信息

        Returns:
            格式化的参考信息字符串
        """
        # 1. 构建搜索查询
        queries = self._build_search_queries(chapter_name, product_type)

        # 2. 逐查询搜索（限2个）
        results = []
        for query in queries[:2]:
            result = await self._search_and_extract(query)
            if result:
                results.append(result)

        # 3. 格式化返回
        return self._format_results(results)
```

### 2.2 搜索查询构建

```python
def _build_search_queries(self, chapter_name: str, product_type: str) -> list[str]:
    """根据章节名构建搜索查询"""
    query_templates = {
        "概述": [f"{product_type} 医疗器械 法规要求", "ISO 14971 医疗器械风险管理"],
        "风险分析": [f"{product_type} 危害分析 风险评估", "ISO 14971 危害判定"],
        "风险评估": ["医疗器械 严重度 频度数 评价准则", "GB 42062 风险评估"],
        "风险控制": ["医疗器械 风险控制措施 ALARP", "ISO 14971 风险控制"],
        # ... 其他章节
    }
    return query_templates.get(chapter_name, [f"{product_type} 医疗器械 法规"])
```

### 2.3 Playwright 搜索流程

```
1. navigate("https://www.google.com")
2. fill search box with query
3. press Enter
4. wait for results
5. extract titles + snippets from first 3 results
6. optionally click into relevant result pages for more detail
```

**注意**:
- Google 可能有人机验证，建议使用 Bing 或 DuckDuckGo
- 需要处理超时、反爬限制
- 结果仅提取摘要，不深入抓取整个页面

---

## 3. 内容生成流程优化

### 3.1 增强后的生成流程

```python
async def _generate_chapter_enhanced(
    self,
    chapter: dict,
    doc_type: str,
    product_name: str,
    product_type: str,
    product_params: str
) -> str:
    """增强版章节生成"""

    # Step 1: RAG 检索
    vector_store = _vector_store()
    rag_chunks = vector_store.retrieve_hybrid(
        query=f"{chapter['query']} {product_name} {product_type}",
        doc_type=doc_type,
        top_k=5
    )

    # Step 2: Web 搜索（异步）
    web_info = ""
    if self.web_search_available:
        web_search = WebSearchService()
        web_info = await web_search.search_regulations(
            chapter_name=chapter["name"],
            product_type=product_type,
            product_params=product_params
        )

    # Step 3: Prompt 组装
    prompt = self._build_enhanced_prompt(
        chapter=chapter,
        doc_type=doc_type,
        product_name=product_name,
        product_type=product_type,
        product_params=product_params,
        rag_chunks=rag_chunks,
        web_info=web_info
    )

    # Step 4: 调用 AI
    return self._call_api(prompt)
```

### 3.2 增强 Prompt 结构

```python
def _build_enhanced_prompt(
    self,
    chapter: dict,
    ...
    rag_chunks: list,
    web_info: str
) -> str:
    """组装带 RAG + Web 上下文的 Prompt"""

    sections = []

    # 1. RAG 参考上下文
    if rag_chunks:
        sections.append("【参考范文 - 来自贵司文档库】")
        for i, chunk in enumerate(rag_chunks, 1):
            sections.append(f"[{i}] {chunk['source_file']} - {chunk['section_title']}")
            sections.append(chunk['text'])
        sections.append("---")

    # 2. Web 搜索上下文
    if web_info:
        sections.append("【相关法规标准 - 来自网络搜索】")
        sections.append(web_info)
        sections.append("---")

    # 3. 产品信息和生成要求
    sections.append(f"【产品信息】...")
    sections.append(f"【生成要求】请生成第X章 {chapter['name']}... ")

    return "\n\n".join(sections)
```

---

## 4. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/services/rag/vector_store.py` | 修改 | 新增 `retrieve_hybrid()` 混合检索方法 |
| `app/services/rag/ingest.py` | 修改 | `CHUNK_SIZE=500` → `CHUNK_SIZE=1000` |
| `app/services/rag/rag_prompt.py` | 修改 | 新增 `build_rag_prompt_with_web()` |
| `app/services/web_search.py` | **新增** | Playwright 网页搜索服务 |
| `app/services/minimax.py` | 修改 | 集成 Web 搜索、启用 RAG by default |
| `app/api/routes.py` | 修改 | 启用 RAG 模式 |

---

## 5. 依赖变更

```txt
# 新增依赖
playwright>=1.40.0
rank_bm25>=0.2.2

# 已有依赖
chromadb>=0.4.22
sentence-transformers>=3.0.0
```

---

## 6. 实现步骤

### Phase 1: RAG 基础优化 (独立)
1. 修改 `ingest.py`: `CHUNK_SIZE=1000`
2. 修改 `vector_store.py`: 新增 `retrieve_hybrid()`
3. 修改 `minimax.py`: 默认启用 RAG，调整 `top_k=5`

### Phase 2: Web 搜索集成 (独立)
4. 新增 `web_search.py`: Playwright 搜索服务
5. 修改 `rag_prompt.py`: 新增 Web 上下文注入方法
6. 修改 `minimax.py`: 集成 Web 搜索到章节生成流程

### Phase 3: 测试验证
7. 重新 ingest 文档库
8. 端到端测试各文档类型生成

---

## 7. 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Playwright 搜索被反爬 | 功能失效 | 使用 DuckDuckGo，添加延时，失败时静默跳过 |
| Web 搜索结果质量不稳定 | 生成内容不一致 | 仅作参考，不强制使用 |
| Chunk 增大后向量库膨胀 | 检索变慢 | ChromaDB 可扩展，影响有限 |
| 多路召回增加复杂度 | 调试困难 | 保留原 `retrieve()` 方法作为 fallback |

---

## 8. 非本次范围 (NOT in scope)

- PDF 解析支持（需要 `pdfplumber` 或 `PyMuPDF`，增加依赖复杂度）
- 重排序 (Rerank) 模型（需要额外部署 Cross-Encoder 模型）
- 查询扩展 (Query Expansion) 使用 LLM 生成多查询（增加 API 调用成本）
- 持久化 Web 搜索结果到向量库（需要增量更新逻辑）

---

## 9. 现有代码利用

| 组件 | 是否复用 | 说明 |
|------|----------|------|
| `VectorStore` | 是 | 扩展 `retrieve_hybrid()` 而非重写 |
| `Embedder` | 是 | 继续用于向量生成 |
| `DOC_CHAPTERS` | 是 | 查询模板复用 |
| `_call_api()` | 是 | AI 调用不变 |
| `DocumentGenerator` | 是 | 流程编排不变 |
