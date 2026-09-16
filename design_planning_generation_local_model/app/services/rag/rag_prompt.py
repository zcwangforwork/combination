"""
RAG Prompt 构建模块

将检索到的参考段落格式化为生成 Prompt 的上下文。
"""


def build_rag_prompt(
    doc_type: str,
    product_name: str,
    product_type: str,
    product_params: str,
    retrieved_chunks: list[dict]
) -> str:
    """
    构建带 RAG 上下文的生成 Prompt

    Args:
        doc_type: 文档类型
        product_name: 产品名称
        product_type: 产品类型
        product_params: 产品参数
        retrieved_chunks: 向量库检索结果

    Returns:
        格式化后的完整 Prompt 字符串
    """
    if not retrieved_chunks:
        return base_prompt  # 返回原始 prompt 而非 None

    # 按 source_file 分组，构建参考上下文
    # 限制每条检索结果长度，避免 RAG 上下文过长导致 LLM 超时
    MAX_CHUNK_LENGTH = 1500
    MAX_CONTEXT_LENGTH = 15000

    context_blocks = []
    total_length = 0
    for chunk in retrieved_chunks:
        source = chunk.get("source_file", "未知来源")
        section = chunk.get("section_title", "")
        text = chunk.get("text", "").strip()[:MAX_CHUNK_LENGTH]

        if not text:
            continue

        header = f"[来源：{source}"
        if section:
            header += f" | 章节：{section}"
        header += "]"

        block = f"{header}\n{text}"
        if total_length + len(block) > MAX_CONTEXT_LENGTH:
            break
        context_blocks.append(block)
        total_length += len(block)

    if not context_blocks:
        return None

    reference_context = "\n\n".join(context_blocks)

    # 构建完整的 RAG Prompt
    rag_instruction = f"""【参考范文 - 请严格参照此详细程度、格式和专业深度生成文档】

{reference_context}

---

【产品信息】
- 产品名称：{product_name}
- 产品类型：{product_type}
- 产品参数：{product_params if product_params else '无特殊参数'}

【重要 - 详细程度和语言要求】
以上参考范文展示了文档应有的详细程度和格式标准，请务必参照：

0. 【强制语言要求】所有内容必须使用中文，不要使用任何英文单词或短语，除了标准号和必要的缩写（如FMEA、SOP、QA、RPN、ISO、GB等）中必须包含的部分
1. 内容详细程度：每个章节都要有极其详细的实质性内容，不能只写框架标题，要像参考范文一样饱满
2. 技术参数：所有技术参数都要具体、可测量，有明确的数值范围和精度要求
3. 表格完整性：所有表格都要完整填写，每个单元格都要有具体内容，不能留"（描述）"或"待填写"等占位符
4. 风险分析覆盖面：风险分析要覆盖所有可能的危害，包括能量危害、生物学危害、环境危害、使用危害等，不能遗漏
5. 标准引用准确性：标准号和条款引用要准确，包括标准号、年代号和具体条款
6. 操作步骤详细度：如果涉及操作步骤，每个步骤都要详细描述，包括使用的设备、工具、操作要点、注意事项
7. 职责分工明确度：职责要明确到具体岗位，资质要求要详细
8. 专业术语使用：要使用专业、规范的医疗器械行业术语
9. 可操作性：生成的文档要像正式发布的文件一样，具有可操作性和可执行性
10. 格式规范性：参照参考范文的格式，包括标题层级、表格样式、段落组织等

请生成与参考范文同等详细程度的文档内容，确保质量达到注册申报或正式使用的水平，并且全部使用中文表达。
"""

    return rag_instruction


def build_rag_prompt_from_base(
    base_prompt: str,
    doc_type: str,
    product_name: str,
    product_type: str,
    product_params: str,
    retrieved_chunks: list[dict]
) -> str:
    """
    在已有 Prompt 模板基础上注入 RAG 上下文

    Args:
        base_prompt: 原始的 PROMPT_TEMPLATE 字符串
        doc_type: 文档类型
        product_name: 产品名称
        product_type: 产品类型
        product_params: 产品参数
        retrieved_chunks: 向量库检索结果

    Returns:
        注入 RAG 上下文后的完整 Prompt
    """
    rag_context = build_rag_prompt(
        doc_type=doc_type,
        product_name=product_name,
        product_type=product_type,
        product_params=product_params,
        retrieved_chunks=retrieved_chunks
    )

    if not rag_context:
        return base_prompt

    # 在 base_prompt 开头插入 RAG 上下文
    return f"{rag_context}\n\n{'='*60}\n\n{base_prompt}"


def format_chunk_for_display(chunk: dict) -> str:
    """
    格式化单个检索结果用于调试/展示

    Args:
        chunk: 检索结果字典

    Returns:
        格式化字符串
    """
    lines = [
        f"来源文件: {chunk.get('source_file', '未知')}",
        f"章节: {chunk.get('section_title', '未知')}",
        f"相似度: {chunk.get('similarity', 0):.3f}",
        f"内容: {chunk.get('text', '')[:200]}..."
    ]
    return " | ".join(lines)
