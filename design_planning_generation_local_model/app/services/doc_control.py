# -*- coding: utf-8 -*-
"""doc_control —— 受控文件形态底座（方案模块四 + 模块三的依据版本判定）。

职责：
1. 版本升版状态机（§5.1）：minor / major / none 三态，判定优先级
   用户指令 > 关键要素清单 > 默认 minor；
2. 修订记录条目构造（§5.2）：来源枚举（用户指令/审校修复/法规变更/参数变更），
   一句话概述 ≤20 字，修订人/生效日期留空待手填；
3. 编制依据版本判定（§4.6 双轨过渡）：按"文档编制日期 vs 2026-11-01"
   自动选择 64号 / 107号（REG_BASIS_DEFAULT=auto；gmp2014/gmp2025 强制指定）。

纯函数模块，不依赖 LLM 与网络。
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Optional, Tuple

# ── 配置（方案 §9.1）──
REG_BASIS_DEFAULT = os.getenv("REG_BASIS_DEFAULT", "auto")  # auto / gmp2014 / gmp2025
DOC_VERSION_POLICY = os.getenv("DOC_VERSION_POLICY", "kf")  # minor/major 判定规则表（预留多规则）

# 新版 GMP 施行日（2025年第107号公告，2026-11-01 施行并废止 64号）
_GMP2025_EFFECTIVE_DATE = date(2026, 11, 1)

# 修订来源枚举（§5.2 ECN/CR 来源标注）
REV_SOURCE_USER = "用户指令"
REV_SOURCE_REVIEW = "审校修复"
REV_SOURCE_REGULATION = "法规变更"
REV_SOURCE_PARAMETER = "参数变更"

# ── 关键要素清单（major 升版触发词；KF 企业定义待确认项#2 关闭后可外置到规则表）──
_MAJOR_KEYWORDS = re.compile(
    r"关键参数|主要参数|性能指标|技术参数|适用标准|标准清单|安全级别|"
    r"软件安全|结构重构|整体结构|全部重写|推倒重来|重大变更|升大版本|升版为|"
    r"大版本|V\d+\.0|产品型号|预期用途|适用范围变更")

# 仅排版/错字类修改（不升版）触发词
_NONE_KEYWORDS = re.compile(
    r"错字|错别字|笔误|标点|排版|格式|字体|空格|标点符号|错漏字|更正错")


def bump_version(version: str, action: str) -> str:
    """版本号推进：minor V1.0→V1.1；major V1.x→V2.0；none 原样返回。

    Args:
        version: 当前版本号（如 "V1.0"；非法格式按 V1.0 处理）
        action: "minor" / "major" / "none"
    """
    m = re.match(r"^[Vv](\d+)\.(\d+)$", (version or "").strip())
    if not m:
        major, minor = 1, 0
    else:
        major, minor = int(m.group(1)), int(m.group(2))
    if action == "major":
        return f"V{major + 1}.0"
    if action == "minor":
        return f"V{major}.{minor + 1}"
    return f"V{major}.{minor}"


def classify_revision(instruction: str = "") -> Tuple[str, str]:
    """升版动作判定（§5.1 优先级：用户指令 > 关键要素清单 > 默认 minor）。

    Returns:
        (action, source)：action ∈ minor/major/none；
        source ∈ REV_SOURCE_*（供修订记录来源列标注）。
    """
    text = (instruction or "").strip()
    if not text:
        return "none", REV_SOURCE_REVIEW
    # 用户显式指令：要求升版/重大变更 → major
    if _MAJOR_KEYWORDS.search(text):
        return "major", REV_SOURCE_USER
    # 明确的参数/法规类变更（非用户显式升版指令）归入对应来源
    if _NONE_KEYWORDS.search(text):
        return "none", REV_SOURCE_REVIEW
    if re.search(r"参数|规格|数值|阈值|剂量|流速|精度", text):
        return "minor", REV_SOURCE_PARAMETER
    if re.search(r"法规|GMP|公告|标准.*换版|107号|64号", text):
        return "minor", REV_SOURCE_REGULATION
    return "minor", REV_SOURCE_USER


def summarize_revision(instruction: str, limit: int = 20) -> str:
    """从修改指令提取一句话修订概述（≤limit 字，超长截断）。"""
    text = re.sub(r"\s+", " ", (instruction or "").strip())
    if not text:
        return "内容修订"
    # 去掉常见前缀指令词，保留核心描述
    text = re.sub(r"^(请|麻烦|帮我)?(修改|调整|更正|更新|完善|优化)[:：，,\s]*", "", text)
    return text[:limit]


def build_revision_entry(version: str, source: str, summary: str) -> dict:
    """构造修订记录表一行（修订人/生效日期留空，签署时手填——合规设计）。"""
    return {
        "version": version,
        "source": source,          # ECN/CR 来源：用户指令/审校修复/法规变更/参数变更
        "summary": summary or "内容修订",
        "revisor": "",             # 修订人：留空
        "effective_date": "",      # 生效日期：留空
    }


# ══════════════════════════════════════════════════════════════════
# 编制依据版本判定（§4.6 双轨过渡：64号 → 107号）
# ══════════════════════════════════════════════════════════════════
_GMP2014_BASIS = {
    "key": "gmp2014",
    "name": "《医疗器械生产质量管理规范》",
    "announce_no": "国家食药监总局 2014 年第 64 号",
    "structure": "13章84条",
    "status": "现行",
    "note": "2026-11-01 废止",
}

_GMP2025_BASIS = {
    "key": "gmp2025",
    "name": "《医疗器械生产质量管理规范》",
    "announce_no": "2025 年第 107 号",
    "structure": "15章132条",
    "status": "未施行（2026-11-01 施行）",
    "note": "2025-11-04 发布",
}


def get_reg_basis(today: Optional[date] = None,
                  policy: Optional[str] = None) -> dict:
    """返回编制依据信息（封面编制依据行数据源）。

    Args:
        today: 判定基准日（默认今天）
        policy: 覆盖 REG_BASIS_DEFAULT；auto=按日期自动，gmp2014/gmp2025=强制
    """
    mode = (policy or REG_BASIS_DEFAULT or "auto").strip().lower()
    if mode == "gmp2014":
        basis = dict(_GMP2014_BASIS)
    elif mode == "gmp2025":
        basis = dict(_GMP2025_BASIS)
    else:
        d = today or date.today()
        if d >= _GMP2025_EFFECTIVE_DATE:
            basis = dict(_GMP2025_BASIS)
            basis["status"] = "现行"
        else:
            basis = dict(_GMP2014_BASIS)
    # 前瞻性采用标注（§4.6 过渡期标注）
    if basis["key"] == "gmp2025" and "未施行" in basis.get("status", ""):
        basis["cover_line_note"] = "（2026-11-01 施行）"
    else:
        basis["cover_line_note"] = ""
    return basis


def reg_basis_cover_line(today: Optional[date] = None) -> str:
    """封面信息表「编制依据」行文本：法规名+公告号+施行状态（GB/T 42061 常挂）。"""
    b = get_reg_basis(today=today)
    line = (f"{b['name']}（{b['announce_no']}，{b['status']}）、"
            f"GB/T 42061-2022《医疗器械质量管理体系 用于法规的要求》")
    if b.get("cover_line_note"):
        line += b["cover_line_note"]
    return line
