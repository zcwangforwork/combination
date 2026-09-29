"""
sec_leak — L3 输出泄漏兜底检测（2026-09-28 新增）

依据方案 §6.2：对"本次检索中被密级过滤掉的 chunk 集合（denied set）"与
回答文本做**确定性**词级 n-gram 重叠检测——不是"AI 审查 AI"，而是集合交
运算，毫秒级、可判定、可审计。

检测语义：
  overlap = |A ∩ C| / min(|A|, |C|)   （A=回答 n-gram 集，C=denied chunk n-gram 集）
  overlap > SEC_LEAK_THRESHOLD（默认 0.15）→ BLOCK

设计要点（方案原文）：
- 8-gram（词级）：中文 8 词连续重叠几乎不可能是巧合，误报率可忽略；
  比字符级 n-gram 更抗分词噪声；
- 归一化取 min 分母：对短回答严格、长回答宽容（"整段抄录才拦"）；
- 白名单机制：法规标准原文、已公开模板等"公开渠道亦存在"的文本加入
  白名单 n-gram 集，检测前剔除（否则标准条款引用会误拦）；
- 明确不覆盖的威胁：模型用自己的话语义转述越权内容——L1 生效前提下
  上下文本无该内容，无从转述，无需 L3 对抗。

注意：流式路径的 token 已经流出，无法撤回；L3 在流结束时的定位是
"事后兜底 + 审计 + 前端替换提示"，主防线永远是 L1（§1.2 纵深防御）。
"""
import os
import threading
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(__file__).parent
_WHITELIST_PATH = _BASE_DIR / "rag" / "sec_leak_whitelist.txt"

BLOCK_MESSAGE = (
    "该回答可能涉及您暂无查看权限的保密资料，已拦截。"
    "如确因工作需要，请联系保密管理员申请相应权限。"
)

_whitelist_ngrams: Optional[set] = None
_whitelist_lock = threading.Lock()


def cfg_ngram() -> int:
    """SEC_LEAK_NGRAM：词级 n-gram 长度（默认 8）"""
    try:
        return max(3, int(os.environ.get("SEC_LEAK_NGRAM", "8")))
    except ValueError:
        return 8


def cfg_threshold() -> float:
    """SEC_LEAK_THRESHOLD：重叠率拦截阈值（默认 0.15）"""
    try:
        return float(os.environ.get("SEC_LEAK_THRESHOLD", "0.15"))
    except ValueError:
        return 0.15


def _tokenize(text: str) -> list:
    """jieba 分词（复用 rag/tokenizer 的缓存与领域词典）"""
    from app.services.rag.tokenizer import get_tokenizer
    return list(get_tokenizer().tokenize(text or ""))


def word_ngrams(text: str, n: int) -> set:
    """词级 n-gram 集合（tuple of tokens；不足 n 词返回空集）"""
    tokens = _tokenize(text)
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _load_whitelist() -> set:
    """白名单 n-gram 集（惰性加载 + 缓存；文件缺省为空 = 无豁免）"""
    global _whitelist_ngrams
    with _whitelist_lock:
        if _whitelist_ngrams is not None:
            return _whitelist_ngrams
        grams: set = set()
        try:
            if _WHITELIST_PATH.exists():
                n = cfg_ngram()
                for line in _WHITELIST_PATH.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        grams |= word_ngrams(line, n)
        except Exception as e:  # noqa: BLE001
            print(f"[sec_leak] 白名单加载失败（按无白名单处理）: {e}")
        _whitelist_ngrams = grams
        return grams


def reset_whitelist_cache() -> None:
    """白名单文件更新后清缓存（管理端热更新用）"""
    global _whitelist_ngrams
    with _whitelist_lock:
        _whitelist_ngrams = None


def check_output_leakage(answer: str, denied_chunks: list,
                         *, n: int = None, threshold: float = None) -> Optional[dict]:
    """回答文本 vs denied chunk 集合的确定性重叠检测。

    Args:
        answer: 待检测的回答全文
        denied_chunks: sec_filter.drain_denied() 取出的被过滤 chunk 列表，
                       每项含 text / source_file / sec_label
        n / threshold: 覆盖默认配置（测试用）

    Returns:
        None = PASS；命中返回 {"source_file", "sec_label", "overlap"} 供审计。
        denied 集合为空（L1 未过滤到任何候选，或 mode=off）时恒 PASS。
    """
    if not answer or not denied_chunks:
        return None
    n = n or cfg_ngram()
    threshold = cfg_threshold() if threshold is None else threshold

    whitelist = _load_whitelist()
    a_grams = word_ngrams(answer, n)
    if whitelist:
        a_grams = a_grams - whitelist
    if not a_grams:
        return None

    best: Optional[dict] = None
    for chunk in denied_chunks:
        text = (chunk or {}).get("text", "")
        if not text:
            continue
        c_grams = word_ngrams(text, n)
        if whitelist:
            c_grams = c_grams - whitelist
        if not c_grams:
            continue
        denom = min(len(a_grams), len(c_grams))
        if denom <= 0:
            continue
        overlap = len(a_grams & c_grams) / denom
        if overlap > threshold and (best is None or overlap > best["overlap"]):
            best = {
                "source_file": chunk.get("source_file", "(未知来源)"),
                "sec_label": chunk.get("sec_label", ""),
                "overlap": round(overlap, 4),
            }
    return best


def check_and_report(answer: str, denied_chunks: list, username: str = "") -> Optional[dict]:
    """检测 + 审计留痕的一体化入口（L3 挂接点统一调用本函数）。

    Returns:
        None = PASS；BLOCK 时返回命中信息（调用方负责用 BLOCK_MESSAGE 替换输出）。
    """
    hit = check_output_leakage(answer, denied_chunks)
    if hit is not None:
        try:
            from app.services import sec_audit
            sec_audit.mark_leak_blocked(username, hit["source_file"], hit["overlap"])
        except Exception:  # noqa: BLE001
            pass
    return hit
