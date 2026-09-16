"""
构建贴敷式胰岛素泵知识库向量库

将 贴敷式胰岛素泵知识库 目录下的所有文档转化为向量，
存入独立的 ChromaDB 目录 chroma_db_insulin_pump，
供项目 RAG 检索使用。
"""

import os
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

import chromadb
from chromadb.config import Settings

from app.services.rag.ingest import (
    extract_text_from_file,
    chunk_text,
    get_supported_files,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_CHUNKS_PER_DOC,
)
from app.services.rag.embedder import Embedder

# ============================================================
# 配置
# ============================================================

# 知识库源目录
KB_SOURCE_DIR = project_root / "贴敷式胰岛素泵知识库"

# 向量库输出目录（独立于现有的 chroma_db）
VECTOR_DB_DIR = project_root / "chroma_db_insulin_pump"

# Collection 名称
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

# 跳过的文件扩展名（无法提取文本的格式）
SKIP_EXTENSIONS = {'.pptx', '.ppt', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.zip', '.rar'}


def get_doc_type(file_path: str) -> str:
    """根据文件路径中的子目录名判断文档类型"""
    rel_path = os.path.relpath(file_path, str(KB_SOURCE_DIR))
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        subdir = parts[0]
        if subdir in SUBDIR_DOC_TYPE_MAP:
            return SUBDIR_DOC_TYPE_MAP[subdir]
    # 尝试从完整路径匹配
    for subdir, doc_type in SUBDIR_DOC_TYPE_MAP.items():
        if subdir in file_path.replace("\\", "/"):
            return doc_type
    return "unknown"


def generate_chunk_id(source_file: str, chunk_index: int) -> str:
    """生成唯一 chunk ID"""
    raw = f"{source_file}_{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def build_knowledge_base():
    """主函数：构建胰岛素泵知识库向量库"""
    start_time = datetime.now()

    print("=" * 70)
    print("贴敷式胰岛素泵知识库 - 向量库构建工具")
    print("=" * 70)
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"源目录: {KB_SOURCE_DIR}")
    print(f"向量库目录: {VECTOR_DB_DIR}")
    print(f"Collection: {COLLECTION_NAME}")

    if not KB_SOURCE_DIR.exists():
        print(f"\n[错误] 知识库目录不存在: {KB_SOURCE_DIR}")
        sys.exit(1)

    # ----------------------------------------------------------
    # 1. 扫描文件
    # ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("[1/4] 扫描知识库文件...")

    # 获取所有文件
    all_files = []
    for root, dirs, files in os.walk(str(KB_SOURCE_DIR)):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in SKIP_EXTENSIONS:
                continue
            all_files.append(os.path.join(root, f))

    # 统计
    supported_files = []
    skipped_files = []
    for f in all_files:
        ext = os.path.splitext(f)[1].lower()
        if ext in {'.docx', '.pdf', '.doc', '.txt', '.xlsx', '.md'}:
            supported_files.append(f)
        else:
            skipped_files.append(f)

    # 按子目录统计
    from collections import defaultdict
    subdir_counts = defaultdict(int)
    for f in supported_files:
        rel_path = os.path.relpath(f, str(KB_SOURCE_DIR))
        subdir = rel_path.replace("\\", "/").split("/")[0]
        subdir_counts[subdir] += 1

    print(f"  总文件数: {len(all_files)}")
    print(f"  支持的文件: {len(supported_files)}")
    print(f"  跳过的文件: {len(skipped_files)}")
    if skipped_files:
        for f in skipped_files:
            print(f"    [SKIP] {os.path.basename(f)}")

    print("\n各子目录文件数:")
    for subdir, count in sorted(subdir_counts.items()):
        doc_type = SUBDIR_DOC_TYPE_MAP.get(subdir, "unknown")
        print(f"  {subdir} → {doc_type}: {count} 个文件")

    if not supported_files:
        print("\n[错误] 没有找到支持的文件")
        sys.exit(1)

    # ----------------------------------------------------------
    # 2. 初始化 ChromaDB 和 Embedder
    # ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("[2/4] 初始化向量库和嵌入模型...")

    os.makedirs(str(VECTOR_DB_DIR), exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR),
        settings=Settings(anonymized_telemetry=False)
    )

    # 删除旧 collection（如果存在）
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  已删除旧 collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "贴敷式胰岛素泵知识库 - 医疗器械法规标准向量库",
            "source_dir": str(KB_SOURCE_DIR),
            "created_at": start_time.isoformat(),
        }
    )
    print(f"  已创建 collection: {COLLECTION_NAME}")

    embedder = Embedder()
    print(f"  嵌入模型: {embedder.model_name} (维度: {embedder.dimensions})")

    # ----------------------------------------------------------
    # 3. 提取文本、分块、生成向量、写入
    # ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("[3/4] 处理文件并生成向量...")
    print("=" * 70)

    total_chunks = 0
    processed_files = 0
    failed_files = 0
    batch_start_time = time.time()

    for idx, file_path in enumerate(sorted(supported_files)):
        rel_path = os.path.relpath(file_path, str(KB_SOURCE_DIR))
        doc_type = get_doc_type(file_path)
        source_file = os.path.basename(file_path)

        print(f"\n[{idx + 1}/{len(supported_files)}] {rel_path}")
        print(f"  文档类型: {doc_type}")

        try:
            paragraphs = extract_text_from_file(file_path)
        except Exception as e:
            print(f"  [失败] 文本提取出错: {e}")
            failed_files += 1
            continue

        if not paragraphs:
            print(f"  [跳过] 未能提取到文本内容（可能是扫描版 PDF 或加密文档）")
            failed_files += 1
            continue

        chunks = chunk_text(paragraphs, CHUNK_SIZE, CHUNK_OVERLAP)

        if len(chunks) > MAX_CHUNKS_PER_DOC:
            print(f"  [限制] chunk 数量 {len(chunks)} → 截断为 {MAX_CHUNKS_PER_DOC}")
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        if not chunks:
            print(f"  [跳过] 没有有效 chunks")
            failed_files += 1
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
            })

        # 生成 embeddings（逐条调用 API）
        print(f"  生成 {len(texts_for_embed)} 个 embedding...")
        try:
            embeddings = embedder.encode(texts_for_embed)
        except Exception as e:
            print(f"  [失败] embedding 生成出错: {e}")
            failed_files += 1
            continue

        # 批量写入 collection
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            end_idx = min(i + batch_size, len(ids))
            collection.add(
                ids=ids[i:end_idx],
                documents=docs[i:end_idx],
                metadatas=metas[i:end_idx],
                embeddings=embeddings[i:end_idx]
            )

        total_chunks += len(chunks)
        processed_files += 1

        elapsed = time.time() - batch_start_time
        rate = (idx + 1) / elapsed if elapsed > 0 else 0
        remaining = (len(supported_files) - idx - 1) / rate if rate > 0 else 0
        print(f"  [OK] {len(chunks)} chunks | 耗时 {elapsed:.0f}s | 预计剩余 {remaining:.0f}s")

    # ----------------------------------------------------------
    # 4. 汇总
    # ----------------------------------------------------------
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("[4/4] 知识库构建完成！")
    print("=" * 70)
    print(f"  源目录: {KB_SOURCE_DIR}")
    print(f"  向量库目录: {VECTOR_DB_DIR}")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  总文件数: {len(all_files)}")
    print(f"  成功处理: {processed_files}")
    print(f"  失败/跳过: {failed_files}")
    print(f"  总 chunks: {total_chunks}")
    print(f"  Collection 实际数量: {collection.count()}")
    print(f"  总耗时: {duration:.0f}s ({duration / 60:.1f} 分钟)")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ----------------------------------------------------------
    # 5. 输出配置信息（用于更新 VectorStore 查询配置）
    # ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("配置信息（用于 RAG 检索）")
    print("=" * 70)
    print(f"  向量库目录: {VECTOR_DB_DIR}")
    print(f"  Collection 名称: {COLLECTION_NAME}")
    print()
    print("请将以下配置添加到 VectorStore.EXTRA_DB_CONFIG 中：")
    print(f"  EXTRA_DB_CONFIG = {{")
    print(f"      r\"{VECTOR_DB_DIR}\": [\"{COLLECTION_NAME}\"],")
    print(f"  }}")

    # ----------------------------------------------------------
    # 6. 快速检索测试
    # ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("检索测试")
    print("=" * 70)

    test_queries = [
        "胰岛素泵的电气安全要求",
        "风险管理报告模板",
        "电磁兼容测试标准",
        "无菌包装验证",
        "软件生命周期要求",
    ]

    for query in test_queries:
        print(f"\n查询: '{query}'")
        try:
            query_embedding = embedder.encode_single(query)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=3,
                include=["documents", "metadatas", "distances"]
            )
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i]
                    similarity = max(0.0, 1.0 - distance / 2.0)
                    meta = results["metadatas"][0][i] or {}
                    doc_text = results["documents"][0][i][:80].replace("\n", " ")
                    print(f"  [{i + 1}] 相似度: {similarity:.3f} | "
                          f"类型: {meta.get('doc_type', '?')} | "
                          f"来源: {meta.get('source_file', '?')}")
                    print(f"      {doc_text}...")
            else:
                print(f"  无结果")
        except Exception as e:
            print(f"  检索失败: {e}")

    print("\n" + "=" * 70)
    print("完成！")
    print("=" * 70)


if __name__ == "__main__":
    build_knowledge_base()
