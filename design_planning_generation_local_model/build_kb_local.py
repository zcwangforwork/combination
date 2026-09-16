"""
用本地 sentence-transformers 模型建立知识库
不依赖外部 API
"""
import sys
import os
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any
import hashlib

print("=" * 70)
print("本地知识库构建工具")
print("=" * 70)

# 检查 sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    print("\n[OK] sentence-transformers 已安装")
except ImportError:
    print("\n[错误] 需要安装 sentence-transformers:")
    print("  pip install sentence-transformers")
    sys.exit(1)

# 初始化 ChromaDB
base_dir = project_root / "chroma_db"
client = chromadb.PersistentClient(
    path=str(base_dir),
    settings=Settings(anonymized_telemetry=False)
)

collection_name = "qms_doc_all"

# 删除旧 collection（如果存在）
try:
    client.delete_collection(collection_name)
    print(f"\n已删除旧 collection: {collection_name}")
except:
    pass

# 创建新 collection
collection = client.create_collection(
    name=collection_name,
    metadata={'description': 'QMS 医疗器械文档参考库 - 本地模型'}
)

print(f"已创建 collection: {collection_name}")

# 加载本地 embedding 模型
print("\n正在加载本地 embedding 模型 (paraphrase-multilingual-MiniLM-L12-v2)...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
print("[OK] 模型加载完成")

# 文档类型映射
DOC_TYPE_MAPPING = {
    "CH3.2风险管理模板": "risk_management_report",
    "CH5.03包装说明使用说明书": "instruction",
    "产品技术要求模板": "product_spec",
    "软件资料": "software",
    "体系资料": "system_doc",
    "流程图": "flowchart",
    "作业指导书": "sop",
    "设计开发表格": "design_doc",
    "验证": "validation",
    "有效期": "shelf_life",
}

def get_doc_type_from_path(file_path: str) -> str:
    """根据文件路径判断文档类型"""
    for dir_name, doc_type in DOC_TYPE_MAPPING.items():
        if dir_name in file_path.replace("\\", "/"):
            return doc_type
    filename = os.path.basename(file_path).lower()
    if any(keyword in filename for keyword in ["sop", "作业指导", "操作规程"]):
        return "sop"
    if any(keyword in filename for keyword in ["风险", "risk"]):
        return "risk_management_report"
    if any(keyword in filename for keyword in ["说明", "manual"]):
        return "instruction"
    if any(keyword in filename for keyword in ["技术要求", "spec"]):
        return "product_spec"
    return "unknown"

def extract_text_from_docx(docx_path: str) -> List[str]:
    """从 docx 提取文本段落"""
    try:
        from docx import Document
        doc = Document(docx_path)
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text and len(text) > 10:
                paragraphs.append(text)
        return paragraphs
    except Exception as e:
        print(f"    [DOCX 读取失败] {e}")
        return []

def extract_text_from_txt(txt_path: str) -> List[str]:
    """从 txt 提取文本"""
    try:
        encodings = ['utf-8', 'gbk', 'gb18030', 'latin1']
        for enc in encodings:
            try:
                with open(txt_path, 'r', encoding=enc) as f:
                    text = f.read()
                    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 10]
                    return paragraphs
            except UnicodeDecodeError:
                continue
        return []
    except Exception as e:
        print(f"    [TXT 读取失败] {e}")
        return []

def split_chunks(paragraphs: List[str], chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """将段落分割成 chunks"""
    chunks = []
    current_chunk = ""
    current_length = 0

    for para in paragraphs:
        para_len = len(para)
        if current_length + para_len < chunk_size or not current_chunk:
            current_chunk += para + "\n"
            current_length += para_len + 1
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n"
            current_length = para_len + 1

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks

# 扫描文档目录
source_dir = project_root / "develop_documents"
print(f"\n扫描目录: {source_dir}")

if not source_dir.exists():
    print(f"[错误] 目录不存在: {source_dir}")
    sys.exit(1)

# 收集所有支持的文件
supported_files = []
for ext in ['*.docx', '*.txt']:
    supported_files.extend(list(source_dir.rglob(ext)))

print(f"\n找到 {len(supported_files)} 个支持的文件")

# 处理文件
total_chunks = 0
processed_files = 0

for file_path in supported_files:
    rel_path = file_path.relative_to(source_dir)
    print(f"\n[{processed_files+1}/{len(supported_files)}] {rel_path}")

    doc_type = get_doc_type_from_path(str(file_path))
    print(f"  文档类型: {doc_type}")

    paragraphs = []
    if file_path.suffix.lower() == '.docx':
        paragraphs = extract_text_from_docx(str(file_path))
    elif file_path.suffix.lower() == '.txt':
        paragraphs = extract_text_from_txt(str(file_path))

    if not paragraphs:
        print("  跳过: 没有提取到文本")
        continue

    chunks = split_chunks(paragraphs)
    if not chunks:
        print("  跳过: 没有有效 chunks")
        continue

    print(f"  提取到 {len(paragraphs)} 段落, {len(chunks)} chunks")

    # 准备数据
    ids = []
    docs = []
    metas = []
    texts = []

    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{file_path.name}_{i}".encode()).hexdigest()[:16]
        ids.append(chunk_id)
        docs.append(chunk)
        texts.append(chunk)
        metas.append({
            'doc_type': doc_type,
            'source_file': str(rel_path),
            'section_title': '',
            'chunk_index': i
        })

    # 生成 embeddings
    print(f"  正在生成 embeddings...")
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    # 添加到 collection（每批最多100个）
    batch_size = 100
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
    print(f"  ✓ 已添加 {len(chunks)} chunks")

print("\n" + "=" * 70)
print(f"知识库构建完成！")
print("=" * 70)
print(f"  - 处理文件: {processed_files}")
print(f"  - 总 chunks: {total_chunks}")
print(f"  - Collection: {collection_name}")
print(f"  - 当前 collection 中: {collection.count()} chunks")

# 测试检索
print("\n" + "=" * 70)
print("测试检索...")
print("=" * 70)

test_queries = [
    "风险管理报告",
    "设计输入要求",
    "产品技术要求",
    "SOP 作业指导书",
]

for query in test_queries:
    print(f"\n查询: '{query}'")
    query_embedding = model.encode([query]).tolist()[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=3,
        include=["documents", "metadatas", "distances"]
    )

    if results['ids'] and results['ids'][0]:
        for i, doc_id in enumerate(results['ids'][0]):
            distance = results['distances'][0][i]
            similarity = max(0.0, 1.0 - distance / 2.0)
            meta = results['metadatas'][0][i]
            source = meta.get('source_file', 'unknown') if meta else 'unknown'
            doc_text = results['documents'][0][i]
            preview = doc_text[:60].replace('\n', ' ')
            print(f"  [{i+1}] 相似度: {similarity:.3f} | {source}")
            print(f"      {preview}...")

print("\n" + "=" * 70)
print("完成！")
print("=" * 70)
