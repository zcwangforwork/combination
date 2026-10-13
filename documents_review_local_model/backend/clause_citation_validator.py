"""法规条款引用校验 — 防止 LLM 编造未在检索片段中出现的条款号。

校验策略：
  1. 从 LLM 输出中提取所有"标准号+条款号"组合
  2. 从 section_knowledge（检索片段）中提取合法条款号集合
  3. 比对：LLM 引用的条款号若不在合法集合中 → 标注"⚠ 引用待核实"
  4. 若知识库片段中提取到的条款号 < 2 个（chunk 无明确条款号），跳过校验

不阻断主流程：任何异常仅 log warning，返回原文本或空校验结果。
"""
import re
import logging
from typing import List, Tuple, Set, Dict, Any

logger = logging.getLogger(__name__)


# 标准号前缀（支持中英文，按出现频率排序以提高正则匹配效率）
_STD_PREFIXES = (
    r"ISO\s*\d{3,5}(?::\d{4})?",       # ISO 14971, ISO 14971:2019, ISO 13485:2016
    r"IEC\s*\d{4,5}(?::\d{4})?",       # IEC 62304, IEC 62304:2015
    r"GB/T\s*\d{4,5}(?:-\d{4})?",      # GB/T 42062-2022
    r"YY/T\s*\d{3,5}(?:-\d{4})?",      # YY/T 0316, YY/T 0664
    r"NMPA\s*GMP",                     # NMPA GMP
    r"MDR\s*\d{4}/\d+",                # MDR 2017/745
    r"FDA\s*21\s*CFR\s*Part\s*\d+",    # FDA 21 CFR Part 820
)

# 完整条款引用模式：<标准号> <分隔符> <数字.数字...>
# 分隔符必须是 §（前后可有空格）或至少一个空格，避免把 "iso14971.md" 这类
# 文件名误识别为 "ISO 1497 §1"（\d{3,5} 回溯后接文件名中的数字）。
# 例：ISO 14971:2019 §5.4.1, IEC 62304 5.6, GB/T 42062-2022 §5.4
_CITATION_RE = re.compile(
    r"(" + "|".join(_STD_PREFIXES) + r")"
    r"(?:\s*§\s*|\s+)"  # 必须有 § 或至少一个空格分隔
    r"(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)


def _normalize_std(std: str) -> str:
    """标准化标准号：去空格、去年份、统一大小写。

    'ISO 14971:2019' → 'ISO14971'
    'gb/t 42062-2022' → 'GB/T42062'
    'IEC 62304' → 'IEC62304'
    """
    s = std.strip()
    # 去年份后缀（:2019 或 -2022）
    s = re.sub(r"[:\-]\d{4}$", "", s)
    # 去所有空格（保留 GB/T 中的斜杠）
    s = re.sub(r"\s+", "", s).upper()
    return s


def extract_citations(text: str) -> List[Tuple[str, str, str, Tuple[int, int]]]:
    """从文本中提取所有条款引用。

    Args:
        text: 待提取的文本（LLM 输出或知识库 chunk 文本）

    Returns:
        [(std_raw, clause_num, normalized_key, (start, end)), ...]
        normalized_key = f"{_normalize_std(std_raw)}|{clause_num}"
        std_raw: 原始标准号字符串（如 'ISO 14971:2019'）
        clause_num: 条款号（如 '5.4.1'）
    """
    if not text:
        return []
    results = []
    for m in _CITATION_RE.finditer(text):
        std_raw = m.group(1)
        clause_num = m.group(2)
        key = f"{_normalize_std(std_raw)}|{clause_num}"
        results.append((std_raw, clause_num, key, m.span()))
    return results


def extract_kb_clauses(knowledge_text: str) -> Set[str]:
    """从知识库检索片段中提取所有合法条款号集合（normalized keys）。

    知识库 chunk 格式参考 agent_graph._retrieve_section_knowledge:
        **[source.md]**
        <chunk text>
    ----
        **[source2.md]**
        <chunk text>

    提取所有 chunk 文本中的条款号，归一化为 set 用于后续比对。
    """
    if not knowledge_text:
        return set()
    clauses: Set[str] = set()
    for _, _, key, _ in extract_citations(knowledge_text):
        clauses.add(key)
    return clauses


def validate_citations(
    result_content: str,
    section_knowledge: str,
    min_kb_clauses: int = 2,
) -> Dict[str, Any]:
    """校验 result_content 中的条款引用是否在 section_knowledge 中出现。

    Args:
        result_content: LLM 生成的审核结果文本
        section_knowledge: 该小节检索到的知识库片段（chunk 拼接文本）
        min_kb_clauses: 知识库片段中最少要有多少个条款号才启用校验；
                       少于此数认为 chunk 无明确条款号可参照，跳过校验，
                       避免对全部引用误标"未核实"。

    Returns:
        {
            "enabled": bool,           # 是否实际执行了校验
            "total": int,              # result_content 中提取的去重后引用数
            "verified": int,           # 在知识库中找到的引用数
            "unverified": int,         # 未在知识库中找到的引用数
            "unverified_list": [       # 未核实引用详情
                {"std": "ISO 14971:2019", "clause": "5.4.1", "raw": "ISO 14971:2019 §5.4.1"},
                ...
            ],
        }
    """
    result: Dict[str, Any] = {
        "enabled": False,
        "total": 0,
        "verified": 0,
        "unverified": 0,
        "unverified_list": [],
    }
    if not result_content:
        return result

    citations = extract_citations(result_content)
    if not citations:
        return result

    kb_clauses = extract_kb_clauses(section_knowledge)
    if len(kb_clauses) < min_kb_clauses:
        # 知识库片段无明确条款号，无法校验 → 跳过
        logger.debug(
            f"跳过条款校验：知识库片段仅含 {len(kb_clauses)} 个条款号 "
            f"< {min_kb_clauses}，认为 chunk 无可参照条款号"
        )
        return result

    result["enabled"] = True

    seen_keys: Set[str] = set()
    for std_raw, clause_num, key, _ in citations:
        if key in seen_keys:
            continue  # 去重：同一标准号+条款号只计一次
        seen_keys.add(key)
        result["total"] += 1
        if key in kb_clauses:
            result["verified"] += 1
        else:
            result["unverified"] += 1
            result["unverified_list"].append({
                "std": std_raw,
                "clause": clause_num,
                "raw": f"{std_raw} §{clause_num}",
            })

    return result


def annotate_unverified(
    result_content: str,
    validation: Dict[str, Any],
    max_annotations: int = 5,
) -> str:
    """在 result_content 末尾追加"引用核实说明"段（不破坏原内容）。

    仅当 validation["enabled"] 且存在未核实引用时追加；
    其他情况原样返回 result_content。

    Args:
        result_content: LLM 生成的原始审核结果文本
        validation: validate_citations() 的返回值
        max_annotations: 最多列出的未核实引用条数，超出部分汇总提示

    Returns:
        追加了"⚠ 引用核实提示"段的文本（或原文本）
    """
    if not validation.get("enabled") or validation.get("unverified", 0) == 0:
        return result_content

    unverified = validation["unverified_list"][:max_annotations]
    lines = [
        "",
        "---",
        "### ⚠ 引用核实提示",
        f"本小节审核结果中检测到 **{validation['unverified']}** 处法规条款引用"
        f"未在检索到的知识库片段中直接出现，可能为 LLM 自主生成，建议人工核实：",
        "",
    ]
    for item in unverified:
        lines.append(f"- `{item['raw']}` — 请确认该条款号在原标准文本中存在且引用准确")
    if validation["unverified"] > max_annotations:
        lines.append(
            f"- ...其余 {validation['unverified'] - max_annotations} 处未核实引用，"
            f"详见审核结果中的条款标注"
        )
    lines.append("")
    return result_content.rstrip() + "\n" + "\n".join(lines)
