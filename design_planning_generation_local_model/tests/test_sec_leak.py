"""sec_leak 单元测试 — L3 输出泄漏确定性检测（方案 §6.2）

覆盖：
1. 词级 n-gram 构造
2. 整段抄录 → BLOCK（含来源与 overlap）
3. 无关回答 / 改写转述 → PASS（明确不覆盖语义转述，L1 为前提）
4. min 分母语义：短回答整段命中同样拦截（对短回答严格）
5. 白名单 n-gram 剔除（法规原文等公开渠道文本不误拦）
6. denied 为空恒 PASS
7. check_and_report 的审计留痕挂接
"""
import pytest

from app.services import sec_leak


@pytest.fixture(autouse=True)
def _hermetic_whitelist(monkeypatch):
    """白名单缓存固定为空集（绕开文件加载，测试不受白名单文件内容影响）"""
    monkeypatch.setattr(sec_leak, "_whitelist_ngrams", set())
    yield


# 空格分隔的 ASCII 词，jieba 分词结果完全可预期（词 + 空格交错），
# n-gram 集合对"逐字抄录"判定是确定性的
_CHUNK = " ".join(f"w{i}" for i in range(17))          # 17 词连续片段
_QUOTE_ALL = " ".join(f"w{i}" for i in range(14))      # chunk 的前段整段抄录
_QUOTE_SHORT = " ".join(f"w{i}" for i in range(9))     # 短抄录（min 分母）
_UNRELATED = " ".join(f"x{i}" for i in range(20))
_PARAPHRASE = " ".join(f"p{i}" for i in range(20))


def _denied(text):
    return [{"text": text, "source_file": "secret.docx", "sec_label": "秘密"}]


# ── 1. n-gram 构造 ───────────────────────────────────────────

def test_word_ngrams_basic():
    grams = sec_leak.word_ngrams("a b c d e f g h i", 8)
    assert len(grams) == 2  # (a..h) 与 (b..i)
    assert sec_leak.word_ngrams("太短了", 8) == set()  # 不足 n 词 → 空集


# ── 2. 整段抄录 → BLOCK ─────────────────────────────────────

def test_verbatim_quote_blocked():
    hit = sec_leak.check_output_leakage(_QUOTE_ALL, _denied(_CHUNK))
    assert hit is not None
    assert hit["source_file"] == "secret.docx"
    assert hit["sec_label"] == "秘密"
    assert hit["overlap"] > 0.15


# ── 3. 无关 / 转述 → PASS ───────────────────────────────────

def test_unrelated_answer_passes():
    assert sec_leak.check_output_leakage(_UNRELATED, _denied(_CHUNK)) is None


def test_paraphrase_passes():
    """模型用自己的话转述：确定性词级重叠为零 → PASS（§6.2 明确不覆盖项）"""
    assert sec_leak.check_output_leakage(_PARAPHRASE, _denied(_CHUNK)) is None


def test_empty_inputs_pass():
    assert sec_leak.check_output_leakage("", _denied(_CHUNK)) is None
    assert sec_leak.check_output_leakage(_QUOTE_ALL, []) is None
    assert sec_leak.check_output_leakage(_QUOTE_ALL, [{"text": "", "source_file": "x"}]) is None


# ── 4. min 分母：短回答整段命中同样拦 ───────────────────────

def test_short_quote_strict():
    """overlap = |A∩C| / min(|A|,|C|)：短回答全部由抄录构成 → overlap→1 → BLOCK"""
    hit = sec_leak.check_output_leakage(_QUOTE_SHORT, _denied(_CHUNK))
    assert hit is not None
    assert hit["overlap"] > 0.9


def test_threshold_override():
    """阈值调到 >1 → 永不拦截（参数覆盖通道）"""
    assert sec_leak.check_output_leakage(
        _QUOTE_ALL, _denied(_CHUNK), threshold=1.1) is None


# ── 5. 白名单剔除 ───────────────────────────────────────────

def test_whitelist_ngrams_exempt():
    """denied chunk 的 n-gram 全部在白名单（如法规原文）→ 双侧剔除后无重叠 → PASS"""
    sec_leak._whitelist_ngrams = sec_leak.word_ngrams(_CHUNK, 8)
    assert sec_leak.check_output_leakage(_QUOTE_ALL, _denied(_CHUNK)) is None
    sec_leak._whitelist_ngrams = set()  # 还原


# ── 6. check_and_report 审计挂接 ─────────────────────────────

def test_check_and_report_marks_audit(monkeypatch):
    from app.services import sec_audit
    calls = []
    monkeypatch.setattr(sec_audit, "mark_leak_blocked",
                        lambda u, sf, ov: calls.append((u, sf, ov)))
    hit = sec_leak.check_and_report(_QUOTE_ALL, _denied(_CHUNK), username="eve")
    assert hit is not None
    assert len(calls) == 1
    assert calls[0][0] == "eve"
    assert calls[0][1] == "secret.docx"
    # PASS 时不留拦截审计
    hit2 = sec_leak.check_and_report(_UNRELATED, _denied(_CHUNK), username="eve")
    assert hit2 is None
    assert len(calls) == 1


def test_block_message_exists():
    assert "保密" in sec_leak.BLOCK_MESSAGE
