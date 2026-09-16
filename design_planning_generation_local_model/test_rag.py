"""
RAG 功能测试脚本

测试项目：
1. 依赖导入检查
2. 向量库摄入（ingest）
3. 向量库检索（retrieve）
4. RAG Prompt 构建
5. RAG vs 非 RAG 生成对比
"""

import os
import sys

# 切换到项目目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("RAG 功能测试")
print("=" * 60)


def test_1_imports():
    """1. 测试依赖导入"""
    print("\n## 1. 依赖导入检查")
    print("-" * 40)

    deps = [
        ("chromadb", "chroma"),
        ("sentence_transformers", "SentenceTransformer"),
        ("torch", "torch"),
        ("docx", "Document"),
    ]

    all_ok = True
    for module, classname in deps:
        try:
            __import__(module)
            print(f"  [OK] {module}: OK")
        except ImportError as e:
            print(f"  [X] {module}: FAILED - {e}")
            all_ok = False

    return all_ok


def test_2_ingest(rebuild=True):
    """2. 测试文档摄入"""
    print("\n## 2. 文档摄入测试")
    print("-" * 40)

    if not rebuild:
        # 只检查向量库状态
        try:
            from app.services.rag.vector_store import VectorStore
            vs = VectorStore()
            count = vs.count()
            sources = vs.get_sources()
            print(f"  向量库状态: {count} chunks, {len(sources)} 个来源文件")
            if count == 0:
                print("  [WARN] 向量库为空，需要先运行摄入脚本")
                print("  命令: python -m app.services.rag.ingest --rebuild")
            return count > 0
        except Exception as e:
            print(f"  [X] 向量库检查失败: {e}")
            return False

    try:
        from app.services.rag.ingest import ingest_all
    except ImportError as e:
        print(f"  [X] 摄入模块导入失败: {e}")
        return False

    source_dir = os.path.join(os.path.dirname(__file__), "develop_documents")
    if not os.path.exists(source_dir):
        print(f"  [X] 参考文档目录不存在: {source_dir}")
        return False

    print(f"  参考文档目录: {source_dir}")
    print(f"  重建模式: {rebuild}")
    print("  摄入中，请稍候...")

    result = ingest_all(source_dir=source_dir, collection_name="all", rebuild=rebuild)

    print(f"  处理文档数: {result['processed_docs']}/{result['total_files']}")
    print(f"  生成 chunk 数: {result['total_chunks']}")
    print(f"  向量库总量: {result['vector_store_count']}")

    return result["total_chunks"] > 0


def test_3_retrieve():
    """3. 测试向量库检索"""
    print("\n## 3. 向量库检索测试")
    print("-" * 40)

    try:
        from app.services.rag.vector_store import VectorStore
    except ImportError as e:
        print(f"  [X] VectorStore 导入失败: {e}")
        return False

    vs = VectorStore()
    count = vs.count()
    print(f"  向量库总量: {count} chunks")

    if count == 0:
        print("  [WARN] 向量库为空，跳过检索测试")
        return False

    # 测试不同文档类型的检索
    test_cases = [
        {
            "doc_type": "risk_management_report",
            "query": "胰岛素泵 有源医疗器械 Bluetooth 闭环控制",
            "top_k": 3
        },
        {
            "doc_type": "product_spec",
            "query": "血液透析浓缩物 技术要求 性能指标",
            "top_k": 3
        },
        {
            "doc_type": "instruction",
            "query": "医疗器械 使用说明书 操作步骤",
            "top_k": 3
        },
    ]

    all_ok = True
    for tc in test_cases:
        results = vs.retrieve(
            doc_type=tc["doc_type"],
            query=tc["query"],
            top_k=tc["top_k"],
            similarity_threshold=0.4
        )
        print(f"\n  [{tc['doc_type']}] query: {tc['query']}")
        print(f"    检索到 {len(results)} 个相关段落:")
        for i, r in enumerate(results, 1):
            print(f"    {i}. [{r['similarity']:.3f}] {r['source_file']}")
            print(f"       章节: {r['section_title'] or 'N/A'}")
            print(f"       内容: {r['text'][:80]}...")

        if not results:
            print(f"    [WARN] 未检索到结果（可能是相似度阈值过高）")
            all_ok = False

    return all_ok


def test_4_rag_prompt():
    """4. 测试 RAG Prompt 构建"""
    print("\n## 4. RAG Prompt 构建测试")
    print("-" * 40)

    try:
        from app.services.rag.vector_store import VectorStore
        from app.services.rag.rag_prompt import build_rag_prompt_from_base
    except ImportError as e:
        print(f"  [X] RAG 模块导入失败: {e}")
        return False

    vs = VectorStore()
    chunks = vs.retrieve(
        doc_type="risk_management_report",
        query="胰岛素泵 有源医疗器械 Bluetooth",
        top_k=2,
        similarity_threshold=0.4
    )

    if not chunks:
        print("  [WARN] 向量库为空，跳过 Prompt 构建测试")
        return False

    base_prompt = """产品信息：
- 产品名称：{product_name}
- 产品类型：{product_type}

请生成风险管理报告的以下章节：
## 2.3.1 能量危害
（请在此处填写详细内容）"""

    enhanced = build_rag_prompt_from_base(
        base_prompt=base_prompt,
        doc_type="risk_management_report",
        product_name="胰岛素泵",
        product_type="有源医疗器械",
        product_params="闭环控制",
        retrieved_chunks=chunks
    )

    print(f"  原始 Prompt 长度: {len(base_prompt)} 字符")
    print(f"  增强后 Prompt 长度: {len(enhanced)} 字符")
    print(f"  RAG 上下文注入: {len(chunks)} 个段落")

    # 显示前 500 字符
    print(f"\n  增强 Prompt 前 500 字符:")
    print("  " + "-" * 38)
    for line in enhanced[:500].split("\n"):
        print(f"  {line}")
    print(f"  ...")

    return len(enhanced) > len(base_prompt)


def test_5_rag_vs_normal():
    """5. RAG vs 非 RAG 生成对比（模拟）"""
    print("\n## 5. RAG vs 非 RAG 对比说明")
    print("-" * 40)

    print("""
  本测试需要有效的 MiniMax API Key 才能执行实际 API 调用。

  对比内容：

  【非 RAG 模式】
  - 直接使用 PROMPT_TEMPLATE 生成
  - 模型依靠"记忆"生成内容
  - 详细内容程度依赖模型自身能力
  - 可能出现泛化描述、框架式内容

  【RAG 模式】
  - 注入真实参考文档段落作为上下文
  - 模型"参照"真实范文的详细程度
  - 内容更贴近实际模板质量
  - 标准号引用更准确

  【启用方式】
  service = MiniMaxService(use_rag=True)

  【预期差异】
  - RAG 模式 FMEA 项数更多（≥15 项 vs ~10 项）
  - RAG 模式技术参数更具体
  - RAG 模式表格更完整，少有"（描述）"占位符
    """)

    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        print("  [WARN] MINIMAX_API_KEY 未设置，跳过实际 API 调用测试")
        return False

    print("  [OK] API Key 已配置，可执行实际测试")
    return True


def test_6_api_endpoint():
    """6. 测试 API 端点"""
    print("\n## 6. API 端点测试")
    print("-" * 40)

    import requests as req

    try:
        resp = req.get("http://localhost:8000/api/health", timeout=5)
        print(f"  API 健康检查: {resp.status_code}")
    except Exception as e:
        print(f"  [WARN] API 服务未启动或无法访问: {e}")
        print("  启动服务: python run.py")
        return False

    return True


def main():
    """主测试流程"""
    results = {}

    # 1. 依赖检查（必须通过）
    results["imports"] = test_1_imports()
    if not results["imports"]:
        print("\n[X] 依赖导入失败，请先安装依赖：")
        print("   pip install chromadb==0.4.22 sentence-transformers==2.2.2 torch>=2.0.0")
        return False

    # 2. 摄入测试（检查现有向量库）
    results["ingest_check"] = test_2_ingest(rebuild=False)

    if not results["ingest_check"]:
        answer = input("\n  向量库为空，是否执行首次摄入？（需要几分钟）[y/N]: ")
        if answer.lower() == "y":
            results["ingest"] = test_2_ingest(rebuild=True)
        else:
            results["ingest"] = False
    else:
        results["ingest"] = True

    # 3. 检索测试（需要向量库有数据）
    if results["ingest"]:
        results["retrieve"] = test_3_retrieve()
        results["prompt"] = test_4_rag_prompt()
    else:
        results["retrieve"] = False
        results["prompt"] = False

    # 4. RAG vs 非 RAG 说明
    results["comparison"] = test_5_rag_vs_normal()

    # 5. API 端点（可选）
    try:
        results["api"] = test_6_api_endpoint()
    except Exception:
        results["api"] = False

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    status_map = {True: "[OK] PASS", False: "[X] FAIL", None: "- SKIP"}
    for name, result in results.items():
        status = status_map.get(result, str(result))
        print(f"  {name:20s}: {status}")

    passed = sum(1 for v in results.values() if v is True)
    total = len([v for v in results.values() if v is not None])
    print(f"\n  通过: {passed}/{total}")

    if results.get("ingest") and results.get("retrieve"):
        print("\n  [OK] RAG 功能可用！可以在生成时启用 use_rag=True")
    else:
        print("\n  [WARN] RAG 功能未就绪，请先完成摄入脚本")

    return passed >= 2  # 至少依赖检查和基本功能通过


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
