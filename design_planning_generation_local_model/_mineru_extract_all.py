# -*- coding: utf-8 -*-
"""Extract all 4 reference PDFs to markdown using local MinerU model."""
import sys, os, io, time

LOG = r"E:\A_nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model\_mineru_extract_log.txt"
sys.stdout = open(LOG, "w", encoding="utf-8")
sys.stderr = sys.stdout

MODEL_PATH = r"E:\model\MinerU2.5-Pro-2605-1.2B"
BASE = r"e:\A_documents_inside\0729"
OUT_DIR = r"E:\A_nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model"

FILES = {
    "软件配置管理计划": "KF-GS1 Plus-2-0007 软件配置管理计划 A0.pdf",
    "用户需求": "KF-GS1 Plus-1-0001 用户需求 V1.2.pdf",
    "项目计划书": "KF-GS1 Plus-1-0002 项目计划书 A1.pdf",
    "设计输入": "KF-CGM-2-0004 设计输入 V7.0.pdf",
}

def log(*a):
    print(*a, flush=True)

log("=== loading model ===")
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
model = Qwen2VLForConditionalGeneration.from_pretrained(MODEL_PATH, dtype="auto", device_map="auto")
processor = AutoProcessor.from_pretrained(MODEL_PATH, use_fast=True)
from mineru_vl_utils import MinerUClient
client = MinerUClient(backend="transformers", model=model, processor=processor, image_analysis=False)
log("=== model loaded ===")

import fitz
from PIL import Image
from mineru_vl_utils.post_process import json2md

for name, fn in FILES.items():
    pdf = os.path.join(BASE, fn)
    out = os.path.join(OUT_DIR, f"_mineru_{name}.md")
    log(f"=== START {name}: {fn} ===")
    doc = fitz.open(pdf)
    parts = []
    for pno in range(doc.page_count):
        page = doc[pno]
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        t0 = time.time()
        try:
            result = client.two_step_extract(img)
            md = json2md(result)
            parts.append(f"\n\n========== 第 {pno+1} 页 ==========\n\n{md}")
            log(f"  page {pno+1}/{doc.page_count} done in {time.time()-t0:.1f}s, {len(md)} chars")
        except Exception as e:
            parts.append(f"\n\n========== 第 {pno+1} 页 ==========\n\n[解析失败: {e}]")
            log(f"  page {pno+1} FAILED: {e}")
    doc.close()
    full = "".join(parts)
    with open(out, "w", encoding="utf-8") as f:
        f.write(full)
    log(f"=== DONE {name} -> {out} ({len(full)} chars) ===")

log("=== ALL DONE ===")
