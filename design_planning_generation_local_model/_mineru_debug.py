# -*- coding: utf-8 -*-
"""Debug MinerU two_step_extract on a single scanned page."""
import sys, os, io, time

OUT = r"E:\A_nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model\_mineru_debug.txt"
sys.stdout = open(OUT, "w", encoding="utf-8")
sys.stderr = sys.stdout

MODEL_PATH = r"E:\model\MinerU2.5-Pro-2605-1.2B"
PDF = r"e:\A_documents_inside\0729\KF-GS1 Plus-2-0007 软件配置管理计划 A0.pdf"

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
doc = fitz.open(PDF)
page = doc[0]
pix = page.get_pixmap(dpi=200)
img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
log("=== page1 image size:", img.size, "===")

t0 = time.time()
result = client.two_step_extract(img)
log("=== two_step_extract done in %.1fs, result type=%s len=%d ===" % (time.time()-t0, type(result).__name__, len(result)))

for i, blk in enumerate(result):
    log("block[%d]: type=%r content=%r" % (i, blk.get("type"), (blk.get("content") or "")[:300]))

from mineru_vl_utils.post_process import json2md
md = json2md(result)
log("=== json2md len=%d ===" % len(md))
log("--- markdown ---")
log(md)
log("=== DONE ===")
