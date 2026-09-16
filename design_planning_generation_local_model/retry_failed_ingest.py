"""
重试因限流失败的文件摄入

使用更长的间隔重新尝试之前因 API 限流 (429) 而失败的文件。

用法:
    python retry_failed_ingest.py
"""

import sys
import io
import os
import time
from pathlib import Path

# 设置 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

from app.services.rag.ingest import (
    get_supported_files, ingest_document
)
from app.services.rag.vector_store import VectorStore


# 之前因限流失败的文件列表
FAILED_FILES = [
    "设计验证及确认报告模板-上海版.docx",
    "PCR实验室SOP文件（模板）.pdf",
    "PCR实验室人员培训和考核记录（模板）.pdf",
    "医疗器械产品包装和标签研究验证报告-9650cc819ace.docx",
    "1-2项目立项及开发输入.docx",
    "2-2设计和开发计划.docx",
    "3-1设计和开发评审记录.docx",
    "3-2设计和开发验证记录和报告.docx",
    "4-5关键和特殊过程清单.docx",
    "BOM表.docx",
    "人员需求.docx",
    "设备需求.docx",
    "医疗器械产品注册资料模板）.pdf",
    "初始污染菌和恢复期实验验证模板）.pdf",
    "包装运输验证报告 - 副本.pdf",
]


def main():
    start_time = time.time()

    print("=" * 70)
    print("重试限流失败的文件")
    print("=" * 70)

    # 初始化 VectorStore
    vs = VectorStore(collection_name="all")
    print(f"当前向量库: {vs.count()} chunks")

    # 获取已有来源文件
    existing_sources = set(vs.get_sources())
    print(f"已有来源文件数: {len(existing_sources)}")

    # 扫描所有文件并匹配失败的
    source_dir = project_root / "develop_documents"
    all_files = get_supported_files(str(source_dir))

    # 构建文件名到路径的映射
    file_map = {}
    for f in all_files:
        basename = os.path.basename(f)
        file_map[basename] = f

    # 找出需要重试的文件
    retry_files = []
    for fname in FAILED_FILES:
        if fname in file_map:
            # 检查是否已经在向量库中
            if fname not in existing_sources:
                retry_files.append(file_map[fname])
            else:
                print(f"  [已存在] {fname}")
        else:
            print(f"  [未找到] {fname}")

    if not retry_files:
        print("\n无需重试的文件。")
        return

    print(f"\n需要重试的文件: {len(retry_files)}")
    print("使用更长间隔（每个 chunk 后等待 0.5 秒）...")
    print("-" * 70)

    total_chunks = 0
    total_docs = 0
    still_failed = []

    for i, file_path in enumerate(retry_files):
        filename = os.path.basename(file_path)
        print(f"\n[{i+1}/{len(retry_files)}] {filename}")

        try:
            chunks_added = ingest_document(
                file_path=file_path,
                vector_store=vs
            )
            if chunks_added > 0:
                total_docs += 1
                total_chunks += chunks_added
                print(f"  [OK] {chunks_added} chunks")
            else:
                print(f"  [空] 无有效文本")
        except Exception as e:
            still_failed.append((filename, str(e)))
            print(f"  [失败] {str(e)[:100]}")

        # 文件间等待更长时间避免限流
        if i + 1 < len(retry_files):
            print("  等待 3 秒...")
            time.sleep(3)

    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("重试完成!")
    print("=" * 70)
    print(f"  重试文件: {len(retry_files)}")
    print(f"  成功: {total_docs}")
    print(f"  新增 Chunks: {total_chunks}")
    print(f"  仍然失败: {len(still_failed)}")
    print(f"  向量库总量: {vs.count()}")
    print(f"  耗时: {elapsed:.1f} 秒")

    if still_failed:
        print("\n仍然失败的文件:")
        for fname, err in still_failed:
            print(f"  - {fname}: {err[:100]}")

    # 验证检索
    print("\n" + "=" * 70)
    print("验证检索质量...")
    print("=" * 70)

    test_queries = [
        "风险管理报告",
        "设计输入要求",
        "产品技术要求",
        "SOP 作业指导书",
    ]

    for query in test_queries:
        print(f"\n查询: '{query}'")
        results = vs.retrieve(query=query, top_k=3)

        if not results:
            print("  [警告] 无检索结果")
            continue

        for j, result in enumerate(results):
            similarity = result.get("similarity", 0)
            source = result.get("source_file", "未知")
            text_preview = result.get("text", "")[:60].replace("\n", " ")
            print(f"  [{j+1}] 相似度: {similarity:.3f} | {source}")
            print(f"      {text_preview}...")


if __name__ == "__main__":
    main()
