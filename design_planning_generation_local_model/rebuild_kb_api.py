"""
RAG 知识库重建脚本 — 使用火山方舟向量化 API

清除旧的本地模型向量（384维），使用 API 向量化（1024维）重新摄入
develop_documents/ 目录下的所有文档。

用法:
    python rebuild_kb_api.py
"""

import sys
import os
import time
from pathlib import Path

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


def main():
    start_time = time.time()

    print("=" * 70)
    print("RAG 知识库重建 — 使用向量化 API")
    print("=" * 70)

    # 1. 前置检查：API Key
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        print("\n[错误] 未设置 MINIMAX_API_KEY 环境变量")
        print("  请在 .env 文件中设置 API Key")
        sys.exit(1)
    print(f"\n[OK] API Key 已设置 (前10位: {api_key[:10]}...)")

    # 2. 源目录检查
    source_dir = project_root / "develop_documents"
    if not source_dir.exists():
        print(f"\n[错误] 文档目录不存在: {source_dir}")
        sys.exit(1)
    print(f"[OK] 文档目录: {source_dir}")

    # 3. 初始化 VectorStore
    print("\n[初始化] VectorStore...")
    vs = VectorStore(collection_name="all")
    old_count = vs.count()
    print(f"[OK] 当前 collection '{vs.collection_name}' 中有 {old_count} 个 chunks")

    # 4. 清除旧 collection（维度不兼容，必须重建）
    print("\n[清除] 删除旧 collection（384维 → 1024维，不兼容）...")
    vs.clear()
    # 重新初始化（clear 会删除 collection，需要重新创建）
    vs = VectorStore(collection_name="all")
    print(f"[OK] 旧 collection 已清除，当前 chunks: {vs.count()}")

    # 5. 扫描文件
    print("\n[扫描] 搜索支持的文件...")
    supported_files = get_supported_files(str(source_dir))
    print(f"[OK] 找到 {len(supported_files)} 个文件")

    # 按扩展名统计
    ext_stats = {}
    for f in supported_files:
        ext = os.path.splitext(f)[1].lower()
        ext_stats[ext] = ext_stats.get(ext, 0) + 1
    print("  文件类型分布:")
    for ext, count in sorted(ext_stats.items()):
        print(f"    {ext}: {count}")

    # 6. 逐文件摄入
    print(f"\n[摄入] 开始处理...")
    print("-" * 70)

    total_chunks = 0
    total_docs = 0
    failed_docs = []
    empty_docs = []
    skipped_doc = 0

    for i, file_path in enumerate(supported_files):
        filename = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        # 跳过 .doc 文件（textract 在 Windows 上难以安装）
        if ext == '.doc':
            skipped_doc += 1
            if skipped_doc <= 5:
                print(f"  [跳过] {filename} (.doc 文件暂不支持)")
            elif skipped_doc == 6:
                print(f"  [跳过] ... 还有更多 .doc 文件被跳过")
            continue

        # 进度报告
        if (i + 1) % 10 == 0 or (i + 1) == len(supported_files):
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"[进度] {i + 1}/{len(supported_files)} "
                  f"({speed:.1f} 文件/秒, "
                  f"成功:{total_docs} chunks:{total_chunks} "
                  f"失败:{len(failed_docs)} 空:{len(empty_docs)} "
                  f"跳过:.doc:{skipped_doc})")

        try:
            chunks_added = ingest_document(
                file_path=file_path,
                vector_store=vs
            )
            if chunks_added > 0:
                total_docs += 1
                total_chunks += chunks_added
            else:
                empty_docs.append(filename)
        except Exception as e:
            failed_docs.append((filename, str(e)))
            if len(failed_docs) <= 10:
                print(f"  [失败] {filename}: {str(e)[:100]}")

    elapsed = time.time() - start_time

    # 7. 汇总报告
    print("\n" + "=" * 70)
    print("知识库重建完成!")
    print("=" * 70)
    print(f"  扫描文件总数: {len(supported_files)}")
    print(f"  跳过 (.doc): {skipped_doc}")
    print(f"  成功摄入: {total_docs}")
    print(f"  生成 Chunks: {total_chunks}")
    print(f"  空文档: {len(empty_docs)}")
    print(f"  失败文件: {len(failed_docs)}")
    print(f"  向量库总量: {vs.count()}")
    print(f"  总耗时: {elapsed:.1f} 秒")

    if empty_docs:
        print(f"\n空文档列表 (前20个):")
        for f in empty_docs[:20]:
            print(f"  - {f}")

    if failed_docs:
        print(f"\n失败文件列表 (前20个):")
        for fname, err in failed_docs[:20]:
            print(f"  - {fname}: {err[:100]}")

    # 8. 验证检索
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

    print("\n" + "=" * 70)
    print("完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
