"""提取结果磁盘缓存测试：_save/_load_extract_cache + submit_extract_task 命中路径

覆盖：
1. 保存 → 读取往返（TTL 内命中）
2. 过期缓存返回 None
3. 空内容缓存返回 None
4. submit_extract_task 命中缓存：任务直接 completed、不启动解析线程
"""
import json
import os
import time
import tempfile

from app.services import attachment_service as avs


def test_cache_roundtrip(tmp_path):
    d = str(tmp_path)
    orig = avs._EXTRACT_CACHE_DIR
    avs._EXTRACT_CACHE_DIR = d
    try:
        avs._save_extract_cache("abc123", "模板.docx", "全文内容", 4, "全文内容", "")
        cached = avs._load_extract_cache("abc123")
        assert cached is not None
        assert cached["filename"] == "模板.docx"
        assert cached["full_text"] == "全文内容"
        assert cached["char_count"] == 4
        assert "cached_at" in cached
    finally:
        avs._EXTRACT_CACHE_DIR = orig


def test_cache_expired(tmp_path):
    orig = avs._EXTRACT_CACHE_DIR
    avs._EXTRACT_CACHE_DIR = str(tmp_path)
    try:
        # 手工写入一个过期缓存（cached_at 早于 TTL）
        data = {"filename": "旧.docx", "full_text": "内容", "char_count": 2,
                "preview": "内容", "toc": "",
                "cached_at": time.time() - (avs._EXTRACT_CACHE_TTL_HOURS + 1) * 3600}
        with open(os.path.join(str(tmp_path), "old.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        assert avs._load_extract_cache("old") is None
    finally:
        avs._EXTRACT_CACHE_DIR = orig


def test_cache_empty_text(tmp_path):
    orig = avs._EXTRACT_CACHE_DIR
    avs._EXTRACT_CACHE_DIR = str(tmp_path)
    try:
        avs._save_extract_cache("empty1", "空.docx", "", 0, "", "")
        assert avs._load_extract_cache("empty1") is None
    finally:
        avs._EXTRACT_CACHE_DIR = orig


def test_submit_task_cache_hit():
    """命中缓存：任务立即 completed，无后台解析（from_cache 标记）"""
    # 预置缓存
    avs._save_extract_cache("deadbeef", "模板.docx", "缓存全文", 4, "缓存全文", "")
    try:
        # 构造与缓存哈希一致的调用：直接 mock compute_file_hash
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
            tf.write(b"dummy")
            temp = tf.name
        try:
            orig_hash = avs.compute_file_hash
            avs.compute_file_hash = lambda p: "deadbeef"
            task_id = avs.submit_extract_task(b"dummy", "模板.docx", persist=False)
        finally:
            avs.compute_file_hash = orig_hash
            os.remove(temp)

        task = avs.extract_tasks[task_id]
        assert task["status"] == "completed"
        assert task["full_text"] == "缓存全文"
        assert task["char_count"] == 4
        assert task.get("from_cache") is True
        assert "命中缓存" in task["message"]
        # original_path 保留（docx 段落级手术基底）
        assert task.get("original_path")
    finally:
        # 清理
        try:
            os.remove(avs._extract_cache_path("deadbeef"))
        except OSError:
            pass
