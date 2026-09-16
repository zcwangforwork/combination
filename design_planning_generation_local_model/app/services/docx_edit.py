"""docx_edit.py — 段落级手术：在原 docx 上执行「删除/替换/插入」编辑指令。

用于「修改/精简/补全上传文档」功能。LLM 基于原文档的块清单（带序号）输出编辑指令
JSON，本模块在原 docx 上执行这些指令——只改动被指令命中的块，其余段落与表格（含其
字体、字号、对齐、缩进等样式）原样保留，避免从 Markdown 重新排版导致的样式丢失。

编辑指令协议（ops 为 list[dict]）：
    {"op": "delete", "block": int}                    # 删除第 block 块
    {"op": "replace", "block": int, "text": str}      # 用 text 替换第 block 块的文字（段落保留样式）
    {"op": "insert_after", "block": int, "text": str} # 在第 block 块之后插入新段落

block 为 1-based 块序号，与 build_block_inventory 输出中的 [n] 一一对应。
"""
from __future__ import annotations

import copy
from typing import List, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

_P_TAG = qn('w:p')
_TBL_TAG = qn('w:tbl')
_TR_TAG = qn('w:tr')
_TC_TAG = qn('w:tc')
_R_TAG = qn('w:r')
_T_TAG = qn('w:t')
_RPR_TAG = qn('w:rPr')
_PPR_TAG = qn('w:pPr')


def iter_body_blocks(doc: Document) -> list:
    """返回 docx body 的顶层块元素列表（仅 w:p 段落与 w:tbl 表格，按文档顺序）。

    段落级手术的「块序号」由本函数决定；块清单生成与指令执行必须共用本函数，
    保证 LLM 看到的序号与执行器定位到的块一一对应。
    """
    body = doc.element.body
    blocks = []
    for child in body.iterchildren():
        if child.tag in (_P_TAG, _TBL_TAG):
            blocks.append(child)
    return blocks


def _element_text(el) -> str:
    """取任意元素内所有 w:t 文本拼接（段落/表格通用）。"""
    return "".join(t.text or "" for t in el.iter(_T_TAG))


def table_text(tbl_el) -> str:
    """取表格元素的可读文本：每行「单元格1 | 单元格2」，行间换行。"""
    lines = []
    for tr in tbl_el.findall(_TR_TAG):
        cells = []
        for tc in tr.findall(_TC_TAG):
            cells.append(_element_text(tc))
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def build_block_inventory(doc: Document, max_block_chars: int = 500) -> str:
    """生成带序号的块清单文本，供 LLM 判断哪些块需要删除/替换/插入。

    表格块标注 [表格]，其内部行换行展示。超长块截断并标注原长度（对定位足够）。
    """
    lines = []
    for i, blk in enumerate(iter_body_blocks(doc), start=1):
        if blk.tag == _TBL_TAG:
            text = "[表格]\n" + table_text(blk)
        else:
            text = _element_text(blk)
        if len(text) > max_block_chars:
            text = text[:max_block_chars] + f"……(共{len(text)}字，已截断)"
        lines.append(f"[{i}] {text}")
    return "\n\n".join(lines)


def inventory_text_from_path(docx_path: str) -> str:
    """打开 docx 文件并返回块清单文本（供 LLM 生成编辑指令参考）。"""
    return build_block_inventory(Document(docx_path))


def _replace_paragraph_text(p_el, text: str) -> None:
    """替换段落文字，保留段落样式：选中一个样式载体 run，只改其文字、删除其余 run。"""
    runs = p_el.findall(_R_TAG)
    if runs:
        # 样式载体：优先取第一个非空文本的 run，其次取第一个 run
        style_run = None
        for r in runs:
            if _element_text(r).strip():
                style_run = r
                break
        if style_run is None:
            style_run = runs[0]
        # 删除其余 run
        for r in runs:
            if r is not style_run:
                p_el.remove(r)
        # 清空 style_run 内除 rPr 之外的子元素（w:t / w:br / w:drawing 等），保留样式属性
        for child in list(style_run):
            if child.tag != _RPR_TAG:
                style_run.remove(child)
        t = OxmlElement('w:t')
        t.set(qn('xml:space'), 'preserve')
        t.text = text
        style_run.append(t)
    else:
        r = OxmlElement('w:r')
        t = OxmlElement('w:t')
        t.set(qn('xml:space'), 'preserve')
        t.text = text
        r.append(t)
        p_el.append(r)


def _insert_paragraph_after(anchor_el, text: str) -> None:
    """在指定块之后插入新段落；若锚定块是段落则复制其 pPr 以保持段样式一致。"""
    new_p = OxmlElement('w:p')
    if anchor_el.tag == _P_TAG:
        ppr = anchor_el.find(_PPR_TAG)
        if ppr is not None:
            new_p.append(copy.deepcopy(ppr))
    r = OxmlElement('w:r')
    t = OxmlElement('w:t')
    t.set(qn('xml:space'), 'preserve')
    t.text = text
    r.append(t)
    new_p.append(r)
    anchor_el.addnext(new_p)


def _replace_table_with_paragraphs(tbl_el, text: str) -> None:
    """兜底：把表格替换为若干普通段落（每行一段）。表格逐格样式无法保留，仅保守兜底。"""
    paras = [ln for ln in text.split("\n") if ln.strip()] or [text]
    prev = tbl_el
    for ln in paras:
        new_p = OxmlElement('w:p')
        r = OxmlElement('w:r')
        t = OxmlElement('w:t')
        t.set(qn('xml:space'), 'preserve')
        t.text = ln
        r.append(t)
        new_p.append(r)
        prev.addnext(new_p)
        prev = new_p
    tbl_el.getparent().remove(tbl_el)


def apply_edit_ops(doc: Document, ops: List[dict]) -> dict:
    """在原 docx 上执行编辑指令列表，返回执行统计。

    先处理 replace / insert，最后统一执行 delete，避免「先删除再操作同一块」失联。
    """
    blocks = iter_body_blocks(doc)
    n = len(blocks)

    def _resolve(idx) -> Optional:
        if isinstance(idx, int) and 1 <= idx <= n:
            return blocks[idx - 1]
        return None

    stats = {"deleted": 0, "replaced": 0, "inserted": 0, "skipped": 0}
    delete_targets = []

    for op in ops or []:
        if not isinstance(op, dict):
            stats["skipped"] += 1
            continue
        kind = op.get("op")
        try:
            block_no = int(op.get("block"))
        except (TypeError, ValueError):
            block_no = 0
        el = _resolve(block_no)
        alive = el is not None and el.getparent() is not None

        if kind == "delete":
            if alive:
                delete_targets.append(el)
                stats["deleted"] += 1
            else:
                stats["skipped"] += 1
        elif kind == "replace":
            text = str(op.get("text", ""))
            if alive and el.tag == _P_TAG:
                _replace_paragraph_text(el, text)
                stats["replaced"] += 1
            elif alive and el.tag == _TBL_TAG:
                _replace_table_with_paragraphs(el, text)
                stats["replaced"] += 1
            else:
                stats["skipped"] += 1
        elif kind == "insert_after":
            text = str(op.get("text", ""))
            if alive:
                _insert_paragraph_after(el, text)
                stats["inserted"] += 1
            else:
                stats["skipped"] += 1
        else:
            stats["skipped"] += 1

    for el in delete_targets:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    return stats
