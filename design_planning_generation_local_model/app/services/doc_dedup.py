"""
doc_dedup — 生成后全文档去重兜底

在 Markdown → Word 转换前对完整文档内容做去重处理，降低章节/内容重复：

1. 过滤冗余前缀行（"本章依据XX编制"、"合规性说明"等，与 minimax.py 旧版过滤保持一致）
2. 去除全文档中精确/近似重复的正文行（非表格、非标题，保留首次出现）
3. 合并高相似度小节（两个小节内容近似度超阈值时，保留更详细者，删除重复者）

纯文本处理（str -> str），无外部依赖，可安全用于所有生成路径。
"""
import re


# 冗余前缀（行首匹配，整行过滤）—— 与 minimax.py `_generate_by_chapters` 过滤一致
REDUNDANT_PREFIXES = (
    '本章依据', '本节依据', '本节规定', '本节定义', '本节基于',
    '合规性说明', '实施建议', '参数映射表', '本章内容明确',
    '本章规定', '上述标准', '上述参数', '本章将', '本节将',
    '本小节将', '本节内容将',
)

# 独立冗余行（整行完全匹配，模型误生成的元子节标题）
REDUNDANT_EXACT_LINES = ('目的', '适用范围', '定义', '概述')

# 小节内容相似度阈值：超过则判定为重复小节，删除较短者
SECTION_SIMILARITY_THRESHOLD = 0.88

# 参与小节相似度比较的最小内容长度（避免把短小节误判合并）
SECTION_MIN_LEN = 120

# 精确重复行去除的最小长度（所有正文行参与，低阈值安全无副作用）
DUP_EXACT_MIN_LEN = 4

# 近似重复行去除的最小长度（仅非列表项参与，避免误删短小但必要的碎片行）
DUP_LINE_MIN_LEN = 12


def _is_heading(line: str) -> bool:
    s = line.strip()
    return s.startswith('#') and len(s) > 1


def _is_table_line(line: str) -> bool:
    return line.strip().startswith('|')


def _normalize(text: str) -> str:
    """归一化：去空白，用于重复行比较"""
    return re.sub(r'\s+', '', text)


def _bigrams(text: str) -> set:
    """字符 bigram 集合，用于中文文本相似度计算"""
    text = re.sub(r'\s+', '', text)
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _similarity(a: str, b: str) -> float:
    ta, tb = _bigrams(a), _bigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _filter_redundant_lines(content: str) -> str:
    """过滤冗余前缀行与独立冗余行"""
    out = []
    in_fence = False
    for line in content.split('\n'):
        s = line.strip()
        # 围栏代码块（mermaid / 普通代码）整体保留，避免误删围栏内行
        if s.startswith('```'):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if not s:
            out.append(line)
            continue
        if _is_heading(line):
            out.append(line)
            continue
        if any(s.startswith(p) for p in REDUNDANT_PREFIXES):
            continue
        if s in REDUNDANT_EXACT_LINES:
            continue
        out.append(line)
    return '\n'.join(out)


def _remove_duplicate_lines(content: str) -> str:
    """去除全文档中精确/近似重复的正文行（保留首次出现）。

    精确匹配用 dict O(1)，所有正文行（含列表项）参与，阈值低（DUP_EXACT_MIN_LEN）
    保证安全；近似匹配按长度分桶（±15%）缩小候选集，仅非列表项参与且阈值更高，
    避免误删相似但不同的并列项。列表项先剥离 `- ` / `* ` 前缀再计算正文。
    """
    seen_exact: dict = {}     # normalized -> None（精确匹配集合）
    seen_by_len: dict = {}    # 长度桶 -> [normalized, ...]（近似匹配候选，仅非列表项）
    out = []
    in_fence = False
    for line in content.split('\n'):
        s = line.strip()
        # 围栏代码块（mermaid / 普通代码）整体保留，不去重：
        # 否则第二个 ```mermaid 围栏及其内部与首块重复的行（如 flowchart TD）
        # 会被当作重复正文行删除，导致围栏结构被破坏、后续内容被吞入孤立代码块
        if s.startswith('```'):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if (not s
                or _is_heading(line)
                or _is_table_line(line)
                or s == '---'):
            out.append(line)
            continue
        is_list_item = s.startswith('- ') or s.startswith('* ')
        body = s[2:] if is_list_item else s
        key = _normalize(body)
        if len(key) < DUP_EXACT_MIN_LEN:
            out.append(line)
            continue
        if key in seen_exact:
            continue  # 精确重复，跳过

        # 非列表项再做近似匹配（只与长度相近的行比较）
        if not is_list_item:
            klen = len(key)
            lo, hi = int(klen * 0.85), int(klen * 1.15)
            dup = False
            for bucket_len in range(max(lo, DUP_LINE_MIN_LEN), hi + 1):
                for existing in seen_by_len.get(bucket_len, ()):
                    if _similarity(key, existing) > 0.92:
                        dup = True
                        break
                if dup:
                    break
            if dup:
                continue
            seen_by_len.setdefault(klen, []).append(key)

        seen_exact[key] = None
        out.append(line)
    return '\n'.join(out)


def _split_blocks(content: str) -> list:
    """按标题行将文档切分为 (heading_or_empty, body) 块列表"""
    blocks = []
    current_heading = ''
    current_body = []
    for line in content.split('\n'):
        if _is_heading(line):
            if current_heading or current_body:
                blocks.append((current_heading, '\n'.join(current_body).strip()))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)
    if current_heading or current_body:
        blocks.append((current_heading, '\n'.join(current_body).strip()))
    return blocks


def _merge_similar_sections(content: str) -> str:
    """合并高相似度小节：两个小节内容近似度超阈值时保留较详细者，删除重复者。

    仅处理长度 >= SECTION_MIN_LEN 的内容块，阈值保守（0.88），
    避免误删真实但不完全相同的小节。
    """
    blocks = _split_blocks(content)
    if len(blocks) < 2:
        return content

    # 标记待删除的块下标
    drop_idx = set()
    # 只对"有标题且有实质内容"的块做比较
    indexable = [
        (i, blocks[i]) for i in range(len(blocks))
        if blocks[i][0] and len(blocks[i][1]) >= SECTION_MIN_LEN
    ]

    for a in range(len(indexable)):
        if indexable[a][0] in drop_idx:
            continue
        ia, (ha, ba) = indexable[a]
        for b in range(a + 1, len(indexable)):
            ib, (hb, bb) = indexable[b]
            if ib in drop_idx:
                continue
            sim = _similarity(ba, bb)
            if sim >= SECTION_SIMILARITY_THRESHOLD:
                # 保留较详细者，删除较短者
                if len(ba) >= len(bb):
                    drop_idx.add(ib)
                else:
                    drop_idx.add(ia)
                    break  # ia 被替换，停止对其继续比较

    if not drop_idx:
        return content

    out = []
    for i, (heading, body) in enumerate(blocks):
        if i in drop_idx:
            continue
        if heading:
            out.append(heading)
        if body:
            out.append(body)
    return '\n'.join(out)


def dedup_markdown(content: str) -> str:
    """对完整 Markdown 文档内容执行去重处理（幂等，可安全重复调用）。

    流程：过滤冗余行 → 去除重复行 → 合并相似小节。
    """
    if not content:
        return content
    content = _filter_redundant_lines(content)
    content = _remove_duplicate_lines(content)
    content = _merge_similar_sections(content)
    return content
