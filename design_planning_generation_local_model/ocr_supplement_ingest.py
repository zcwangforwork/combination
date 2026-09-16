"""
OCR 补充摄入脚本 - 处理第一次摄入中失败的扫描版 PDF

针对 build_insulin_pump_kb.py 第一次运行中跳过的 383 个扫描版 PDF，
使用 PyMuPDF + Tesseract OCR 提取文本并追加到现有向量库。
"""

import os
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

import chromadb
from chromadb.config import Settings

from app.services.rag.ingest import (
    extract_text_from_file,
    extract_text_from_pdf,
    chunk_text,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_CHUNKS_PER_DOC,
)
from app.services.rag.embedder import Embedder

# 配置
KB_SOURCE_DIR = project_root / "贴敷式胰岛素泵知识库"
VECTOR_DB_DIR = project_root / "chroma_db_insulin_pump"
COLLECTION_NAME = "insulin_pump_kb"

# 子目录 → doc_type 映射
SUBDIR_DOC_TYPE_MAP = {
    "01-医用电气设备安全": "medical_electrical_safety",
    "02-电磁兼容": "emc",
    "03-软件工程与可用性": "software_usability",
    "04-风险管理": "risk_management",
    "05-质量管理体系": "quality_management",
    "06-生物相容性": "biocompatibility",
    "07-无菌包装": "sterile_packaging",
    "08-灭菌": "sterilization",
    "09-标签与制造商信息": "labeling",
    "10-无线共存": "wireless_coexistence",
    "11-临床评价与上市后监管": "clinical_evaluation",
    "12-输液输注与连接件": "infusion_connectors",
    "13-环境可靠性试验与洁净室": "environmental_reliability",
    "14-运输包装验证": "transport_packaging",
    "15-设计验证与统计分析": "design_verification",
    "16-血糖监测与糖尿病相关": "glucose_monitoring",
    "17-有源植入与闭环控制": "active_implant_closed_loop",
    "18-激光与光学安全": "laser_optical_safety",
    "19-GHTF指南": "ghtf_guidelines",
    "20-材料标准": "material_standards",
    "21-产品注册与备案": "product_registration",
    "22-设计开发文档与模板": "design_dev_templates",
    "23-工艺与设备验证": "process_equipment_validation",
    "24-作业指导书": "sop",
    "25-有效期与稳定性": "shelf_life_stability",
}

SKIP_EXTENSIONS = {".pptx", ".ppt", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".zip", ".rar"}


def get_doc_type(file_path: str) -> str:
    """根据文件路径中的子目录名判断文档类型"""
    rel_path = os.path.relpath(file_path, str(KB_SOURCE_DIR))
    for subdir, doc_type in SUBDIR_DOC_TYPE_MAP.items():
        if subdir in rel_path.replace("\\", "/"):
            return doc_type
    return "unknown"


def generate_chunk_id(source_file: str, chunk_index: int) -> str:
    raw = f"{source_file}_{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def main():
    start_time = datetime.now()

    print("=" * 70)
    print("贴敷式胰岛素泵知识库 - OCR 补充摄入")
    print("=" * 70)
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 连接现有 collection，获取已处理的文件列表
    print("\n[1/4] 连接现有向量库...")
    client = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection(COLLECTION_NAME)
    existing_count = collection.count()
    print(f"  现有 chunks: {existing_count}")

    # 获取已处理的源文件
    result = collection.get(include=["metadatas"])
    processed_files = set()
    for meta in result["metadatas"]:
        if meta and meta.get("source_file"):
            processed_files.add(meta["source_file"])
    print(f"  已处理源文件: {len(processed_files)}")

    # 2. 扫描知识库，找出未处理的文件
    print("\n[2/4] 扫描知识库，找出未处理文件...")

    all_files = []
    for root, dirs, files in os.walk(str(KB_SOURCE_DIR)):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith(".") or f.startswith("~$"):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in SKIP_EXTENSIONS:
                continue
            all_files.append(os.path.join(root, f))

    # 筛选未处理的文件
    unprocessed_files = []
    unavailable_files = []
    for f in all_files:
        base_name = os.path.basename(f)
        if base_name not in processed_files:
            if os.path.isfile(f):
                unprocessed_files.append(f)
            else:
                unavailable_files.append(f)

    # 按子目录统计
    subdir_counts = defaultdict(int)
    for f in unprocessed_files:
        rel_path = os.path.relpath(f, str(KB_SOURCE_DIR))
        subdir = rel_path.replace("\\", "/").split("/")[0]
        subdir_counts[subdir] += 1

    print(f"  知识库总文件数: {len(all_files)}")
    print(f"  已处理: {len(processed_files)}")
    print(f"  待处理: {len(unprocessed_files)}")
    if unavailable_files:
        print(f"  文件不可访问: {len(unavailable_files)}")
    print(f"\n待处理文件分布:")
    for subdir, count in sorted(subdir_counts.items()):
        doc_type = SUBDIR_DOC_TYPE_MAP.get(subdir, "unknown")
        print(f"  {subdir} → {doc_type}: {count} 个")

    if not unprocessed_files:
        print("\n所有文件已处理完毕，无需补充摄入。")
        return

    # 3. 初始化 Embedder
    print("\n[3/4] 处理文件并生成向量（OCR 模式）...")

    embedder = Embedder()
    print(f"  嵌入模型: {embedder.model_name} (维度: {embedder.dimensions})")

    total_chunks = 0
    processed_count = 0
    failed_count = 0
    batch_start_time = time.time()

    for idx, file_path in enumerate(sorted(unprocessed_files)):
        rel_path = os.path.relpath(file_path, str(KB_SOURCE_DIR))
        doc_type = get_doc_type(file_path)
        source_file = os.path.basename(file_path)
        ext = os.path.splitext(source_file)[1].lower()

        print(f"\n[{idx + 1}/{len(unprocessed_files)}] {rel_path}")
        print(f"  文档类型: {doc_type} | 格式: {ext}")

        try:
            if ext == ".pdf":
                # 对 PDF 启用 OCR 回退
                paragraphs = extract_text_from_pdf(file_path, enable_ocr=True)
            else:
                paragraphs = extract_text_from_file(file_path)
        except Exception as e:
            print(f"  [失败] 文本提取出错: {e}")
            failed_count += 1
            continue

        if not paragraphs:
            print(f"  [跳过] 仍未能提取到文本内容")
            failed_count += 1
            continue

        chunks = chunk_text(paragraphs, CHUNK_SIZE, CHUNK_OVERLAP)

        if len(chunks) > MAX_CHUNKS_PER_DOC:
            print(f"  [限制] chunk 数量 {len(chunks)} → 截断为 {MAX_CHUNKS_PER_DOC}")
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        if not chunks:
            print(f"  [跳过] 没有有效 chunks")
            failed_count += 1
            continue

        # 准备数据
        ids = []
        docs = []
        metas = []
        texts_for_embed = []

        for i, chunk in enumerate(chunks):
            chunk_id = generate_chunk_id(source_file, i)
            ids.append(chunk_id)
            docs.append(chunk["text"])
            texts_for_embed.append(chunk["text"])
            metas.append({
                "doc_type": doc_type,
                "source_file": source_file,
                "source_subdir": os.path.dirname(rel_path),
                "section_title": chunk.get("section_title", ""),
                "chunk_index": i,
                "ocr": True,  # 标记为 OCR 提取
            })

        # 生成 embeddings
        print(f"  生成 {len(texts_for_embed)} 个 embedding...")
        try:
            embeddings = embedder.encode(texts_for_embed)
        except Exception as e:
            print(f"  [失败] embedding 生成出错: {e}")
            failed_count += 1
            continue

        # 批量写入
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            end_idx = min(i + batch_size, len(ids))
            collection.add(
                ids=ids[i:end_idx],
                documents=docs[i:end_idx],
                metadatas=metas[i:end_idx],
                embeddings=embeddings[i:end_idx],
            )

        total_chunks += len(chunks)
        processed_count += 1

        elapsed = time.time() - batch_start_time
        rate = (idx + 1) / elapsed if elapsed > 0 else 0
        remaining = (len(unprocessed_files) - idx - 1) / rate if rate > 0 else 0
        print(f"  [OK] {len(chunks)} chunks | 耗时 {elapsed:.0f}s | 预计剩余 {remaining:.0f}s")

    # 4. 汇总
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("OCR 补充摄入完成！")
    print("=" * 70)
    print(f"  总文件数: {len(all_files)}")
    print(f"  本次处理: {processed_count}")
    print(f"  本次失败: {failed_count}")
    print(f"  本次新增 chunks: {total_chunks}")
    print(f"  Collection 总量: {collection.count()}")
    print(f"  总耗时: {duration:.0f}s ({duration / 60:.1f} 分钟)")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 5. 检索测试
    print("\n" + "=" * 70)
    print("检索测试")
    print("=" * 70)

    test_queries = [
        "胰岛素泵电气安全基本要求",
        "风险管理报告模板",
        "质量管理体系要求",
    ]
    for query in test_queries:
        print(f"\n查询: '{query}'")
        try:
            query_embedding = embedder.encode_single(query)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=2,
                include=["documents", "metadatas", "distances"],
            )
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i]
                    similarity = max(0.0, 1.0 - distance / 2.0)
                    meta = results["metadatas"][0][i] or {}
                    doc_text = results["documents"][0][i][:80].replace("\n", " ")
                    ocr_flag = " [OCR]" if meta.get("ocr") else ""
                    print(f"  [{i + 1}] sim={similarity:.3f} type={meta.get('doc_type', '?')} "
                          f"src={meta.get('source_file', '?')}{ocr_flag}")
                    print(f"       {doc_text}...")
        except Exception as e:
            print(f"  检索失败: {e}")

    print("\n" + "=" * 70)
    print("完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
