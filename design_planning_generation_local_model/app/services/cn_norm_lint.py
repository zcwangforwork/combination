# -*- coding: utf-8 -*-
"""cn_norm_lint —— 确定性中文规范校验器（中国体系文档写作合规提升 方案模块一）。

定位（方案 §2.1）：
- 管：字词级规范性（助动词 M 组 / 标点 P 组 / 数字单位 N 组）、文档级结构
  （八股章节 S 组）、引用有效性（R 组）、术语一致性（T 组）；
- 不管：语义对错、内容质量、条款适用性、英文文档。

执行模型：
1. autofix_text() 先做"安全自动修复"（autocorrect-py 排版 + 自研 P01/P02/P03/N01），
   修复不改语义，修复计数计入报告；
2. lint_document() 对修复后文本跑全部规则，输出结构化违规清单
   （rule_id / rule_name / location / severity / suggestion / exempted）；
3. 豁免上下文引擎先行做区间标记（书名号/引号/条款行/修订表格/附录），
   命中豁免区间的只进豁免统计不报违规（方案 §2.4）。

纯规则、零 LLM、零网络——不接入任何云端校对 API（本地化红线）。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── 配置项（方案 §9.1）──
# cn_norm_lint.py 位于 app/services/ → app/data 是其同级目录
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CN_NORM_TERMS_PATH = os.getenv("CN_NORM_TERMS_PATH", "") or os.path.join(
    _DATA_DIR, "cn_norm_terms.json")
CN_LINT_CONFIG_PATH = os.getenv("CN_LINT_CONFIG_PATH", "") or os.path.join(
    _DATA_DIR, "cn_lint_config.json")
DOC_REGISTRY_PATH = os.path.join(_DATA_DIR, "doc_registry.json")

# ── SOP/程序文件类 doc_type（S01 八股校验适用范围）与记录类（S02 适用范围）──
SOP_DOC_TYPES = {
    "sop", "manufacturing_sop", "inspection_sop",
    "equipment_operation_procedures",
}
RECORD_DOC_TYPE_KEYWORDS = ("记录", "表单", "record", "form")

# ── S01 八股六章的近义词组（标题归一后包含任一关键词即算该章存在）──
_SOP_REQUIRED_CHAPTERS: List[Tuple[str, Tuple[str, ...]]] = [
    ("目的", ("目的",)),
    ("范围", ("范围", "适用")),
    ("职责", ("职责", "责任", "岗位")),
    ("工作程序", ("工作程序", "操作步骤", "程序", "流程", "作业", "步骤", "方法")),
    ("相关文件", ("相关文件", "引用文件", "参考文献", "依据文件")),
    ("记录", ("记录", "表单")),
]

# ── M04「建议+动词」句式判定用动词表（排除名词用法：建议书/修改建议等）──
_M04_VERB_RE = re.compile(
    r"建议(?=[进行采取采用对将在予以考虑优先使用开展实施设置建立明确避免禁止"
    r"保留遵循执行检查验证确认记录评估审核批准增加删除修改更新纳入排除加强完善"
    r"指定编制制定填写签署归档保存培训监测控制定期及时立即])")

# ── 豁免章节关键词（M04 在此类章节不报）──
_M04_EXEMPT_SECTION_KEYWORDS = ("参考资料", "背景", "编制说明", "参考文件", "引言", "前言")

_CJK_RE = re.compile(r"[一-鿿]")
_CJK_CLASS = "一-鿿"


@dataclass
class Violation:
    """单条违规（方案 §2.6 报告字段）。"""
    rule_id: str
    rule_name: str
    severity: str            # Error / Warning / Info
    location: str            # 章节路径 + 段落序号
    excerpt: str             # 原文片段（截断至 50 字）
    suggestion: str = ""     # 建议改法；空 = 请人工判断
    exempted: bool = False   # 豁免命中不进违规数，进豁免统计

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "location": self.location,
            "excerpt": self.excerpt,
            "suggestion": self.suggestion or "请人工判断",
            "exempted": self.exempted,
        }


@dataclass
class LintReport:
    """整份文档的校验报告。"""
    violations: List[Violation] = field(default_factory=list)
    exempted_hits: Dict[str, int] = field(default_factory=dict)  # rule_id → 豁免计数
    autofix_count: int = 0          # 自动修复处数（autocorrect + 自研修复）
    aux_stats: Dict[str, object] = field(default_factory=dict)   # M06 画像等

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "Error" and not v.exempted
                   for v in self.violations)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations
                   if v.severity == "Error" and not v.exempted)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations
                   if v.severity == "Warning" and not v.exempted)

    def to_dict(self) -> dict:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "exempted_hits": dict(self.exempted_hits),
            "autofix_count": self.autofix_count,
            "stats": self.aux_stats,
        }

    def summary_lines(self, max_items: int = 30) -> List[str]:
        """供日志/Agent 回复使用的简要清单。"""
        real = [v for v in self.violations if not v.exempted]
        lines = [f"共 {len(real)} 处违规（Error {self.error_count} / "
                 f"Warning {self.warning_count}），自动修复 {self.autofix_count} 处，"
                 f"豁免命中 {sum(self.exempted_hits.values())} 处。"]
        for v in real[:max_items]:
            sev = {"Error": "❌", "Warning": "⚠️", "Info": "ℹ️"}.get(v.severity, "·")
            lines.append(f"{sev}[{v.rule_id} {v.rule_name}] {v.location}: "
                         f"「{v.excerpt}」→ {v.suggestion or '请人工判断'}")
        if len(real) > max_items:
            lines.append(f"…其余 {len(real) - max_items} 处从略")
        return lines


# ══════════════════════════════════════════════════════════════════
# 规则元数据（名称与级别，供报告与前端展示）
# ══════════════════════════════════════════════════════════════════
RULE_META: Dict[str, Tuple[str, str]] = {
    "M01": ("禁用\"应当\"（GB/T 1.1）", "Error"),
    "M02": ("禁用\"应该\"（GB/T 1.1）", "Error"),
    "M03": ("\"必须\"限法规原文留用", "Error"),
    "M04": ("\"建议\"不作规范性表述", "Warning"),
    "M05": ("口语强调词（严禁/务必/应确保）", "Warning"),
    "M06": ("助动词使用画像", "Info"),
    "P01": ("重复标点", "Error"),
    "P02": ("中文句内半角标点", "Error"),
    "P03": ("省略号写法", "Warning"),
    "P04": ("并列数字/英文间误用顿号", "Warning"),
    "P05": ("书名号《》未配对", "Error"),
    "N01": ("全角数字", "Error"),
    "N02": ("量值与单位写法不一致", "Warning"),
    "N03": ("概数应用汉字", "Info"),
    "N04": ("千分位分节", "Warning"),
    "S01": ("程序文件八股六章齐全", "Error"),
    "S02": ("记录表单可追溯三要素", "Warning"),
    "S03": ("章节编号连续", "Error"),
    "R01": ("内部文件编号未登记", "Warning"),
    "R02": ("标准号写法不规范", "Warning"),
    "T01": ("术语写法与规范表不符", "Warning"),
}

# 规则开关外置配置（CN_LINT_CONFIG_PATH 可覆盖）
_DEFAULT_DISABLED_RULES: List[str] = []
_DISABLED_RULES: Optional[List[str]] = None


def _disabled_rules() -> List[str]:
    global _DISABLED_RULES
    if _DISABLED_RULES is None:
        rules = list(_DEFAULT_DISABLED_RULES)
        try:
            if os.path.exists(CN_LINT_CONFIG_PATH):
                with open(CN_LINT_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                rules = [str(r) for r in cfg.get("disabled_rules", rules)]
        except Exception as e:
            print(f"[cn_norm_lint] 读取规则开关配置失败，使用默认: {e}")
        _DISABLED_RULES = rules
    return _DISABLED_RULES


# ══════════════════════════════════════════════════════════════════
# 豁免上下文引擎（方案 §2.4）
# ══════════════════════════════════════════════════════════════════
def _merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """合并重叠区间并排序。"""
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def mark_exempt_intervals(text: str) -> List[Tuple[int, int]]:
    """标记豁免字符区间（闭开区间 [s, e)）。

    豁免区域（按方案 §2.4，markdown 阶段可判定的五种）：
    1. 书名号《》内 —— 法规/标准原文引用（法规用"应当/不得"，合法）；
    2. 成对引号“”/‘’内 —— 引文；
    3. 条款号引用行 —— "第28条""4.2.4"所在行（行主体为条款号的行整行豁免）；
    4. 修订记录表格 —— markdown 表头含"版本/修订"的表格整块；
    5. 附录原文 —— 标题含"附录"的章节正文。
    封面/页眉页脚属模板层，markdown 阶段不存在，由模板层负责。
    """
    intervals: List[Tuple[int, int]] = []

    # 1. 书名号《》（支持一层嵌套外的贪婪闭合：以最近 》为准——用非贪婪逐对匹配）
    for m in re.finditer(r"《[^《》]*》", text):
        intervals.append((m.start(), m.end()))

    # 2. 成对中文引号
    for m in re.finditer(r"“[^“”]*”", text):
        intervals.append((m.start(), m.end()))
    for m in re.finditer(r"‘[^‘’]*’", text):
        intervals.append((m.start(), m.end()))

    # 3/4/5. 按行处理：条款行 / 修订表格 / 附录章节
    offset = 0
    in_appendix = False
    in_revision_table = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        # 附录章节判定（# 开头的标题行）
        if stripped.startswith("#"):
            heading_txt = stripped.lstrip("#").strip()
            in_appendix = "附录" in heading_txt[:6] or stripped.startswith("#附录")
        # 修订记录表格判定：表格行（| 开头），表头含 版本/修订 则整块豁免直到非表格行
        if stripped.startswith("|"):
            if any(k in stripped for k in ("版本", "修订")) and not in_revision_table:
                in_revision_table = True  # 表头行起豁免
        else:
            in_revision_table = False
        line_exempt = in_appendix or in_revision_table
        # 条款号引用行：行主体（去空白后）≥60% 为条款号/数字/标点的短行
        if not line_exempt and stripped and len(stripped) <= 40:
            core = re.sub(r"[\s。；，、：()（）【】\[\]]", "", stripped)
            if core and re.fullmatch(r"(?:第?[0-9一二三四五六七八九十百]+[条章节]?)+"
                                     r"(?:[.．\-—][0-9]+)*", core):
                line_exempt = True
        if line_exempt:
            intervals.append((offset, offset + len(line)))
        offset += len(line)

    return _merge_intervals(intervals)


def _pos_exempted(pos: int, intervals: List[Tuple[int, int]]) -> bool:
    """二分判断字符位置是否落在豁免区间。"""
    lo, hi = 0, len(intervals)
    while lo < hi:
        mid = (lo + hi) // 2
        s, e = intervals[mid]
        if pos < s:
            hi = mid
        elif pos >= e:
            lo = mid + 1
        else:
            return True
    return False


# ══════════════════════════════════════════════════════════════════
# 自动修复（autocorrect-py + 自研 P01/P02/P03/N01）
# ══════════════════════════════════════════════════════════════════
def _autocorrect_available() -> bool:
    try:
        import autocorrect  # noqa: F401
        return True
    except ImportError:
        return False


def _run_autocorrect(text: str) -> Tuple[str, int]:
    """调用 autocorrect-py 做排版安全修复；不可用时原样返回。

    规则决策表见 .autocorrectrc（space-dash 关闭以保护标准号/文件编号，
    spellcheck 关闭——术语校验由自研 T01 词表承担）。"""
    try:
        from autocorrect import format
        fixed = format(text)
        if not fixed:
            return text, 0
        n = sum(1 for a, b in zip(text, fixed) if a != b) + \
            abs(len(text) - len(fixed))
        # 字符级差异数会高估（插入引起的错位）；用简单的字符集差值上限即可
        n = min(n, max(len(text), len(fixed)))
        return fixed, n
    except Exception as e:
        print(f"[cn_norm_lint] autocorrect 调用失败，跳过该层修复: {e}")
        return text, 0


# P02：中文句内半角标点（前后邻 CJK，或前 CJK 后行尾/空白）
_P02_RE = re.compile(
    rf"(?<=[{_CJK_CLASS}])([,;:!?])(?=[{_CJK_CLASS}]|$)")
# 句号单独处理：前邻 CJK 且后邻 CJK/空白/行尾（数字上下文小数点不命中）
_P02_DOT_RE = re.compile(
    rf"(?<=[{_CJK_CLASS}])\.(?=\s|$|[{_CJK_CLASS}])")
_P02_MAP = {",": "，", ";": "；", ":": "：", "!": "！", "?": "？", ".": "。"}

# P01：重复标点
_P01_RE = re.compile(r"([，。！？；：、])\1+")
# P03：省略号
_P03_RE = re.compile(r"\.{3,}|。{3,}|(?<![.…])…(?![…])")
# N01：全角数字/字母 → 半角（仅数字，字母交由 autocorrect halfwidth-word）
_N01_RE = re.compile(r"[０-９Ａ-Ｚａ-ｚ]+")


def _fullwidth_to_halfwidth(s: str) -> str:
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch == "　":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def autofix_text(text: str, use_autocorrect: bool = True) -> Tuple[str, int]:
    """安全自动修复一轮，返回 (修复后文本, 修复处数)。不改语义。"""
    fixed = text
    count = 0
    if use_autocorrect and _autocorrect_available():
        fixed, n = _run_autocorrect(fixed)
        count += n

    # P01 重复标点 → 单个
    fixed, n = _P01_RE.subn(lambda m: m.group(1), fixed); count += n
    # P02 中文句内半角 → 全角
    fixed, n = _P02_RE.subn(lambda m: _P02_MAP.get(m.group(1), m.group(1)), fixed); count += n
    fixed, n = _P02_DOT_RE.subn("。", fixed); count += n
    # P03 省略号 → ……
    fixed, n = _P03_RE.subn("……", fixed); count += n
    # N01 全角数字/字母 → 半角
    fixed, n = _N01_RE.subn(lambda m: _fullwidth_to_halfwidth(m.group(0)), fixed); count += n
    return fixed, count


# ══════════════════════════════════════════════════════════════════
# 章节切分（供 location 与 S 组规则）
# ══════════════════════════════════════════════════════════════════
def _split_sections(markdown: str) -> List[Tuple[str, str, int]]:
    """按标题切分 → [(标题文本, 正文, 正文起始偏移)]。

    无标题时整体作为一节。偏移指向正文在全文中的字符位置（豁免区间对齐用）。
    """
    sections: List[Tuple[str, str, int]] = []
    lines = markdown.splitlines(keepends=True)
    offset = 0
    cur_title = ""
    cur_start: Optional[int] = None
    for line in lines:
        if line.lstrip().startswith("#"):
            if cur_start is not None:
                sections.append((cur_title, markdown[cur_start:offset], cur_start))
            cur_title = line.lstrip().lstrip("#").strip() or "(无标题)"
            cur_start = offset + len(line)
        offset += len(line)
    if cur_start is None:
        sections.append(("", markdown, 0))
    else:
        sections.append((cur_title, markdown[cur_start:], cur_start))
    return sections


# ══════════════════════════════════════════════════════════════════
# 主入口：lint_document
# ══════════════════════════════════════════════════════════════════
def lint_document(markdown: str, doc_type: str = "",
                  autofix: bool = True) -> Tuple[str, LintReport]:
    """对文档全文执行校验。

    Args:
        markdown: 待检文本（建议传入导出前处理链 ②字数收敛 之后的最终文本）
        doc_type: 文档类型（决定 S 组规则的适用性）
        autofix: 是否先做安全自动修复（默认 True；False 供纯报告模式复检）

    Returns:
        (修复后文本, 报告)。调用方负责将修复后文本同步回 state。
    """
    report = LintReport()
    text = markdown or ""
    if not text.strip():
        return text, report

    if autofix:
        text, report.autofix_count = autofix_text(text)

    disabled = set(_disabled_rules())
    intervals = mark_exempt_intervals(text)

    def _excerpts(pos: int, text: str = text) -> str:
        s = max(0, pos - 20)
        e = min(len(text), pos + 30)
        frag = text[s:e].replace("\n", " ").strip()
        return (frag[:50] + "…") if len(frag) > 50 else frag

    def _hit(rule_id: str, pos: int, suggestion: str, section: str,
             para_idx: int = 1) -> None:
        """登记一处命中：豁免区间内 → 豁免统计；否则 → 违规清单。"""
        name, sev = RULE_META[rule_id]
        v = Violation(rule_id=rule_id, rule_name=name, severity=sev,
                      location=f"{section or '(全文)'} 段{para_idx}",
                      excerpt=_excerpts(pos), suggestion=suggestion)
        if _pos_exempted(pos, intervals):
            v.exempted = True
            report.exempted_hits[rule_id] = report.exempted_hits.get(rule_id, 0) + 1
        report.violations.append(v)

    # ── M 组：GB/T 1.1 助动词 ──
    if "M01" not in disabled:
        for m in re.finditer(r"应当", text):
            _hit("M01", m.start(), "改用\"应\"", _section_of(text, m.start()))
    if "M02" not in disabled:
        for m in re.finditer(r"应该", text):
            _hit("M02", m.start(), "改用\"应\"", _section_of(text, m.start()))
    if "M03" not in disabled:
        for m in re.finditer(r"必须", text):
            _hit("M03", m.start(),
                 "非法规原文引用改用\"应\"；引用法规原文请置于《》内",
                 _section_of(text, m.start()))
    if "M04" not in disabled:
        for m in _M04_VERB_RE.finditer(text):
            sec = _section_of(text, m.start())
            if any(k in sec for k in _M04_EXEMPT_SECTION_KEYWORDS):
                continue
            _hit("M04", m.start(), "规范性要求改用\"宜\"", sec)
    if "M05" not in disabled:
        for m in re.finditer(r"严禁", text):
            _hit("M05", m.start(), "改用\"不应\"", _section_of(text, m.start()))
        for m in re.finditer(r"务必", text):
            _hit("M05", m.start(), "改用\"应\"", _section_of(text, m.start()))
        for m in re.finditer(r"应确保", text):
            _hit("M05", m.start(), "\"应确保\"改用\"应\"（功能描述直接以\"应\"引导）",
                 _section_of(text, m.start()))
    if "M06" not in disabled:
        report.aux_stats["modal_profile"] = _modal_profile(text)

    # ── P 组残余检查（自动修复后仍存在的形态）──
    if "P04" not in disabled:
        for m in re.finditer(r"(?<=[0-9A-Za-z])、(?=[0-9A-Za-z])", text):
            _hit("P04", m.start(), "并列数字/英文间用逗号或连接号（序号列表除外）",
                 _section_of(text, m.start()))
    if "P05" not in disabled:
        for sec_name, body, base in _split_sections(text):
            name, sev = RULE_META["P05"]
            if body.count("《") != body.count("》"):
                pos = base + body.find("《") if "《" in body else base
                report.violations.append(Violation(
                    "P05", name, sev, sec_name or "(全文)",
                    _excerpts(pos), "《》数量不相等，请检查配对"))
            else:
                m = re.search(r"《[^《》]*《", body)
                if m:
                    report.violations.append(Violation(
                        "P05", name, sev, sec_name or "(全文)",
                        _excerpts(base + m.start()), "书名号嵌套，请检查"))

    # ── N 组 ──
    if "N02" not in disabled:
        for unit_cn, unit_sym in (("毫米", "mm"), ("厘米", "cm"), ("千克", "kg"),
                                  ("毫升", "mL"), ("兆帕", "MPa"), ("千伏", "kV")):
            has_cn = re.search(rf"\d+\s*{unit_cn}", text)
            has_sym = re.search(rf"\d+\s*{unit_sym}(?![A-Za-z])", text)
            if has_cn and has_sym:
                pos = has_cn.start()
                name, sev = RULE_META["N02"]
                report.violations.append(Violation(
                    "N02", name, sev, _section_of(text, pos), _excerpts(pos),
                    f"\"{unit_cn}\"与\"{unit_sym}\"同篇混用，建议统一为 {unit_sym}"))
                break  # 每对单位只报一次
        # 数值与单位符号间缺空格（多位数/小数一并覆盖；表格行 | 开头豁免）
        for m in re.finditer(
                r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)"
                r"(mm|cm|kg|MPa|kPa|mL|kHz|MHz)(?![A-Za-z])",
                text):
            if _line_of(text, m.start()).lstrip().startswith("|"):
                continue  # 表格内除外
            _hit("N02", m.start(), "数值与单位符号之间加空格（如 45 mm）",
                 _section_of(text, m.start()))
    if "N03" not in disabled:
        for m in re.finditer(
                r"\d+\s*[-–~～至]\s*\d+\s*(个|人|次|天|日|年|种|项|台|件|批)", text):
            _hit("N03", m.start(), "概数宜用汉字（如\"三四个\"）",
                 _section_of(text, m.start()))
    if "N04" not in disabled:
        # 标准号（GB/T 42061-2022 等）中的数字段不属千分位检查范围
        std_spans = [m.span() for m in _STD_TOKEN.finditer(text)]
        for m in re.finditer(r"(?<![\d.,])\d{5,}(?![\d.])", text):
            if any(s <= m.start() < e for s, e in std_spans):
                continue  # 标准号组成部分除外
            line = _line_of(text, m.start())
            if line.lstrip().startswith("|") or "编号" in line:
                continue  # 表格/编号行除外
            _hit("N04", m.start(), "5 位以上数值建议按千分位分节（如 12,000）",
                 _section_of(text, m.start()))

    # ── S 组 ──
    if doc_type in SOP_DOC_TYPES and "S01" not in disabled:
        headings = [t for t, _, _ in _split_sections(text)]
        _check_sop_chapters(headings, report)
    if "S02" not in disabled and _is_record_doc(doc_type):
        _check_record_elements(text, report)
    if "S03" not in disabled:
        _check_numbering(text, report)

    # ── R 组 ──
    if "R01" not in disabled:
        _check_internal_refs(text, report)
    if "R02" not in disabled:
        _check_standard_numbers(text, report, _hit)

    # ── T 组 ──
    if "T01" not in disabled:
        _check_terms(text, report, _hit)

    return text, report


def _section_of(text: str, pos: int) -> str:
    """返回 pos 所在章节标题（最近的 # 标题行）。"""
    head = text[:pos]
    matches = list(re.finditer(r"^#+\s*(.+)$", head, re.M))
    if matches:
        return matches[-1].group(1).strip()
    return "(全文)"


def _modal_profile(text: str) -> Dict[str, int]:
    """M06：应/宜/可/能（含否定式）频次画像。"""
    profile: Dict[str, int] = {}
    for label, words in (("应", ("应", "不应")), ("宜", ("宜", "不宜")),
                         ("可", ("可", "不必")), ("能", ("能", "不能"))):
        n = 0
        for w in words:
            n += len(re.findall(re.escape(w), text))
        profile[label] = n
    return profile


def _check_sop_chapters(headings: List[str], report: LintReport) -> None:
    """S01：程序文件八股六章近义匹配，缺失章清单报 Error。"""
    norm = [re.sub(r"[\s\d.、（）()\-—]", "", h) for h in headings]
    missing = []
    for canon, keys in _SOP_REQUIRED_CHAPTERS:
        found = any(any(k in n for k in keys) for n in norm if n)
        if not found:
            missing.append(canon)
    if missing:
        name, sev = RULE_META["S01"]
        report.violations.append(Violation(
            "S01", name, sev, "(文档结构)", "全文",
            f"缺少章节：{'、'.join(missing)}（程序文件八股六章要求）"))


def _is_record_doc(doc_type: str) -> bool:
    if not doc_type:
        return False
    dt = doc_type.lower()
    return any(k in dt for k in RECORD_DOC_TYPE_KEYWORDS)


def _check_record_elements(text: str, report: LintReport) -> None:
    """S02：记录类文档的可追溯三要素（谁/何时/结果）表头语义匹配。"""
    checks = [
        ("操作人/执行要素", ("操作人", "执行人", "签名", "签字", "操作者", "审核人")),
        ("日期/时间要素", ("日期", "时间", "年月日")),
        ("结果/判定要素", ("结果", "判定", "结论", "实测值", "测量值")),
    ]
    missing = [label for label, keys in checks
               if not any(k in text for k in keys)]
    if missing:
        name, sev = RULE_META["S02"]
        report.violations.append(Violation(
            "S02", name, sev, "(文档结构)", "全文",
            f"缺可追溯要素：{'、'.join(missing)}"))


def _check_numbering(text: str, report: LintReport) -> None:
    """S03：多级编号跳号/重号检测（2.1 之后是 2.3 → Error）。"""
    numbering: List[List[int]] = []
    positions: List[int] = []
    for m in re.finditer(r"^#+\s*(\d+(?:\.\d+)*)[.、\s]", text, re.M):
        numbering.append([int(x) for x in m.group(1).split(".")])
        positions.append(m.start())
    prev: Optional[List[int]] = None
    for nums, pos in zip(numbering, positions):
        if prev is not None:
            # 同级：前级前缀相同且层级相同 → 应 +1
            if len(nums) == len(prev) and nums[:-1] == prev[:-1]:
                if nums[-1] != prev[-1] + 1:
                    name, sev = RULE_META["S03"]
                    report.violations.append(Violation(
                        "S03", name, sev, _section_of(text, pos),
                        _excerpt_at(text, pos),
                        f"编号 {'.'.join(map(str, prev))} 之后是 "
                        f"{'.'.join(map(str, nums))}，不连续"))
        prev = nums


def _excerpt_at(text: str, pos: int) -> str:
    e = text.find("\n", pos)
    frag = text[pos:e if e != -1 else len(text)].strip()
    return (frag[:50] + "…") if len(frag) > 50 else frag


def _line_of(text: str, pos: int) -> str:
    """返回 pos 所在行（不含换行符）。"""
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return text[s:e if e != -1 else len(text)]


# ── R01：内部文件编号登记表 ──
def _load_doc_registry() -> set:
    """加载本项目文档集/知识库登记的 KF 编号（不存在时为空集）。"""
    try:
        if os.path.exists(DOC_REGISTRY_PATH):
            with open(DOC_REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {str(x).strip() for x in data}
            if isinstance(data, dict):
                docs = data.get("documents")
                if isinstance(docs, list):
                    return {str(x).strip() for x in docs}
                return {str(k).strip() for k in data}
    except Exception as e:
        print(f"[cn_norm_lint] 登记表读取失败: {e}")
    return set()


_KF_REF_RE = re.compile(r"KF-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _check_internal_refs(text: str, report: LintReport) -> None:
    registry = _load_doc_registry()
    if not registry:
        return  # 登记表为空（未部署）时 R01 静默跳过，避免全量误报
    seen: set = set()
    for m in _KF_REF_RE.finditer(text):
        ref = m.group(0)
        if ref in seen:
            continue
        seen.add(ref)
        if ref not in registry:
            name, sev = RULE_META["R01"]
            report.violations.append(Violation(
                "R01", name, sev, _section_of(text, m.start()),
                _excerpt_at(text, m.start()),
                f"内部文件编号 {ref} 未在登记表中命中"
                f"（可能指向未生成文档，合法场景，请人工确认）"))


# ── R02：标准号规范化 ──
# 规范形态：GB/T 42061-2022 / YY/T 0664-2021 / ISO 13485:2016 / IEC 62304 等
_STD_CANONICAL = re.compile(
    r"^(GB/T|GB|YY/T|YY|ISO|IEC|IEEE|EN|GB/Z)\s?\d+(?:\.\d+)?[:-]\d{4}$"
    r"|^(GB/T|GB|YY/T|YY|ISO|IEC|IEEE|EN|GB/Z)\s?\d+(?:\.\d+)?$")
_STD_TOKEN = re.compile(
    r"(?:GB/?T|GB/Z|GB|YY/?T|YY|ISO|IEC|IEEE|EN)\s*\d+(?:[.\-—–]\d+)*(?:\s?[:-]\s?\d{4})?",
    re.I)


def _check_standard_numbers(text: str, report: LintReport, _hit) -> None:
    seen: set = set()
    for m in _STD_TOKEN.finditer(text):
        raw = m.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        canon = _normalize_std(raw)
        if canon != raw:
            _hit("R02", m.start(), f"规范写法：{canon}",
                 _section_of(text, m.start()))


def _normalize_std(raw: str) -> str:
    """把变体标准号归一为规范形态。"""
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    # 统一大小写前缀
    upper = s.upper()
    prefix = re.match(r"^(GB/T|GB/Z|GB|YY/T|YY|ISO|IEC|IEEE|EN)", upper)
    if not prefix:
        return raw
    pfx = prefix.group(1)
    rest = s[prefix.end():]
    # 分隔符规范化：年代号用 - ，版本号用 : ；去空格
    rest = rest.strip()
    if not rest:
        return pfx
    year = ""
    m = re.search(r"[:-]\s*(\d{4})$", rest)
    if m:
        year = m.group(1)
        rest = rest[:m.start()]
    rest = re.sub(r"[\s\-—–.]+", "-", rest.strip())
    out = f"{pfx} {rest}"
    if year:
        out += f"-{year}" if pfx.startswith(("GB", "YY", "EN")) else f":{year}"
    return out


# ── T01：术语规范表 ──
_TERM_CACHE: Optional[Dict[str, str]] = None


def load_term_map() -> Dict[str, str]:
    """加载术语规范表（错误写法 → 规范写法）。"""
    global _TERM_CACHE
    if _TERM_CACHE is not None:
        return _TERM_CACHE
    term_map: Dict[str, str] = {}
    try:
        if os.path.exists(CN_NORM_TERMS_PATH):
            with open(CN_NORM_TERMS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("terms"), dict):
                data = data["terms"]
            if isinstance(data, dict):
                term_map = {str(k): str(v) for k, v in data.items()}
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("wrong") and item.get("right"):
                        for w in item["wrong"]:
                            term_map[str(w)] = str(item["right"])
    except Exception as e:
        print(f"[cn_norm_lint] 术语表读取失败: {e}")
    term_map.pop("_说明", None)
    _TERM_CACHE = term_map
    return term_map


def _check_terms(text: str, report: LintReport, _hit) -> None:
    term_map = load_term_map()
    if not term_map:
        return
    for wrong in sorted(term_map, key=len, reverse=True):
        right = term_map[wrong]
        if wrong == right or wrong not in text:
            continue
        start = 0
        while True:
            idx = text.find(wrong, start)
            if idx < 0:
                break
            start = idx + len(wrong)
            # 命中处若已是规范写法的组成部分（如术语 "SO 13485" 命中在
            # "ISO 13485" 内部）则跳过：左右扩展后包含规范写法即视为规范形态
            ext = text[max(0, idx - len(right) - 2): idx + len(wrong) + len(right) + 2]
            if right in ext and right != wrong:
                continue
            _hit("T01", idx, f"术语规范写法：{right}", _section_of(text, idx))
