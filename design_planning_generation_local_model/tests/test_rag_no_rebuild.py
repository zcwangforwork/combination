# -*- coding: utf-8 -*-
"""免重建 RAG 检索优化（2026-10-10）纯函数单测。

覆盖不改向量索引的检索层增强（含两处经评测撤销的实验守护）：
  1. tokenizer 标准号规范化 token（GB 9706.1-2020 / gb9706.1 对齐）
  2. reranker 精排输入 = 纯正文截断（元数据前缀实验经评测撤销，守护不回潮）
  3. 跨查询 RRF 融合 _fuse_rrf（多查询融合核心数学）

不依赖 Chroma / GPU / LLM——聚焦可确定性验证的融合与文本变换逻辑。
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rag.tokenizer import _extract_std_num_tokens  # noqa: E402
from app.services.rag.reranker import Reranker  # noqa: E402
from app.services.rag.vector_store import VectorStore  # noqa: E402


# ── 1. 标准号规范化 ──

def test_std_num_variants_align():
    """同一标准的不同写法应得到相同规范化 token（去空格/斜杠/t、去年代后缀）"""
    cases = [
        (["gb9706.1"], "GB 9706.1-2020 通用要求", "gb9706.1 无空格小写"),
        (["gb9706.1"], "gb9706.1 中的规定", "gb9706.1 原始紧凑"),
        (["gb42062"], "GB/T 42062-2022 风险管理", "GB/T 带斜杠带年"),
        (["gb42062"], "GBT42062 医疗器械风险管理", "GBT 无分隔"),
        (["iso14971"], "ISO 14971:2019 风险管理", "ISO 冒号年"),
        (["iec60601-1-11"], "IEC 60601-1-11:2015 并列标准", "IEC 多段号"),
    ]
    for expect, text, label in cases:
        got = _extract_std_num_tokens(text)
        assert got == expect, f"{label}: {text!r} → {got} != {expect}"


def test_std_num_fullwidth_normalized():
    """全角标点（／．－：）应先转半角再匹配"""
    got = _extract_std_num_tokens("GB／T ４２０６２".replace("４２０６２", "42062"))
    assert got == ["gb42062"], f"全角斜杠: {got}"
    got = _extract_std_num_tokens("GB 9706．1-2020")
    assert got == ["gb9706.1"], f"全角点号: {got}"


def test_std_num_no_false_positive_in_word():
    """英文单词内出现的 gb/en 等字母串不应被识别为标准号前缀"""
    assert _extract_std_num_tokens("agb123 结尾拼接") == []
    assert _extract_std_num_tokens("engine 5000 转速") == []


def test_std_num_in_tokenizer_output():
    """分词结果应附加规范化 token（端到端）"""
    from app.services.rag.tokenizer import get_tokenizer
    tokens = get_tokenizer().tokenize("依据 GB 9706.1-2020 的电气安全要求")
    assert "gb9706.1" in tokens, f"tokens={tokens}"


# ── 2. reranker 精排输入（纯正文截断）──
# [2026-10-10 评测回退] 元数据前缀方案实测 MRR 0.56→0.17（同文件候选无差别化），
# 已撤销；以下用例守护「精排输入不得再引入元数据前缀」这一评测结论。

def test_rerank_doc_input_pure_truncation():
    """精排输入 = 纯正文截断，即使 chunk 带元数据也不加前缀"""
    chunk = {
        "source_file": "GB 9706.1-2020 通用要求.pdf",
        "section_title": "4.3 电气安全",
        "text": "x" * 5000,
    }
    out = Reranker._doc_input(chunk, 1500)
    assert out == "x" * 1500


def test_rerank_doc_input_no_meta():
    """无元数据 / 无 text 的 chunk 均安全退化"""
    assert Reranker._doc_input({"text": "y" * 2000}, 100) == "y" * 100
    assert Reranker._doc_input({}, 100) == ""


# ── 4. 跨查询 RRF 融合 ──

def _mk(cid, rrf, text=None):
    return {"chunk_id": cid, "rrf_score": rrf, "similarity": rrf,
            "text": text or cid}


def test_fuse_rrf_common_chunk_wins():
    """两路都排第一的 chunk 融合分最高"""
    p1 = [_mk("a", 0.032), _mk("b", 0.016), _mk("c", 0.008)]
    p2 = [_mk("a", 0.030), _mk("x", 0.015)]
    out = VectorStore._fuse_rrf([p1, p2])
    assert out[0]["chunk_id"] == "a"
    assert out[0]["matched_queries"] == 2
    # 融合分 = 1/61 + 1/61（两路均第 1）
    assert abs(out[0]["mq_rrf_score"] - 2.0 / 61.0) < 1e-9
    ids = [r["chunk_id"] for r in out]
    assert set(ids) == {"a", "b", "c", "x"}, "全部 chunk 保留"


def test_fuse_rrf_dedup_keeps_best_payload():
    """同一 chunk 跨路重复时保留单路 rrf 表现更好的载荷"""
    p1 = [_mk("a", 0.010, "weak")]
    p2 = [_mk("a", 0.030, "strong")]
    out = VectorStore._fuse_rrf([p1, p2])
    assert len(out) == 1
    assert out[0]["text"] == "strong"


def test_fuse_rrf_single_path_order():
    """单路时等价于按 rrf_score 降序"""
    p = [_mk("m", 0.01), _mk("k", 0.03), _mk("z", 0.02)]
    out = VectorStore._fuse_rrf([p])
    assert [r["chunk_id"] for r in out] == ["k", "z", "m"]


def test_fuse_rrf_empty():
    assert VectorStore._fuse_rrf([]) == []
    assert VectorStore._fuse_rrf([[], []]) == []
