"""
Document Generator - 文档生成协调服务
"""

import asyncio
from app.services.minimax import MiniMaxService
from app.services.template import TemplateService

from app.services.attachment_service import resolve_attachment_content, resolve_attachment_texts
from typing import Optional, List


class DocumentGenerator:
    """文档生成器 - 协调整个生成流程"""

    def __init__(self, progress_callback=None):
        self.minimax_service = MiniMaxService()
        self.minimax_service.progress_callback = progress_callback  # 传递进度回调
        self.template_service = TemplateService()
        self.last_generated_content = ""  # 最近一次生成的 Markdown 内容
        self.last_diff_data = None  # 最近一次修订的差异数据

    async def generate(
        self,
        doc_type: str,
        product_name: str,
        product_type: str,
        product_params: str = "",
        file_ids: Optional[List[str]] = None,
        attachment_content: Optional[str] = None
    ) -> bytes:
        """
        生成文档

        完整流程：
        1. 验证输入参数
        2. 解析附件内容（file_ids → 文本）
        3. 调用AI生成内容
        4. 加载模板
        5. 填充内容
        6. 返回Word文件字节

        Args:
            doc_type: 文档类型
            product_name: 产品名称
            product_type: 产品类型
            product_params: 产品参数
            file_ids: 已入库附件的file_id列表
            attachment_content: 临时附件的提取文本

        Returns:
            Word文件字节数据
        """
        # 1. 验证参数
        self._validate_input(doc_type, product_name, product_type)

        # 2. 解析附件内容
        combined_attachment, attachment_texts = self._resolve_attachments(file_ids, attachment_content)

        # 3. 在线程池中执行耗时同步操作，避免阻塞事件循环
        content = await asyncio.to_thread(
            self.minimax_service.generate_content_with_fallback,
            doc_type=doc_type,
            product_name=product_name,
            product_type=product_type,
            product_params=product_params,
            attachment_content=combined_attachment,
            attachment_texts=attachment_texts
        )

        # 保存原始Markdown内容，供后续修订使用
        self.last_generated_content = content

        # 4. 加载模板
        doc = self.template_service.load_template(doc_type)

        # 5. 填充模板
        doc = self.template_service.fill_template(
            doc=doc,
            content=content,
            product_name=product_name,
            doc_type=doc_type
        )

        # 6. 转换为字节
        return self.template_service.document_to_bytes(doc)

    def _resolve_attachments(
        self,
        file_ids: Optional[List[str]],
        attachment_content: Optional[str]
    ) -> tuple:
        """
        解析附件内容，返回 (merged_str, attachment_texts)。

        - merged_str: 所有附件合并后的单一字符串（向后兼容旧路径）
        - attachment_texts: 各附件独立文本列表（用于配额分配/逐附件检索）
        """
        attachment_texts = []
        parts = []

        # 从向量库解析 file_ids（保持各附件独立）
        if file_ids:
            individual_texts = resolve_attachment_texts(file_ids)
            attachment_texts.extend(individual_texts)
            merged = "\n\n".join(individual_texts)
            if merged:
                parts.append(merged)

        # 直接传入的文本内容（作为整体加入）
        if attachment_content:
            attachment_texts.append(attachment_content)
            parts.append(attachment_content)

        merged_str = "\n\n".join(parts) if parts else ""
        return merged_str, attachment_texts

    @property
    def search_log(self) -> list:
        """返回最近一次生成的搜索方式日志"""
        return getattr(self.minimax_service, "search_log", [])

    @property
    def timing_log(self) -> dict:
        """返回最近一次生成的计时日志（章节级 + 总耗时）"""
        return getattr(self.minimax_service, "timing_log", {})

    async def revise(
        self,
        current_content: str,
        feedback: str,
        doc_type: str,
        product_name: str,
        product_type: str,
        product_params: str = ""
    ) -> str:
        """
        基于用户反馈修订文档

        Args:
            current_content: 当前文档的 Markdown 内容
            feedback: 用户修改意见
            doc_type: 文档类型
            product_name: 产品名称
            product_type: 产品类型
            product_params: 产品参数

        Returns:
            修订后的 Word 文件字节数据
        """
        # 调用 AI 修订内容
        revised_content, diff_data = await asyncio.to_thread(
            self.minimax_service.revise_content,
            current_content=current_content,
            feedback=feedback,
            doc_type=doc_type,
            product_name=product_name,
            product_type=product_type,
            product_params=product_params
        )

        # 保存修订后的内容
        self.last_generated_content = revised_content
        self.last_diff_data = diff_data

        # 生成 Word 文档
        doc = self.template_service.load_template(doc_type)
        doc = self.template_service.fill_template(
            doc=doc,
            content=revised_content,
            product_name=product_name,
            doc_type=doc_type
        )
        return self.template_service.document_to_bytes(doc)

    def _validate_input(
        self,
        doc_type: str,
        product_name: str,
        product_type: str
    ):
        """验证输入参数"""
        if not product_name or not product_name.strip():
            raise ValueError("产品名称不能为空")
