"""
Attachment Service - 附件上传、文本提取、向量库入库管理
"""
import os
import json
import uuid
import hashlib
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from app.services.doc_types import SUPPORTED_UPLOAD_FORMATS, MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB
from app.services.rag.ingest import extract_text_from_file, chunk_text, ingest_document


# 内存中的附件提取任务状态
extract_tasks: Dict[str, dict] = {}


def _do_extract(task_id: str, file_path: str, persist: bool, doc_type: str):
    """后台线程：执行文本提取和可选入库"""
    try:
        extract_tasks[task_id]["status"] = "extracting"
        extract_tasks[task_id]["message"] = "正在提取文本..."

        paragraphs = extract_text_from_file(file_path)

        # 如果结构化提取为空，尝试直接读取为纯文本（仅限纯文本类格式）
        # 注意：不得对 pdf/docx/doc/xlsx 等二进制格式做 latin1 兜底——
        # latin1 对任意字节序列都不会解码失败，会把二进制读成乱码并当成"成功提取"，
        # 导致上传"看似成功"却产生乱码文本。
        if not paragraphs:
            _ext = os.path.splitext(file_path)[1].lower()
            if _ext in (".txt", ".md"):
                try:
                    # 尝试多种编码直接读取原始文本
                    raw_text = ""
                    for enc in ["utf-8", "gbk", "gb18030", "latin1"]:
                        try:
                            with open(file_path, "r", encoding=enc) as f:
                                raw_text = f.read().strip()
                            if raw_text:
                                break
                        except Exception:
                            continue
                    if raw_text:
                        paragraphs = [("", raw_text)]
                except Exception:
                    pass

        if not paragraphs:
            extract_tasks[task_id]["status"] = "failed"
            extract_tasks[task_id]["message"] = "无法从文件中提取文本内容，文件可能为空、已加密或格式不支持"
            return

        # 合并为完整文本（不做结构处理，直接拼接）
        lines = []
        for section_title, text in paragraphs:
            if section_title:
                lines.append(section_title)
            lines.append(text)
        full_text = "\n\n".join(lines)

        extract_tasks[task_id]["char_count"] = len(full_text)
        extract_tasks[task_id]["preview"] = full_text[:500] + ("..." if len(full_text) > 500 else "")
        extract_tasks[task_id]["full_text"] = full_text
        extract_tasks[task_id]["toc"] = ""

        # 写入磁盘缓存（模板/附件类），TTL 内同文件重复上传不再触发 MinerU 解析
        if not persist:
            _save_extract_cache(
                extract_tasks[task_id].get("file_hash", ""),
                extract_tasks[task_id].get("filename", filename),
                full_text, len(full_text),
                extract_tasks[task_id]["preview"],
                "",
            )

        # 可选：写入向量库
        if persist:
            extract_tasks[task_id]["message"] = "正在写入知识库..."
            try:
                from app.services.rag.vector_store import VectorStore
                vector_store = VectorStore(collection_name="uploads")
                # 传入已解析的 paragraphs，避免 ingest_document 内部重复调用
                # extract_text_from_file（MinerU 等解析器单次调用即数十秒）
                chunk_count = ingest_document(
                    file_path, vector_store,
                    force_doc_type=doc_type,
                    pre_parsed_paragraphs=paragraphs,
                    file_id=task_id,
                    original_filename=extract_tasks[task_id].get("filename", ""),
                )
                extract_tasks[task_id]["persisted"] = True
                extract_tasks[task_id]["chunk_count"] = chunk_count
            except Exception as e:
                extract_tasks[task_id]["persisted"] = False
                extract_tasks[task_id]["persist_error"] = str(e)
        else:
            extract_tasks[task_id]["persisted"] = False

        extract_tasks[task_id]["status"] = "completed"
        extract_tasks[task_id]["message"] = "提取完成"

    except Exception as e:
        extract_tasks[task_id]["status"] = "failed"
        extract_tasks[task_id]["message"] = f"提取失败: {str(e)}"
    finally:
        # 保留原始文件路径：.docx 是段落级手术（修改/精简/补全上传文档）的基底
        extract_tasks[task_id]["original_path"] = file_path
        # 注意: 保留 full_text 不清除 — Agent模式附件功能需要访问全文


# ── 提取结果磁盘缓存（按文件哈希，TTL 内避免重复解析）──
# 缓存目录：app/../data/extract_cache/；键：文件 MD5；值：提取全文等。
# 仅对 persist=False（模板/会话附件）生效——知识库上传（persist=True）需要
# 重新走向量入库流程，不适用文本缓存。

_EXTRACT_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "extract_cache")
_EXTRACT_CACHE_TTL_HOURS = float(os.getenv("EXTRACT_CACHE_TTL_HOURS", "168"))  # 默认7天
_EXTRACT_CACHE_MAX_FILES = int(os.getenv("EXTRACT_CACHE_MAX_FILES", "300"))


def _extract_cache_path(file_hash: str) -> str:
    return os.path.join(_EXTRACT_CACHE_DIR, f"{file_hash}.json")


def _load_extract_cache(file_hash: str) -> Optional[dict]:
    """读取提取缓存；不存在/过期/损坏返回 None。"""
    path = _extract_cache_path(file_hash)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    cached_at = float(data.get("cached_at") or 0)
    if cached_at <= 0 or (time.time() - cached_at) > _EXTRACT_CACHE_TTL_HOURS * 3600:
        return None
    if not (data.get("full_text") or "").strip():
        return None
    return data


def _save_extract_cache(file_hash: str, filename: str, full_text: str,
                        char_count: int, preview: str, toc: str) -> None:
    """写入提取缓存并按 mtime 淘汰超限旧缓存。"""
    try:
        os.makedirs(_EXTRACT_CACHE_DIR, exist_ok=True)
        data = {
            "filename": filename,
            "full_text": full_text,
            "char_count": char_count,
            "preview": preview,
            "toc": toc or "",
            "cached_at": time.time(),
        }
        with open(_extract_cache_path(file_hash), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        # 容量淘汰：超出上限时删除最旧（按文件 mtime）的缓存文件
        files = [
            os.path.join(_EXTRACT_CACHE_DIR, fn)
            for fn in os.listdir(_EXTRACT_CACHE_DIR) if fn.endswith(".json")
        ]
        if len(files) > _EXTRACT_CACHE_MAX_FILES:
            files.sort(key=lambda p: os.path.getmtime(p))
            for old in files[:len(files) - _EXTRACT_CACHE_MAX_FILES]:
                try:
                    os.remove(old)
                except OSError:
                    pass
    except Exception as e:
        print(f"[extract_cache] 写入失败（不影响提取）: {e}")


def validate_upload(filename: str, file_size: int) -> Tuple[bool, str]:
    """
    验证上传文件

    Returns:
        (is_valid, error_message)
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_UPLOAD_FORMATS:
        return False, f"不支持的文件格式 '{ext}'。支持的格式: {', '.join(SUPPORTED_UPLOAD_FORMATS)}"

    if file_size > MAX_UPLOAD_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return False, f"文件大小 ({size_mb:.1f}MB) 超过限制 ({MAX_UPLOAD_SIZE_MB}MB)"

    if file_size == 0:
        return False, "文件为空，请上传有效文件"

    return True, ""


def compute_file_hash(file_path: str) -> str:
    """计算文件 MD5 hash，用于去重"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def submit_extract_task(
    file_content: bytes,
    filename: str,
    persist: bool = False,
    doc_type: str = "unknown"
) -> str:
    """
    提交附件提取任务

    Args:
        file_content: 原始文件字节
        filename: 原始文件名
        persist: 是否写入向量库
        doc_type: 文档类型标签

    Returns:
        task_id
    """
    task_id = str(uuid.uuid4())[:12]

    # 保存到临时文件
    ext = os.path.splitext(filename)[1].lower()
    temp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "downloads")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"upload_{task_id}{ext}")

    with open(temp_path, "wb") as f:
        f.write(file_content)

    # 计算 hash（用于去重）
    file_hash = compute_file_hash(temp_path)

    # 去重检查
    for existing_id, task in extract_tasks.items():
        if task.get("file_hash") == file_hash and task.get("status") == "completed":
            # 已有相同文件，直接返回；
            # 但若本次请求入库(persist=True)而既有任务未入库，则重建任务以确保入库
            if persist and not task.get("persisted"):
                continue
            return existing_id

    # ── 提取结果磁盘缓存（模板/附件类，persist=False）──
    # 服务重启后内存去重失效，同文件重复上传会重新触发 MinerU 解析（分钟级）。
    # 磁盘缓存按文件哈希保存提取结果，TTL 内命中则直接完成，跳过解析。
    if not persist:
        cached = _load_extract_cache(file_hash)
        if cached is not None:
            extract_tasks[task_id] = {
                "file_id": task_id,
                "filename": filename,
                "status": "completed",
                "message": "提取完成（命中缓存，未重新解析）",
                "preview": cached.get("preview", ""),
                "char_count": cached.get("char_count", 0),
                "full_text": cached.get("full_text", ""),
                "toc": cached.get("toc", ""),
                "persisted": False,
                "file_hash": file_hash,
                "created_at": time.time(),
                "from_cache": True,
                # 保留原始文件路径：.docx 段落级手术（修改/精简）的基底
                "original_path": temp_path,
            }
            print(f"[extract_cache] 命中 {filename} "
                  f"({cached.get('char_count', 0)} chars，跳过解析)")
            return task_id

    extract_tasks[task_id] = {
        "file_id": task_id,
        "filename": filename,
        "status": "pending",
        "message": "任务已创建，等待处理...",
        "preview": None,
        "char_count": 0,
        "persisted": False,
        "file_hash": file_hash,
        "created_at": time.time()
    }

    # 启动后台提取线程
    thread = threading.Thread(
        target=_do_extract,
        args=(task_id, temp_path, persist, doc_type),
        daemon=True
    )
    thread.start()

    return task_id


def get_extract_status(task_id: str) -> Optional[dict]:
    """查询提取任务状态"""
    if task_id not in extract_tasks:
        return None

    task = extract_tasks[task_id]
    return {
        "file_id": task["file_id"],
        "filename": task["filename"],
        "status": task["status"],
        "message": task["message"],
        "preview": task.get("preview"),
        "char_count": task.get("char_count", 0),
        "persisted": task.get("persisted", False)
    }


def resolve_attachment_content(file_ids: Optional[List[str]] = None) -> str:
    """
    将 file_ids 解析为完整的附件文本内容

    从 uploads collection 检索所有 file_id 对应的 chunks，
    合并为完整文本返回。

    Args:
        file_ids: 已入库的文件 ID 列表

    Returns:
        合并的附件文本内容
    """
    if not file_ids:
        return ""

    try:
        from app.services.rag.vector_store import VectorStore
        vs = VectorStore(collection_name="uploads")

        all_texts = []
        for file_id in file_ids:
            try:
                results = vs.collection.get(
                    where={"file_id": file_id},
                    include=["documents"]
                )
                if results and results.get("documents"):
                    all_texts.extend(results["documents"])
            except Exception:
                continue

        return "\n\n".join(all_texts) if all_texts else ""
    except Exception:
        return ""


def resolve_attachment_texts(file_ids: Optional[List[str]] = None) -> List[str]:
    """
    将 file_ids 解析为各附件的独立文本列表（保持附件边界，不合并）。

    与 resolve_attachment_content 的区别：
    - resolve_attachment_content 返回所有附件合并后的单一字符串
    - resolve_attachment_texts 返回各附件独立的文本，用于配额分配/逐附件检索

    Args:
        file_ids: 已入库的文件 ID 列表

    Returns:
        各附件文本组成的列表（按 file_ids 顺序），空文本附件被跳过
    """
    if not file_ids:
        return []

    try:
        from app.services.rag.vector_store import VectorStore
        vs = VectorStore(collection_name="uploads")

        texts = []
        for file_id in file_ids:
            try:
                results = vs.collection.get(
                    where={"file_id": file_id},
                    include=["documents"]
                )
                if results and results.get("documents"):
                    text = "\n\n".join(results["documents"])
                    if text.strip():
                        texts.append(text)
            except Exception:
                continue

        return texts
    except Exception:
        return []
