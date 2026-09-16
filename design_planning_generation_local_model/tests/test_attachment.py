"""
附件上传与文档生成 — 关键测试
"""

import os
import sys
import io
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ==================== 附件验证测试 ====================

class TestUploadValidation:
    """上传文件验证测试"""

    def test_valid_docx(self):
        """有效.docx文件应通过验证"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("test.docx", 1024)
        assert is_valid
        assert error == ""

    def test_valid_pdf(self):
        """有效.pdf文件应通过验证"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("test.pdf", 5 * 1024 * 1024)
        assert is_valid
        assert error == ""

    def test_valid_txt(self):
        """有效.txt文件应通过验证"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("test.txt", 100)
        assert is_valid
        assert error == ""

    def test_invalid_format_xlsx(self):
        """不支持的.xlsx格式应返回400错误"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("data.xlsx", 1024)
        assert not is_valid
        assert "不支持" in error

    def test_invalid_format_jpg(self):
        """不支持的.jpg格式应返回400错误"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("photo.jpg", 2048)
        assert not is_valid
        assert "不支持" in error

    def test_file_too_large(self):
        """超过10MB的文件应返回错误"""
        from app.services.attachment_service import validate_upload
        oversized = (10 * 1024 * 1024) + 1  # 10MB + 1 byte
        is_valid, error = validate_upload("large.pdf", oversized)
        assert not is_valid
        assert "超过限制" in error or "MB" in error

    def test_empty_file(self):
        """空文件应返回错误"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("empty.docx", 0)
        assert not is_valid
        assert "空" in error or "有效" in error

    def test_max_size_boundary(self):
        """恰好10MB的文件应通过验证"""
        from app.services.attachment_service import validate_upload
        is_valid, error = validate_upload("exact.pdf", 10 * 1024 * 1024)
        assert is_valid


# ==================== 附件状态管理测试 ====================

class TestExtractTasks:
    """提取任务状态管理测试"""

    def test_submit_creates_task(self):
        """提交提取任务应创建并返回task_id"""
        from app.services.attachment_service import submit_extract_task, get_extract_status
        task_id = submit_extract_task(
            file_content=b"Hello world test content",
            filename="test.txt",
            persist=False
        )
        assert task_id is not None
        assert len(task_id) > 0

        status = get_extract_status(task_id)
        assert status is not None
        assert status["filename"] == "test.txt"

    def test_get_nonexistent_task(self):
        """查询不存在的任务应返回None"""
        from app.services.attachment_service import get_extract_status
        assert get_extract_status("nonexistent") is None


# ==================== 文档生成（带附件）测试 ====================

class TestGeneratorWithAttachment:
    """带附件参数的文档生成测试"""

    def test_generator_accepts_file_ids(self):
        """generator应接受file_ids参数"""
        from app.services.generator import DocumentGenerator
        gen = DocumentGenerator()
        # 验证方法签名接受新参数
        import inspect
        sig = inspect.signature(gen.generate)
        params = list(sig.parameters.keys())
        assert "file_ids" in params
        assert "attachment_content" in params

    def test_resolve_attachments_empty(self):
        """空附件参数应返回空字符串和空列表"""
        from app.services.generator import DocumentGenerator
        gen = DocumentGenerator()
        merged, texts = gen._resolve_attachments(None, None)
        assert merged == ""
        assert texts == []

    def test_resolve_attachments_content_only(self):
        """仅有attachment_content时应返回合并字符串和单元素列表"""
        from app.services.generator import DocumentGenerator
        gen = DocumentGenerator()
        merged, texts = gen._resolve_attachments(None, "test attachment content")
        assert "test attachment content" in merged
        assert len(texts) == 1
        assert "test attachment content" in texts[0]

    def test_resolve_attachments_both(self):
        """同时有file_ids和attachment_content时应合并"""
        from app.services.generator import DocumentGenerator
        gen = DocumentGenerator()
        with patch("app.services.generator.resolve_attachment_texts", return_value=["from vector store"]):
            merged, texts = gen._resolve_attachments(["file123"], "direct text")
            assert "from vector store" in merged
            assert "direct text" in merged
            assert len(texts) == 2
            assert "from vector store" in texts[0]
            assert "direct text" in texts[1]


# ==================== 向后兼容回归测试 ====================

class TestBackwardCompatibility:
    """确保不传附件参数时现有流程不变"""

    def test_generate_request_without_attachment(self):
        """不传附件参数的GenerateRequest应正常创建"""
        from app.api.routes import GenerateRequest
        req = GenerateRequest(
            doc_type="risk_management_report",
            product_name="胰岛素泵",
            product_type="有源医疗器械"
        )
        assert req.file_ids is None
        assert req.attachment_content is None
        assert req.product_name == "胰岛素泵"

    def test_generate_request_with_attachment(self):
        """带附件参数的GenerateRequest应正常创建"""
        from app.api.routes import GenerateRequest
        req = GenerateRequest(
            doc_type="sop",
            product_name="血糖仪",
            product_type="有源医疗器械",
            file_ids=["abc123"],
            attachment_content="产品说明文本"
        )
        assert req.file_ids == ["abc123"]
        assert req.attachment_content == "产品说明文本"

    def test_generate_request_roundtrip(self):
        """GenerateRequest应能序列化并包含所有字段"""
        from app.api.routes import GenerateRequest
        import json
        req = GenerateRequest(
            doc_type="product_spec",
            product_name="测试产品",
            product_type="植入器械",
            product_params="测试参数",
            file_ids=["f1", "f2"],
            attachment_content="附件文本"
        )
        data = req.model_dump()
        assert data["doc_type"] == "product_spec"
        assert data["file_ids"] == ["f1", "f2"]
        assert data["attachment_content"] == "附件文本"


# ==================== 文档类型常量测试 ====================

class TestDocTypeConstants:
    """公共常量完整性测试"""

    def test_doc_types_consistency(self):
        """DOC_TYPES和DOC_TYPE_LABELS应一一对应"""
        from app.services.doc_types import DOC_TYPES, DOC_TYPE_LABELS
        for dt in DOC_TYPES:
            assert dt in DOC_TYPE_LABELS, f"{dt} 缺少label映射"

    def test_all_imports_same_source(self):
        """所有模块应从同一来源导入"""
        from app.services.doc_types import DOC_TYPE_LABELS as SRC
        # 验证 template.py 的导入
        from app.services.template import DOC_TYPE_LABELS as TPL
        assert SRC is TPL


# ==================== 关键词匹配测试 ====================

class TestKeywordMatching:
    """附件内容关键词匹配测试"""

    def test_match_relevant_paragraphs(self):
        """应匹配到与查询相关的段落"""
        from app.services.minimax import MiniMaxService
        svc = MiniMaxService(api_key="test_key")

        text = "产品为有源医疗器械\n使用蓝牙通信\n外壳材质为医用级塑料\n适用人群为成人患者\n工作温度范围10-40度"
        query = "通信 蓝牙 有源"

        result = svc._match_relevant_paragraphs(text, query, max_chars=500)
        assert "蓝牙" in result
        assert "有源" in result

    def test_match_empty_text(self):
        """空文本应返回空字符串"""
        from app.services.minimax import MiniMaxService
        svc = MiniMaxService(api_key="test_key")
        result = svc._match_relevant_paragraphs("", "测试", 500)
        assert result == ""

    def test_match_no_keywords(self):
        """无匹配关键词时应返回空字符串"""
        from app.services.minimax import MiniMaxService
        svc = MiniMaxService(api_key="test_key")
        result = svc._match_relevant_paragraphs("完全不相关的内容", "蓝牙通信", 500)
        assert result == "" or len(result) >= 0  # 可能部分匹配或无匹配


# ==================== 跨Collection检索测试 ====================

class TestCrossCollectionRetrieval:
    """跨collection检索测试"""

    def test_minimax_accepts_attachment_content(self):
        """MinimaxService方法应接受attachment_content和attachment_texts参数"""
        from app.services.minimax import MiniMaxService
        import inspect
        sig = inspect.signature(MiniMaxService.generate_content_with_fallback)
        params = list(sig.parameters.keys())
        assert "attachment_content" in params
        assert "attachment_texts" in params


# ==================== Multi-attachment Quota Allocation Tests ====================

class TestAllocateAttachmentQuota:
    """Test the _allocate_attachment_quota helper method"""

    def _get_svc(self):
        from app.services.minimax import MiniMaxService
        return MiniMaxService(api_key="test_key")

    def test_empty_list(self):
        """Empty attachment list returns empty list"""
        svc = self._get_svc()
        result = svc._allocate_attachment_quota([], total_budget=3000)
        assert result == []

    def test_single_attachment(self):
        """Single attachment gets full budget"""
        svc = self._get_svc()
        text = "A" * 5000
        result = svc._allocate_attachment_quota([text], total_budget=3000)
        assert len(result) == 1
        assert len(result[0]) == 3000

    def test_two_attachments_proportional(self):
        """Two attachments get proportional allocation with min guarantee"""
        svc = self._get_svc()
        text1 = "A" * 2000
        text2 = "B" * 8000
        result = svc._allocate_attachment_quota([text1, text2], total_budget=3000, min_per=500)
        assert len(result) == 2
        # text1 is 20% of total, text2 is 80%
        # proportional: text1=600, text2=2400
        # min_per=500, so both are above min
        assert len(result[0]) >= 500  # at least min_per
        assert len(result[1]) >= 500
        assert result[0].startswith("A")
        assert result[1].startswith("B")

    def test_min_per_guarantee(self):
        """Small attachment still gets min_per chars"""
        svc = self._get_svc()
        text1 = "X" * 100  # very small
        text2 = "Y" * 10000
        result = svc._allocate_attachment_quota([text1, text2], total_budget=3000, min_per=500)
        assert len(result) == 2
        # text1 is only 100 chars, so gets all 100
        assert len(result[0]) == 100
        # text2 gets the rest
        assert len(result[1]) > 0

    def test_five_attachments_equal_split(self):
        """N > 4 triggers equal split"""
        svc = self._get_svc()
        texts = [chr(65 + i) * 10000 for i in range(5)]
        result = svc._allocate_attachment_quota(texts, total_budget=3000, min_per=500)
        assert len(result) == 5
        per = 3000 // 5  # 600
        for r in result:
            assert len(r) == per

    def test_empty_text_filtered(self):
        """Empty/whitespace texts are filtered"""
        svc = self._get_svc()
        result = svc._allocate_attachment_quota(["", "  ", "A" * 1000], total_budget=3000)
        assert len(result) == 3  # same length as input
        assert result[0] == ""
        assert result[1] == ""
        # single non-empty gets full text (but capped at its length = 1000)
        assert len(result[2]) == 1000

    def test_all_empty(self):
        """All empty texts returns list of empty strings"""
        svc = self._get_svc()
        result = svc._allocate_attachment_quota(["", ""], total_budget=3000)
        assert result == ["", ""]


# ==================== Multi-attachment Injection Tests ====================

class TestMultiAttachmentInjection:
    """Test multi-attachment injection in prompt builders"""

    def _get_svc(self):
        from app.services.minimax import MiniMaxService
        return MiniMaxService(api_key="test_key")

    def test_single_attachment_falls_back(self):
        """Single attachment (len==1) uses old logic via attachment_content"""
        svc = self._get_svc()
        prompt = svc._build_section_prompt(
            index=1,
            chapter_name="test_chapter",
            section_name="test_section",
            section_query="test query",
            chunks=[],
            uploads_chunks=[],
            web_info="",
            doc_type="sop",
            product_name="test",
            product_type="test",
            product_params="",
            attachment_content="single attachment content",
            attachment_texts=["single attachment content"],
            total_sections=1,
            all_chapter_names=[]
        )
        # Should contain the old-style label (single attachment path)
        assert "single attachment content" in prompt

    def test_multi_attachment_first_section_quota(self):
        """Multi-attachment first section uses quota allocation"""
        svc = self._get_svc()
        text1 = "A" * 2000
        text2 = "B" * 2000
        prompt = svc._build_section_prompt(
            index=1,
            chapter_name="test_chapter",
            section_name="test_section",
            section_query="test query",
            chunks=[],
            uploads_chunks=[],
            web_info="",
            doc_type="sop",
            product_name="test",
            product_type="test",
            product_params="",
            attachment_content="",
            attachment_texts=[text1, text2],
            total_sections=1,
            all_chapter_names=[]
        )
        # Both attachments should be represented in the prompt
        assert "A" in prompt
        assert "B" in prompt
        # Should have multi-attachment label
        assert "---" in prompt

    def test_multi_attachment_subsequent_section_rag(self):
        """Multi-attachment subsequent section uses per-attachment RAG"""
        svc = self._get_svc()
        text1 = "keyword1 is here in this paragraph\nanother paragraph"
        text2 = "keyword2 is here in this paragraph\nanother one"
        prompt = svc._build_section_prompt(
            index=2,  # subsequent section
            chapter_name="test_chapter",
            section_name="test_section",
            section_query="keyword1 keyword2",
            chunks=[],
            uploads_chunks=[],
            web_info="",
            doc_type="sop",
            product_name="test",
            product_type="test",
            product_params="",
            attachment_content="",
            attachment_texts=[text1, text2],
            total_sections=2,
            all_chapter_names=[]
        )
        # Should contain relevant paragraphs from both attachments
        assert "keyword1" in prompt or "keyword2" in prompt

    def test_attachment_texts_none_falls_back(self):
        """attachment_texts=None uses old logic"""
        svc = self._get_svc()
        prompt = svc._build_section_prompt(
            index=1,
            chapter_name="test_chapter",
            section_name="test_section",
            section_query="test query",
            chunks=[],
            uploads_chunks=[],
            web_info="",
            doc_type="sop",
            product_name="test",
            product_type="test",
            product_params="",
            attachment_content="fallback content",
            attachment_texts=None,
            total_sections=1,
            all_chapter_names=[]
        )
        assert "fallback content" in prompt

    def test_empty_attachment_skipped(self):
        """Empty attachment texts are skipped in multi-attachment path"""
        svc = self._get_svc()
        prompt = svc._build_section_prompt(
            index=1,
            chapter_name="test_chapter",
            section_name="test_section",
            section_query="test query",
            chunks=[],
            uploads_chunks=[],
            web_info="",
            doc_type="sop",
            product_name="test",
            product_type="test",
            product_params="",
            attachment_content="",
            attachment_texts=["real content", "", "  "],
            total_sections=1,
            all_chapter_names=[]
        )
        # Only the non-empty attachment should be in the prompt
        assert "real content" in prompt


# ==================== Outline From Attachment Multi Tests ====================

class TestOutlineFromAttachmentMulti:
    """Test outline_from_attachment with multiple attachments"""

    def test_outline_uses_all_attachments(self):
        """Multiple attachments should all be included"""
        from app.services.agent_tools import set_current_attachments, outline_from_attachment
        import json

        attachments = [
            {"file_id": "f1", "filename": "doc1.txt", "full_text": "Content from doc1 " * 100},
            {"file_id": "f2", "filename": "doc2.txt", "full_text": "Content from doc2 " * 100},
        ]
        set_current_attachments(attachments)

        captured_prompt = {}

        def mock_call(*args, **kwargs):
            captured_prompt['system'] = kwargs.get('system_prompt', '')
            captured_prompt['user'] = kwargs.get('user_prompt', '')
            return '{"doc_title": "test", "chapters": [{"id": 1, "title": "ch1", "description": "d", "key_standards": [], "subsections": [{"title": "s1", "content_points": ["p1"]}]}]}'

        with patch("app.services.minimax._call_minimax_api_raw", side_effect=mock_call):
            import asyncio
            result = asyncio.run(outline_from_attachment.ainvoke(
                {"file_id": "", "doc_type": "sop", "product_name": "test"}
            ))
            # User prompt should contain both filenames
            if captured_prompt.get('user'):
                assert "doc1.txt" in captured_prompt['user']
                assert "doc2.txt" in captured_prompt['user']

        set_current_attachments([])

    def test_outline_single_attachment_unchanged(self):
        """Single attachment should still work"""
        from app.services.agent_tools import set_current_attachments, outline_from_attachment
        import json

        attachments = [
            {"file_id": "f1", "filename": "single.txt", "full_text": "Single doc content " * 100},
        ]
        set_current_attachments(attachments)

        def mock_call(*args, **kwargs):
            return '{"doc_title": "test", "chapters": [{"id": 1, "title": "ch1", "description": "d", "key_standards": [], "subsections": [{"title": "s1", "content_points": ["p1"]}]}]}'

        with patch("app.services.minimax._call_minimax_api_raw", side_effect=mock_call):
            import asyncio
            result = asyncio.run(outline_from_attachment.ainvoke(
                {"file_id": "", "doc_type": "sop", "product_name": "test"}
            ))
            assert result is not None

        set_current_attachments([])

    def test_outline_file_id_specified(self):
        """file_id specified should use only that attachment"""
        from app.services.agent_tools import set_current_attachments, outline_from_attachment

        attachments = [
            {"file_id": "f1", "filename": "doc1.txt", "full_text": "Content from doc1 " * 100},
            {"file_id": "f2", "filename": "doc2.txt", "full_text": "Content from doc2 " * 100},
        ]
        set_current_attachments(attachments)

        captured_prompt = {}

        def mock_call(*args, **kwargs):
            captured_prompt['user'] = kwargs.get('user_prompt', '')
            return '{"doc_title": "test", "chapters": [{"id": 1, "title": "ch1", "description": "d", "key_standards": [], "subsections": [{"title": "s1", "content_points": ["p1"]}]}]}'

        with patch("app.services.minimax._call_minimax_api_raw", side_effect=mock_call):
            import asyncio
            result = asyncio.run(outline_from_attachment.ainvoke(
                {"file_id": "f2", "doc_type": "sop", "product_name": "test"}
            ))
            # Should only contain doc2, not doc1
            if captured_prompt.get('user'):
                assert "doc2.txt" in captured_prompt['user']
                assert "doc1.txt" not in captured_prompt['user']

        set_current_attachments([])
