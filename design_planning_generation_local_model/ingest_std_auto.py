"""
非交互式脚本：摄入医械标准库到知识库
"""

import os
import sys
from pathlib import Path
import time

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.rag.ingest import ingest_document, get_supported_files, extract_text_from_file
from app.services.rag.vector_store import VectorStore


def main():
    start_time = time.time()
    print("=" * 60)
    print("医械标准库知识库摄入工具 (非交互式)")
    print("=" * 60)

    # 医械标准库目录
    std_dir = project_root / "医械标准库"

    if not std_dir.exists():
        print(f"目录不存在: {std_dir}")
        return

    print(f"\n处理目录: {std_dir}")

    # 获取支持的文件
    files = get_supported_files(str(std_dir))
    if not files:
        print("没有找到支持的文件")
        return

    print(f"发现 {len(files)} 个文件\n")

    # 初始化向量库
    vector_store = VectorStore(collection_name="all")

    total_chunks = 0
    total_docs = 0
    failed_docs = []

    # 按子目录分组，便于显示进度
    for i, file_path in enumerate(sorted(files)):
        filename = os.path.basename(file_path)

        # 每100个文件显示一次进度
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"[进度] {i + 1}/{len(files)} 文件已处理，当前速度: {i/elapsed:.1f} 文件/秒")

        try:
            # 使用 force_doc_type 为 "standard"
            chunks_added = ingest_document(
                file_path=file_path,
                vector_store=vector_store,
                force_doc_type="standard"
            )
            if chunks_added > 0:
                total_docs += 1
                total_chunks += chunks_added
            else:
                failed_docs.append((filename, "空文档或读取失败"))
        except Exception as e:
            failed_docs.append((filename, str(e)))

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("摄入完成!")
    print(f"  总文件数: {len(files)}")
    print(f"  成功处理: {total_docs}")
    print(f"  生成Chunks: {total_chunks}")
    print(f"  失败文件: {len(failed_docs)}")
    print(f"  向量库总量: {vector_store.count()}")
    print(f"  总耗时: {elapsed:.1f} 秒")

    if failed_docs:
        print(f"\n失败文件列表 (前20个):")
        for fname, err in failed_docs[:20]:
            print(f"  - {fname}: {err}")

    # 输出向量库来源文件统计
    sources = vector_store.get_sources()
    std_sources = [s for s in sources if "医械标准库" in s or "standard" in s.lower()]
    print(f"\n向量库中来自医械标准库的文件数: {len(std_sources)}")


if __name__ == "__main__":
    main()
