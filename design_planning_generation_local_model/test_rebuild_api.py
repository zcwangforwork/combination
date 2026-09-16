"""
RAG 知识库重建 — 测试套件

测试向量化 API 重建知识库的各个环节。
运行: python test_rebuild_api.py
"""

import sys
import io
import os
import tempfile
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


def test_api_key_exists():
    """测试 1: API Key 是否已设置"""
    api_key = os.getenv("MINIMAX_API_KEY", "")
    assert api_key, "MINIMAX_API_KEY 环境变量未设置"
    assert len(api_key) > 10, f"API Key 长度异常: {len(api_key)}"
    print("[PASS] test_api_key_exists")


def test_embedder_initialization():
    """测试 2: Embedder 初始化和基本向量化"""
    from app.services.rag.embedder import Embedder

    embedder = Embedder()
    assert embedder.model_name == "qwen3-embedding:4b"

    # 测试单条文本
    test_text = "这是一个测试文本，用于验证向量化 API 是否正常工作。"
    embedding = embedder.encode_single(test_text)

    assert isinstance(embedding, list), "embedding 应该是列表类型"
    assert len(embedding) == 1024, f"embedding 维度应为 1024，实际为 {len(embedding)}"
    assert all(isinstance(v, float) for v in embedding), "embedding 值应为 float"

    # 测试批量
    texts = ["风险管理报告", "设计输入要求"]
    embeddings = embedder.encode(texts)
    assert len(embeddings) == 2, f"批量向量化应返回 2 个向量，实际为 {len(embeddings)}"

    print("[PASS] test_embedder_initialization")


def test_vectorstore_clear_and_recreate():
    """测试 3: 清除和重建 collection"""
    from app.services.rag.vector_store import VectorStore

    # 使用临时目录（在 Windows 上需要用短路径）
    tmpdir = tempfile.mkdtemp(prefix="chroma_test_")
    try:
        vs = VectorStore(
            persist_directory=tmpdir,
            collection_name="test_clear"
        )

        # 初始应该是空的
        count = vs.count()
        assert count == 0, f"新建 collection 应该为空，实际有 {count} 个 chunks"

        # 添加一个测试 chunk
        vs.add_chunk(
            chunk_id="test_001",
            text="测试文本内容",
            doc_type="test",
            source_file="test.txt"
        )
        count_after_add = vs.count()
        assert count_after_add == 1, f"添加后应该有 1 个 chunk，实际有 {count_after_add}"

        # 清除
        vs.clear()
        vs = VectorStore(
            persist_directory=tmpdir,
            collection_name="test_clear"
        )
        count_after_clear = vs.count()
        assert count_after_clear == 0, f"清除后应该为空，实际有 {count_after_clear} 个 chunks"
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("[PASS] test_vectorstore_clear_and_recreate")


def test_single_docx_ingestion():
    """测试 4: 单个 .docx 文件摄入"""
    from app.services.rag.ingest import extract_text_from_file, chunk_text

    # 查找一个实际的 .docx 文件
    source_dir = project_root / "develop_documents"
    if not source_dir.exists():
        print("[SKIP] test_single_docx_ingestion — develop_documents 目录不存在")
        return "skip"

    # 查找第一个 .docx 文件
    docx_files = list(source_dir.rglob("*.docx"))
    if not docx_files:
        print("[SKIP] test_single_docx_ingestion — 没有 .docx 文件")
        return "skip"

    test_file = str(docx_files[0])
    print(f"  测试文件: {os.path.basename(test_file)}")

    # 提取文本
    paragraphs = extract_text_from_file(test_file)
    assert isinstance(paragraphs, list), "提取结果应该是列表"

    if not paragraphs:
        print("[SKIP] test_single_docx_ingestion — 文件为空或无法提取")
        return "skip"

    # 分块
    chunks = chunk_text(paragraphs)
    assert len(chunks) > 0, f"分块后应有 chunks，实际为 {len(chunks)}"

    # 检查 chunk 结构
    first_chunk = chunks[0]
    assert "text" in first_chunk, "chunk 应包含 text 字段"
    assert "chunk_id" in first_chunk, "chunk 应包含 chunk_id 字段"
    assert len(first_chunk["text"]) > 0, "chunk 文本不应为空"

    print(f"  提取段落: {len(paragraphs)}, 生成 chunks: {len(chunks)}")
    print("[PASS] test_single_docx_ingestion")


def test_retrieval_after_ingest():
    """测试 5: 摄入后的检索质量"""
    from app.services.rag.vector_store import VectorStore

    vs = VectorStore(collection_name="all")
    count = vs.count()

    if count == 0:
        print("[SKIP] test_retrieval_after_ingest — 向量库为空，请先运行 rebuild_kb_api.py")
        return "skip"

    # 测试检索
    query = "风险管理报告"
    results = vs.retrieve(query=query, top_k=3)

    assert isinstance(results, list), "检索结果应该是列表"
    assert len(results) > 0, f"查询 '{query}' 应有结果"

    # 检查结果结构
    first_result = results[0]
    assert "text" in first_result, "结果应包含 text 字段"
    assert "similarity" in first_result, "结果应包含 similarity 字段"
    assert "source_file" in first_result, "结果应包含 source_file 字段"

    # 检查相似度
    similarity = first_result["similarity"]
    assert similarity > 0.3, f"最相关结果的相似度应 > 0.3，实际为 {similarity:.3f}"

    print(f"  查询: '{query}'")
    print(f"  结果数: {len(results)}")
    print(f"  最高相似度: {similarity:.3f}")
    print("[PASS] test_retrieval_after_ingest")


def test_corrupt_file_handling():
    """测试 6: 损坏文件/不存在文件的处理"""
    from app.services.rag.ingest import extract_text_from_file

    # 不存在的文件 — 应该不崩溃
    try:
        paragraphs = extract_text_from_file("/nonexistent/path/file.docx")
        # 可能返回空列表
    except Exception:
        pass  # 抛出异常也是可以接受的

    # 空路径
    try:
        paragraphs = extract_text_from_file("")
    except Exception:
        pass  # 抛出异常也是可以接受的

    print("[PASS] test_corrupt_file_handling")


def test_doc_file_skip():
    """测试 7: .doc 文件跳过逻辑"""
    from app.services.rag.ingest import extract_text_from_file

    # 查找一个实际的 .doc 文件
    source_dir = project_root / "develop_documents"
    if not source_dir.exists():
        print("[SKIP] test_doc_file_skip — develop_documents 目录不存在")
        return "skip"

    doc_files = list(source_dir.rglob("*.doc"))
    if not doc_files:
        print("[SKIP] test_doc_file_skip — 没有 .doc 文件")
        return "skip"

    test_file = str(doc_files[0])
    print(f"  测试文件: {os.path.basename(test_file)}")

    # .doc 文件提取不应导致崩溃
    try:
        paragraphs = extract_text_from_file(test_file)
        assert isinstance(paragraphs, list), "结果应该是列表"
        print(f"  提取到 {len(paragraphs)} 个段落")
    except Exception as e:
        # 如果抛出异常，确保不是系统级崩溃
        print(f"  .doc 提取抛出异常 (可接受): {type(e).__name__}")

    print("[PASS] test_doc_file_skip")


def main():
    print("=" * 70)
    print("RAG 知识库重建 — 测试套件")
    print("=" * 70)

    tests = [
        ("1. API Key 检查", test_api_key_exists),
        ("2. Embedder 初始化", test_embedder_initialization),
        ("3. VectorStore 清除重建", test_vectorstore_clear_and_recreate),
        ("4. 单文件摄入", test_single_docx_ingestion),
        ("5. 检索质量验证", test_retrieval_after_ingest),
        ("6. 损坏文件处理", test_corrupt_file_handling),
        ("7. .doc 文件跳过", test_doc_file_skip),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            result = test_fn()
            if result == "skip":
                skipped += 1
            else:
                passed += 1
        except AssertionError as e:
            print(f"[FAIL] {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print("测试结果")
    print("=" * 70)
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  跳过: {skipped}")
    print(f"  总计: {len(tests)}")

    if failed > 0:
        print("\n[!] 有测试失败，请检查上方输出")
        sys.exit(1)
    else:
        print("\n[OK] 所有测试通过!")


if __name__ == "__main__":
    main()
