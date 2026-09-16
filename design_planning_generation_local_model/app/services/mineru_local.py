"""
MinerU 本地模型解析服务

使用本地部署的 MinerU2.5-Pro-2605-1.2B 视觉语言模型解析文档，
替代云端 API 调用。模型基于 Qwen2VL 架构，通过 mineru_vl_utils 的
MinerUClient 调用，输出 Markdown。

工作流程：
1. 将输入文件（PDF/DOCX/PPTX/XLSX/图片）转换为每页一张图片
   - PDF → PyMuPDF (fitz) 渲染
   - DOCX/DOC/PPT/PPTX/XLS/XLSX → win32com 转 PDF → PyMuPDF 渲染
   - 图片（PNG/JPG等）→ 直接使用
2. 加载本地 Qwen2VL 模型 + AutoProcessor
3. 对每页图片调用 MinerUClient.two_step_extract() 获取结构化内容
4. 用 json2md 合并为完整 Markdown

注意：模型加载在子进程中执行（由 mineru_runner.py 调用），
避免主服务进程 GPU 显存占用和 C 扩展冲突。
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

# 默认配置
DEFAULT_MODEL_PATH = r"E:\model\MinerU2.5-Pro-2605-1.2B"
DEFAULT_DPI = 200          # PDF 渲染分辨率
DEFAULT_MAX_PAGES = 50     # 单文件最大页数（防止超大文档卡死）

# 支持的图片扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


# ── 文件 → 图片转换 ──

def convert_pdf_to_images(
    pdf_path: str,
    dpi: int = DEFAULT_DPI,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> List:
    """使用 PyMuPDF 将 PDF 每页渲染为 PIL Image"""
    import fitz
    from PIL import Image
    import io

    images = []
    doc = fitz.open(pdf_path)
    try:
        pages_to_process = min(doc.page_count, max_pages)
        for page_num in range(pages_to_process):
            try:
                page = doc[page_num]
                pix = page.get_pixmap(dpi=dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                # 转为 RGB（模型要求）
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images.append(img)
            except Exception as e:
                print(f"[MinerU-Local] PDF 第{page_num+1}页渲染失败: {e}", file=sys.stderr)
    finally:
        doc.close()

    return images


def _convert_office_to_pdf(
    file_path: str,
    app_name: str,
    open_method: str,
    file_format: int,
) -> Optional[str]:
    """通用 Office 文档转 PDF（通过 win32com）

    Args:
        file_path: 源文件路径
        app_name: COM 应用名（Word.Application / PowerPoint.Application / Excel.Application）
        open_method: 打开方式（Documents.Open / Presentations.Open / Workbooks.Open）
        file_format: SaveAs 的 FileFormat 参数
    """
    import win32com.client

    # 输出 PDF 到临时文件
    temp_dir = tempfile.mkdtemp(prefix="mineru_office_")
    pdf_path = os.path.join(temp_dir, Path(file_path).stem + ".pdf")

    app = None
    doc = None
    try:
        app = win32com.client.Dispatch(app_name)
        # Word/Excel 需要 Visible=False，PowerPoint 需要 WithWindow=False
        if app_name == "Word.Application":
            app.Visible = False
            app.DisplayAlerts = False
            doc = app.Documents.Open(file_path)
            doc.SaveAs(pdf_path, FileFormat=file_format)
        elif app_name == "Excel.Application":
            app.Visible = False
            app.DisplayAlerts = False
            doc = app.Workbooks.Open(file_path)
            doc.ExportAsFixedFormat(file_format, pdf_path)
        elif app_name == "PowerPoint.Application":
            doc = app.Presentations.Open(file_path, WithWindow=False)
            doc.SaveAs(pdf_path, file_format)
    except Exception as e:
        print(f"[MinerU-Local] Office 转 PDF 失败 ({app_name}): {e}", file=sys.stderr)
        return None
    finally:
        try:
            if doc is not None:
                doc.Close()
        except Exception:
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass

    if os.path.isfile(pdf_path):
        return pdf_path
    return None


def convert_docx_to_pdf(docx_path: str) -> Optional[str]:
    """DOCX/DOC → PDF（win32com Word）"""
    return _convert_office_to_pdf(
        docx_path, "Word.Application", "Documents.Open", 17  # wdFormatPDF=17
    )


def convert_pptx_to_pdf(pptx_path: str) -> Optional[str]:
    """PPTX/PPT → PDF（win32com PowerPoint）"""
    return _convert_office_to_pdf(
        pptx_path, "PowerPoint.Application", "Presentations.Open", 32  # ppSaveAsPDF=32
    )


def convert_xlsx_to_pdf(xlsx_path: str) -> Optional[str]:
    """XLSX/XLS → PDF（win32com Excel）"""
    return _convert_office_to_pdf(
        xlsx_path, "Excel.Application", "Workbooks.Open", 0  # xlTypePDF=0
    )


def convert_file_to_images(
    file_path: str,
    dpi: int = DEFAULT_DPI,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> List:
    """根据文件类型转换为图片列表

    Returns:
        List[PIL.Image]：每页一张图片；失败返回空列表
    """
    from PIL import Image

    ext = Path(file_path).suffix.lower()

    # 直接是图片
    if ext in IMAGE_EXTENSIONS:
        try:
            img = Image.open(file_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            return [img]
        except Exception as e:
            print(f"[MinerU-Local] 图片打开失败: {e}", file=sys.stderr)
            return []

    # PDF 直接转图片
    if ext == ".pdf":
        return convert_pdf_to_images(file_path, dpi=dpi, max_pages=max_pages)

    # Office 文档先转 PDF 再转图片
    temp_pdf = None
    if ext in (".docx", ".doc"):
        temp_pdf = convert_docx_to_pdf(file_path)
    elif ext in (".pptx", ".ppt"):
        temp_pdf = convert_pptx_to_pdf(file_path)
    elif ext in (".xlsx", ".xls"):
        temp_pdf = convert_xlsx_to_pdf(file_path)

    if temp_pdf is None:
        print(f"[MinerU-Local] 不支持的格式或转换失败: {ext}", file=sys.stderr)
        return []

    try:
        return convert_pdf_to_images(temp_pdf, dpi=dpi, max_pages=max_pages)
    finally:
        # 清理临时 PDF 及其目录
        try:
            temp_dir = os.path.dirname(temp_pdf)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


# ── 本地模型提取器 ──

class MinerULocalExtractor:
    """本地 MinerU 模型提取器（单例，延迟加载）"""

    _instance = None

    def __init__(self, model_path: str = None):
        self.model_path = model_path or os.environ.get(
            "MINERU_LOCAL_MODEL_PATH", DEFAULT_MODEL_PATH
        )
        self._model = None
        self._processor = None
        self._client = None

    @classmethod
    def get_instance(cls, model_path: str = None) -> "MinerULocalExtractor":
        if cls._instance is None:
            cls._instance = cls(model_path)
        return cls._instance

    def _load_model(self):
        """加载模型、processor 和 MinerUClient"""
        if self._client is not None:
            return

        if not os.path.isdir(self.model_path):
            raise FileNotFoundError(f"模型目录不存在: {self.model_path}")

        print(f"[MinerU-Local] 加载模型: {self.model_path}", file=sys.stderr)

        # transformers>=4.56.0 支持的 Qwen2VL 加载方式
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        self._model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.model_path,
            dtype="auto",
            device_map="auto",
        )
        self._processor = AutoProcessor.from_pretrained(
            self.model_path,
            use_fast=True,
        )

        from mineru_vl_utils import MinerUClient

        self._client = MinerUClient(
            backend="transformers",
            model=self._model,
            processor=self._processor,
            image_analysis=False,  # 设 True 可启用图片/图表分析（更慢）
        )
        print(f"[MinerU-Local] 模型加载完成", file=sys.stderr)

    def extract(self, file_path: str) -> str:
        """解析文档返回 Markdown

        Args:
            file_path: 文件路径

        Returns:
            Markdown 字符串；失败抛异常
        """
        self._load_model()

        filename = os.path.basename(file_path)
        print(f"[MinerU-Local] 开始解析: {filename}", file=sys.stderr)

        # 转图片
        images = convert_file_to_images(file_path)
        if not images:
            raise ValueError(f"无法将文件转换为图片: {filename}")

        print(f"[MinerU-Local] 共 {len(images)} 页", file=sys.stderr)

        from mineru_vl_utils.post_process import json2md

        # 逐页解析并合并
        all_markdown_parts = []
        for i, img in enumerate(images):
            try:
                t0 = time.time()
                content_list = self._client.two_step_extract(img)
                md_part = json2md(content_list)
                all_markdown_parts.append(md_part)
                elapsed = time.time() - t0
                print(
                    f"[MinerU-Local] 第 {i+1}/{len(images)} 页完成 "
                    f"({len(md_part)} 字符, {elapsed:.1f}s)",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"[MinerU-Local] 第 {i+1} 页解析失败: {e}",
                    file=sys.stderr,
                )
                # 跳过失败页，继续处理后续页
                continue

        if not all_markdown_parts:
            raise ValueError(f"所有页面解析均失败: {filename}")

        full_markdown = "\n\n---\n\n".join(all_markdown_parts)
        print(
            f"[MinerU-Local] 解析完成: {filename} → {len(full_markdown)} 字符",
            file=sys.stderr,
        )
        return full_markdown


def extract_text_with_local_mineru(file_path: str, model_path: str = None) -> str:
    """便捷函数：使用本地模型解析文档，返回 Markdown

    Args:
        file_path: 文件路径
        model_path: 模型路径（None 则用默认/环境变量）

    Returns:
        Markdown 字符串
    """
    extractor = MinerULocalExtractor.get_instance(model_path)
    return extractor.extract(file_path)
