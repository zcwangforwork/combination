"""
增量摄入脚本：仅摄入向量库中缺失的医械标准库文件
"""

import os
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.rag.ingest import (
    get_supported_files, extract_text_from_file, chunk_text,
    generate_chunk_id, ingest_document
)
from app.services.rag.vector_store import VectorStore


def main():
    start_time = time.time()
    print("=" * 60)
    print("医械标准库 增量摄入工具")
    print("=" * 60)

    std_dir = project_root / "医械标准库"
    if not std_dir.exists():
        print(f"目录不存在: {std_dir}")
        return

    # 1. 获取磁盘上所有支持的文件
    files_on_disk = get_supported_files(str(std_dir))
    print(f"\n磁盘文件总数: {len(files_on_disk)}")

    # 2. 获取向量库中已有的来源文件
    vs = VectorStore(collection_name="all")
    existing_sources = set(vs.get_sources())
    print(f"向量库已有来源文件数: {len(existing_sources)}")
    print(f"向量库当前chunk数: {vs.count()}")

    # 3. 筛选缺失文件（按 basename 匹配）
    missing_files = []
    for f in sorted(files_on_disk):
        basename = os.path.basename(f)
        if basename not in existing_sources:
            missing_files.append(f)

    print(f"\n需要摄入的缺失文件数: {len(missing_files)}")

    if not missing_files:
        print("所有文件已摄入，无需操作。")
        return

    # 按子目录分组统计
    subdir_missing = {}
    for f in missing_files:
        rel = os.path.relpath(f, std_dir)
        parts = rel.replace("\\", "/").split("/")
        subdir = parts[0] if len(parts) > 1 else "ROOT"
        subdir_missing.setdefault(subdir, []).append(f)

    print("\n各子目录缺失文件数:")
    for subdir in sorted(subdir_missing.keys()):
        print(f"  {subdir}: {len(subdir_missing[subdir])}")

    print(f"\n开始增量摄入...")

    total_chunks = 0
    total_docs = 0
    failed_docs = []
    empty_docs = []

    for i, file_path in enumerate(missing_files):
        filename = os.path.basename(file_path)

        # 每50个文件显示一次进度
        if (i + 1) % 50 == 0 or (i + 1) == len(missing_files):
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"[进度] {i + 1}/{len(missing_files)} "
                  f"({speed:.1f} 文件/秒, "
                  f"成功:{total_docs} chunks:{total_chunks} 失败:{len(failed_docs)} 空:{len(empty_docs)})")

        try:
            chunks_added = ingest_document(
                file_path=file_path,
                vector_store=vs,
                force_doc_type="standard"
            )
            if chunks_added > 0:
                total_docs += 1
                total_chunks += chunks_added
            else:
                empty_docs.append(filename)
        except Exception as e:
            failed_docs.append((filename, str(e)))

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("增量摄入完成!")
    print(f"  缺失文件数: {len(missing_files)}")
    print(f"  成功摄入: {total_docs}")
    print(f"  生成Chunks: {total_chunks}")
    print(f"  空文档: {len(empty_docs)}")
    print(f"  失败文件: {len(failed_docs)}")
    print(f"  向量库总量: {vs.count()}")
    print(f"  向量库来源文件数: {len(vs.get_sources())}")
    print(f"  总耗时: {elapsed:.1f} 秒")

    if empty_docs:
        print(f"\n空文档列表 (前20个):")
        for f in empty_docs[:20]:
            print(f"  - {f}")

    if failed_docs:
        print(f"\n失败文件列表 (前20个):")
        for fname, err in failed_docs[:20]:
            print(f"  - {fname}: {err[:100]}")


if __name__ == "__main__":
    main()
