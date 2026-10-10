"""
VectorStore - ChromaDB 向量存储封装

提供文档摄入和语义检索功能。
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict

import chromadb
from chromadb.config import Settings

from app.services.rag.embedder import Embedder
from app.services.rag.tokenizer import get_tokenizer

# 延迟导入
_chroma_client = None

# RRF 融合权重（向量路 / BM25 路）。模块常量便于评测网格搜索与运行期调参；
# 取值依据见 retrieve_hybrid 内注释与 evals/reports 评测记录。
RRF_W_VECTOR = 0.5
RRF_W_BM25 = 0.5


class VectorStore:
    """ChromaDB 向量存储封装"""

    # ChromaDB 持久化目录
    BASE_DIR = Path(__file__).parent.parent.parent.parent / "chroma_db_insulin_pump"
    COLLECTION_NAME_PREFIX = "qms_doc_"

    # 查询时使用的目标 collection 列表（优先级从高到低）
    # 注意: 这里使用的是 ChromaDB 中的实际 collection 名。
    # insulin_pump_kb 无前缀（历史遗留），uploads 实际名为 qms_doc_uploads。
    QUERY_COLLECTIONS = ["insulin_pump_kb", "qms_doc_uploads"]

    # 额外的 ChromaDB 目录及其 collection 列表
    # 格式: {db_path: [collection_names]}
    EXTRA_DB_CONFIG = {}

    # BM25 索引缓存: collection_name → (chunk_count, BM25Okapi_instance, tokenized_corpus)
    _bm25_cache: Dict[str, tuple] = {}
    _bm25_cache_lock = threading.Lock()

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
        extra_dbs: Optional[dict] = None
    ):
        """
        初始化向量存储

        Args:
            persist_directory: ChromaDB 数据持久化目录（个人库传入 kb_scope.user_kb_dir）
            collection_name: collection 名称（不包含前缀），默认使用 "all"
            extra_dbs: 显式多库检索目标 {db_path: [collection_names]}；
                       缺省时按 kb_scope 请求上下文解析（用户隔离），无上下文回退类级配置
        """
        self.persist_directory = persist_directory or str(self.BASE_DIR)
        self.collection_name = collection_name or "all"
        self.extra_dbs = extra_dbs

        # 确保目录存在
        os.makedirs(self.persist_directory, exist_ok=True)

        self._client = None
        self._collection = None
        self._embedder = None

    def _effective_extra(self) -> dict:
        """解析多库检索目标：显式参数 > kb_scope 请求上下文 > 类级默认。

        共享库目录（BASE_DIR）的目标已由 QUERY_COLLECTIONS 覆盖，剔除避免重复。
        """
        if self.extra_dbs is not None:
            return self.extra_dbs
        try:
            from app.services import kb_scope
            targets = kb_scope.query_targets()
            extra = {p: cs for p, cs in targets.items() if p != str(self.BASE_DIR)}
            if extra:
                return extra
        except Exception:
            pass
        return self.EXTRA_DB_CONFIG

    @property
    def client(self):
        """延迟初始化 ChromaDB 客户端（个人库走独立目录客户端缓存）"""
        if self.persist_directory != str(self.BASE_DIR):
            return self._get_client_for_path(self.persist_directory)
        global _chroma_client
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )
        return _chroma_client

    # 额外客户端缓存: {path: client}
    _extra_clients = {}

    @classmethod
    def _get_client_for_path(cls, db_path: str):
        """获取或创建指定路径的 ChromaDB 客户端"""
        db_path = os.path.abspath(db_path)
        if db_path not in cls._extra_clients:
            os.makedirs(db_path, exist_ok=True)
            cls._extra_clients[db_path] = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False)
            )
        return cls._extra_clients[db_path]

    @classmethod
    def set_extra_db_config(cls, config: dict):
        """
        设置额外的 ChromaDB 目录配置

        Args:
            config: {db_path: [collection_names]}
        """
        cls.EXTRA_DB_CONFIG = config
        # 清除旧的额外客户端缓存
        cls._extra_clients = {}

    @property
    def embedder(self):
        """延迟初始化嵌入器"""
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    @property
    def collection(self):
        """获取或创建 collection"""
        if self._collection is None:
            full_name = f"{self.COLLECTION_NAME_PREFIX}{self.collection_name}"
            self._collection = self.client.get_or_create_collection(
                name=full_name,
                metadata={"description": "QMS 医疗器械文档参考库"}
            )
        return self._collection

    def add_chunk(
        self,
        chunk_id: str,
        text: str,
        doc_type: str,
        source_file: str,
        section_title: Optional[str] = None,
        chunk_index: int = 0,
        metadata: Optional[dict] = None
    ):
        """
        添加单个文档块到向量库

        Args:
            chunk_id: 块唯一 ID
            text: 文本内容
            doc_type: 文档类型（用于过滤）
            source_file: 来源文件名
            section_title: 章节标题
            chunk_index: 块在文档中的顺序索引
            metadata: 额外元数据
        """
        meta = {
            "doc_type": doc_type,
            "source_file": source_file,
            "section_title": section_title or "",
            "chunk_index": chunk_index,
            **(metadata or {})
        }

        # 使用我们的嵌入器生成向量
        embedding = self.embedder.encode_single(text)

        self.collection.add(
            ids=[chunk_id],
            documents=[text],
            metadatas=[meta],
            embeddings=[embedding]
        )

    def add_chunks(self, chunks: list[dict], sec_level=None, acl_version: str = None):
        """
        批量添加文档块

        [SEC] 2026-09-28 统一打标收口（§4.1/§4.2）：入库 chunk 的密级五字段
        一律经 sec_filter.stamp_sec_meta 注入，调用方不得自行拼密级 metadata。
        sec_level 缺省时按 resolve_ingest_sec_level 判定（显式 > 上传者密级
        > 脚本缺省 SEC_DEFAULT_LEVEL=3）。

        Args:
            chunks: 块列表，每项包含 chunk_id, text, doc_type, source_file 等
            sec_level: 显式密级（0-3，管理端/上传表单指定）
            acl_version: 批次版本标记（回填/变更脚本传入）
        """
        if not chunks:
            return

        from app.services.rag import sec_filter

        ids = [c["chunk_id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        # 记录入库时间戳，供知识库文件列表按"最新上传优先"排序
        ingested_at = time.time()
        metadatas = []
        for c in chunks:
            meta = {
                "doc_type": c.get("doc_type", ""),
                "source_file": c.get("source_file", ""),
                "section_title": c.get("section_title", ""),
                "chunk_index": c.get("chunk_index", 0),
                "file_id": c.get("file_id", ""),
                "original_filename": c.get("original_filename", ""),
                "ingested_at": ingested_at,
            }
            meta = sec_filter.stamp_sec_meta(
                meta, sec_level=sec_level, acl_version=acl_version)
            metadatas.append(meta)

        # 使用我们的嵌入器批量生成向量
        embeddings = self.embedder.encode(texts)

        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )

    def retrieve(
        self,
        query: str,
        doc_type: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.0  # 默认 0.0 允许几乎所有结果通过
    ) -> list[dict]:
        """
        语义检索 - 从多个 collection 检索并合并结果

        [SEC] 2026-09-28 密级前置过滤（方案 §5.3）：enforce 模式下 coll.query
        携带 sec_filter 构造的密级 where；shadow 模式不注入 where、仅逐条
        复核标记 denied（不剔除）；off 回退上线前行为。超额召回 ×SEC_OVERFETCH。

        Args:
            query: 查询文本（产品信息）
            doc_type: 文档类型过滤（可选）
            top_k: 返回数量
            similarity_threshold: 最低相似度阈值（0-1），默认 0.0

        Returns:
            检索结果列表，每项包含 text, source_file, section_title, distance
        """
        from app.services.rag import sec_filter
        query_embedding = self.embedder.encode_single(query)
        all_results = []

        # [SEC] 密级过滤上下文（唯一出口 sec_filter，收口原则 §5.2）
        sec_where = sec_filter.effective_query_where()
        sec_mode = sec_filter.get_mode()
        user_sec = sec_filter.current_user_sec_level()
        n_fetch = sec_filter.overfetch_n(top_k)

        # 构建所有 (client, collection_name) 查询对
        query_targets = [(self.client, name) for name in self.QUERY_COLLECTIONS]
        for db_path, coll_names in self._effective_extra().items():
            client = self._get_client_for_path(db_path)
            for name in coll_names:
                query_targets.append((client, name))

        for client, coll_name in query_targets:
            try:
                coll = client.get_collection(name=coll_name)
                results = coll.query(
                    query_embeddings=[query_embedding],
                    n_results=n_fetch,
                    where=sec_where,
                    include=["documents", "metadatas", "distances"]
                )
                if results["ids"]:
                    # [SEC] shadow：无 where 查询 → 逐条密级复核标记 denied（不剔除）
                    if sec_mode == "shadow":
                        self._sec_mark_denied(
                            results["documents"][0], results["metadatas"][0],
                            coll_name, user_sec)
                    # [SEC] enforce：另跑同规模无 where 探针，仅为 denied 统计与 L3 样本
                    elif sec_mode == "enforce":
                        self._sec_probe_denied(
                            coll, query_embedding, n_fetch, coll_name, user_sec)
                    for i in range(len(results["ids"][0])):
                        distance = results["distances"][0][i]
                        similarity = max(0.0, 1.0 - distance / 2.0)
                        if similarity < similarity_threshold:
                            continue
                        meta = results["metadatas"][0][i] or {}
                        # doc_type 过滤
                        if doc_type and meta.get("doc_type", "") != doc_type:
                            continue
                        all_results.append({
                            "text": results["documents"][0][i],
                            "source_file": meta.get("source_file", ""),
                            "section_title": meta.get("section_title", ""),
                            "doc_type": meta.get("doc_type", ""),
                            "chunk_index": meta.get("chunk_index", 0),
                            "similarity": similarity,
                            "distance": distance,
                            "chunk_id": results["ids"][0][i],
                            "sec_level": sec_filter.chunk_sec_level(meta),
                            "sec_label": meta.get("sec_label", ""),
                        })
            except Exception as e:
                print(f"    [VectorStore] 查询 collection '{coll_name}' 失败: {e}")
                continue

        # 按相似度排序并返回 top_k
        all_results.sort(key=lambda x: x["similarity"], reverse=True)
        final = all_results[:top_k]
        # [SEC] 检索审计（异步落盘，不阻塞主链路；off 模式不审计）
        if sec_mode != "off":
            sec_filter.audit_retrieval(
                query=query, scope_summary=f"retrieve:{len(query_targets)}colls",
                results=final)
        return final

    def _sec_mark_denied(self, documents: list, metadatas: list,
                         coll_name: str, user_sec: int) -> None:
        """shadow 模式：对无 where 查询结果逐条密级复核，标记 denied（不剔除）"""
        from app.services.rag import sec_filter
        sec_filter.mark_denied_batch(documents, metadatas, coll_name, user_sec)

    def _sec_probe_denied(self, coll, query_embedding, n_fetch: int,
                          coll_name: str, user_sec: int) -> None:
        """enforce 模式探针：同规模无 where 查询，仅为获取 denied 统计与
        L3 兜底样本（§5.5）；不影响主结果集（主查询已由 where 前置过滤）。"""
        from app.services.rag import sec_filter
        sec_filter.probe_denied(coll, query_embedding, n_fetch, coll_name, user_sec)

    def retrieve_hybrid(
        self,
        query: str,
        doc_type: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        collections: Optional[List[str]] = None,
        audit_scope: Optional[str] = None
    ) -> list[dict]:
        """
        混合检索：向量 + BM25 双路召回，RRF 排名融合

        融合采用 Reciprocal Rank Fusion（score = Σ 1/(k+rank), k=60）：
        cosine 相似度（有界 0-1）与 BM25Okapi 分数（无界）量纲不可比，
        此前的加权线性融合在单侧极端分时会被劫持；rank-based 融合只用排名，
        对分数分布免疫。similarity 字段归一化为 min(1, rrf/(n_lists/(k+1)))，
        近似保留 0-1 阈值语义（无 rerank 路径的 WEB_FALLBACK 消费该字段）。

        注意：当 collection 数据量过大时（>5万条），BM25 检索需加载全量数据到内存，
        开销巨大，因此对大 collection 仅使用向量检索。

        Args:
            query: 查询文本
            doc_type: 文档类型过滤（可选），如果过滤后无结果则忽略
            top_k: 返回数量
            similarity_threshold: 最低相似度阈值（0-1，作用于向量路召回）
            collections: 显式限定检索的 collection 名列表（仅本 store 自身 client）；
                         uploads 等定向检索场景传入，缺省查全部目标库
            audit_scope: 检索审计的 scope_summary 覆盖值（如 "search_kb:uploads"），
                         缺省用 "hybrid:{n}colls"

        Returns:
            合并后的检索结果列表，按 RRF 综合分数排序
        """
        t_start = time.time()
        print(f"    [VectorStore] retrieve_hybrid start — query='{query[:80]}'")

        t_embed_start = time.time()
        query_embedding = self.embedder.encode_single(query)
        print(f"    [VectorStore] embedding done ({time.time() - t_embed_start:.1f}s)")

        # [SEC] 密级过滤上下文（§5.2 收口；off 模式完全回退上线前行为）
        from app.services.rag import sec_filter
        sec_where = sec_filter.effective_query_where()
        sec_mode = sec_filter.get_mode()
        user_sec = sec_filter.current_user_sec_level()
        n_fetch = top_k * 2 if sec_mode == "off" else max(
            top_k * 2, sec_filter.overfetch_n(top_k))

        # 构建所有 (client, collection_name) 查询对
        # collections 显式限定时仅查本 store 自身 client 的指定 collection（uploads 定向检索）
        if collections:
            query_targets = [(self.client, name) for name in collections]
        else:
            query_targets = [(self.client, name) for name in self.QUERY_COLLECTIONS]
            for db_path, coll_names in self._effective_extra().items():
                client = self._get_client_for_path(db_path)
                for name in coll_names:
                    query_targets.append((client, name))

        # 1. 向量检索 - 从所有 collection 检索并合并
        vector_dict = {}
        for client, coll_name in query_targets:
            try:
                coll = client.get_collection(name=coll_name)
                vector_results = coll.query(
                    query_embeddings=[query_embedding],
                    n_results=n_fetch,
                    where=sec_where,
                    include=["documents", "metadatas", "distances"]
                )
                if vector_results["ids"]:
                    # [SEC] shadow：无 where → 逐条复核标记 denied；enforce：探针取 denied 样本
                    if sec_mode == "shadow":
                        self._sec_mark_denied(
                            vector_results["documents"][0],
                            vector_results["metadatas"][0], coll_name, user_sec)
                    elif sec_mode == "enforce":
                        self._sec_probe_denied(
                            coll, query_embedding, n_fetch, coll_name, user_sec)
                    for i in range(len(vector_results["ids"][0])):
                        chunk_id = vector_results["ids"][0][i]
                        distance = vector_results["distances"][0][i]
                        similarity = max(0.0, 1.0 - distance / 2.0)

                        if similarity >= similarity_threshold:
                            meta = vector_results["metadatas"][0][i] or {}
                            chunk_doc_type = meta.get("doc_type", "")

                            # doc_type 过滤（uploads 用户上传文件的 doc_type 恒为 unknown，
                            # 豁免过滤以确保用户上传内容始终可被检索）
                            if doc_type and chunk_doc_type != doc_type and coll_name != "qms_doc_uploads":
                                continue

                            # 去重：同一 chunk_id 只保留相似度更高的
                            if chunk_id not in vector_dict or similarity > vector_dict[chunk_id]["vector_score"]:
                                vector_dict[chunk_id] = {
                                    "text": vector_results["documents"][0][i],
                                    "source_file": meta.get("source_file", ""),
                                    "section_title": meta.get("section_title", ""),
                                    "doc_type": chunk_doc_type,
                                    "chunk_index": meta.get("chunk_index", 0),
                                    "similarity": similarity,
                                    "vector_score": similarity,
                                    "bm25_score": 0.0,
                                    "source_collection": coll_name,
                                    "sec_level": sec_filter.chunk_sec_level(meta),
                                    "sec_label": meta.get("sec_label", ""),
                                }
            except Exception as e:
                print(f"    [VectorStore] 混合检索 collection '{coll_name}' 失败: {e}")
                continue

        # 如果 doc_type 过滤后无结果，忽略过滤重新检索
        # [SEC] 红线：回退的只是 doc_type，密级 where 必须原样携带（§5 红线1）
        if not vector_dict and doc_type:
            print(f"    [RAG] doc_type='{doc_type}' 过滤无结果，忽略类型过滤")
            for client, coll_name in query_targets:
                try:
                    coll = client.get_collection(name=coll_name)
                    vector_results = coll.query(
                        query_embeddings=[query_embedding],
                        n_results=n_fetch,
                        where=sec_where,
                        include=["documents", "metadatas", "distances"]
                    )
                    if vector_results["ids"]:
                        if sec_mode == "shadow":
                            self._sec_mark_denied(
                                vector_results["documents"][0],
                                vector_results["metadatas"][0], coll_name, user_sec)
                        for i in range(len(vector_results["ids"][0])):
                            chunk_id = vector_results["ids"][0][i]
                            distance = vector_results["distances"][0][i]
                            similarity = max(0.0, 1.0 - distance / 2.0)

                            if similarity >= similarity_threshold:
                                meta = vector_results["metadatas"][0][i] or {}
                                if chunk_id not in vector_dict or similarity > vector_dict[chunk_id]["vector_score"]:
                                    vector_dict[chunk_id] = {
                                        "text": vector_results["documents"][0][i],
                                        "source_file": meta.get("source_file", ""),
                                        "section_title": meta.get("section_title", ""),
                                        "doc_type": meta.get("doc_type", ""),
                                        "chunk_index": meta.get("chunk_index", 0),
                                        "similarity": similarity,
                                        "vector_score": similarity,
                                        "bm25_score": 0.0,
                                        "source_collection": coll_name,
                                        "sec_level": sec_filter.chunk_sec_level(meta),
                                        "sec_label": meta.get("sec_label", ""),
                                    }
                except Exception:
                    continue

        t_vector_done = time.time()
        print(f"    [VectorStore] vector search done — {len(vector_dict)} results ({t_vector_done - t_embed_start:.1f}s from embed start)")

        # 2. BM25 关键词检索 - 仅对小 collection 执行（<5万条）
        # [SEC] §5.4 缓存不变、候选复核：BM25 索引仍按全量语料构建（缓存复用），
        # 对返回候选逐条密级复核——enforce 剔除并登记，shadow 仅登记不剔除。
        bm25_hits = {}
        for client, coll_name in query_targets:
            try:
                coll = client.get_collection(name=coll_name)
                coll_count = coll.count()
                if coll_count < 50000:
                    hits = self._bm25_search_collection(client, coll_name, query, None, top_k * 2)
                    for cid, hit in hits.items():
                        prev = bm25_hits.get(cid)
                        if prev is None or hit["score"] > prev["score"]:
                            bm25_hits[cid] = hit
                else:
                    print(f"    [VectorStore] 跳过 BM25 检索（{coll_name} 有 {coll_count} 条，超过 5 万阈值）")
            except Exception:
                continue

        # [SEC] BM25 候选密级复核（§5.4）
        bm25_scores = {}
        for cid, hit in bm25_hits.items():
            if sec_mode == "off":
                bm25_scores[cid] = hit["score"]
                continue
            if not sec_filter.candidate_visible(hit.get("meta"), user_sec):
                sec_filter.note_denied(hit.get("doc", ""), hit.get("meta"),
                                       hit.get("collection", ""))
                if sec_mode == "enforce":
                    continue  # 剔除：BM25 命中但密级不可见
            bm25_scores[cid] = hit["score"]

        t_bm25_done = time.time()
        print(f"    [VectorStore] BM25 done — {len(bm25_scores)} results ({t_bm25_done - t_vector_done:.1f}s)")

        # 3. 加权 RRF（Reciprocal Rank Fusion）合并结果
        # 向量路与 BM25 路分别按自身分数排名，chunk 得分 = Σ w/(k+rank)（k=60 标准平滑）。
        # 只用排名不用原始分 → 对两路分数分布/量纲完全免疫（cosine 有界 vs BM25Okapi 无界）。
        # [2026-10-10 权重网格] golden set 实测（0.6/0.4→0.5/0.5 之间存在悬崖）：
        #   0.6v/0.4b: R@15=0.58（向量路前 31 名全数压过 BM25 第 1 名，标准号
        #               gold 由 BM25 精确匹配承载、被向量尾巴挤出窗口）
        #   0.5v/0.5b: R@15=1.00 RR=0.318（唯一「两路互不淹没」的对称配置）
        #   0.4v/0.6b ~ 0.2v/0.8b: R@15=1.00，RR 略升但 BM25 可淹没向量路头部
        # 取等权：主链路（精排候选池）对各配置不敏感，回退路径需要对称鲁棒性，
        # 且与 _fuse_rrf 多查询平权语义一致。调参改模块常量 RRF_W_*。
        rrf_k = 60.0
        w_vector, w_bm25 = RRF_W_VECTOR, RRF_W_BM25

        rrf_scores: Dict[str, float] = {}
        for rank, cid in enumerate(
                sorted(vector_dict, key=lambda c: vector_dict[c]["vector_score"], reverse=True),
                start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + w_vector / (rrf_k + rank)
        for rank, cid in enumerate(
                sorted(bm25_scores, key=lambda c: bm25_scores[c], reverse=True),
                start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + w_bm25 / (rrf_k + rank)

        # 归一化锚点：两路同 chunk 同时第 1 的理论贡献上界（w 和 = 1）
        norm_cap = (w_vector + w_bm25) / (rrf_k + 1.0)

        merged = []
        for chunk_id, rrf in rrf_scores.items():
            vec_score = vector_dict.get(chunk_id, {}).get("vector_score", 0.0)
            bm_score = bm25_scores.get(chunk_id, 0.0)

            chunk_info = vector_dict.get(chunk_id, {})
            bm_hit = bm25_hits.get(chunk_id, {})
            bm_meta = bm_hit.get("meta") or {}
            merged.append({
                # bm25-only 命中（向量段未召回）时从 BM25 载荷补全文与元数据
                "chunk_id": chunk_id,
                "text": chunk_info.get("text") or bm_hit.get("doc", ""),
                "source_file": chunk_info.get("source_file") or bm_meta.get("source_file", ""),
                "section_title": chunk_info.get("section_title") or bm_meta.get("section_title", ""),
                "doc_type": chunk_info.get("doc_type") or bm_meta.get("doc_type", ""),
                "chunk_index": chunk_info.get("chunk_index", bm_meta.get("chunk_index", 0)),
                "similarity": min(1.0, rrf / norm_cap),
                "vector_score": vec_score,
                "bm25_score": bm_score,
                "rrf_score": rrf,
                "source_collection": chunk_info.get("source_collection") or bm_hit.get("collection", ""),
                "sec_level": chunk_info.get("sec_level")
                if chunk_info.get("sec_level") is not None
                else sec_filter.chunk_sec_level(bm_meta),
                "sec_label": chunk_info.get("sec_label") or bm_meta.get("sec_label", ""),
            })

        # 按 RRF 分数排序（并列时向量分高者优先，保证确定性）
        merged.sort(key=lambda x: (-x["rrf_score"], -x["vector_score"]))

        final = merged[:top_k]
        print(f"    [VectorStore] retrieve_hybrid done — {len(final)} results, total {time.time() - t_start:.1f}s")

        # [SEC] 检索审计（异步落盘；off 模式不审计）
        if sec_mode != "off":
            sec_filter.audit_retrieval(
                query=query,
                scope_summary=audit_scope or f"hybrid:{len(query_targets)}colls",
                results=final)
        return final

    @classmethod
    def _get_or_build_bm25(cls, cache_key: str, docs: List[str]):
        """
        获取或构建缓存的 BM25Okapi 实例

        当 collection 的 chunk 数量不变时，复用已构建的 BM25 索引，
        避免每次查询都重新加载全量文档 + 重新分词。

        [2026-10-10 评测回退] 语料不做元数据前置：前置 source_file 会让同文件
        全部 chunk 命中标准号 token，BM25 路同文件洪水把边缘 gold 挤出窗口
        （R@15 1.0→0.83）。精确词对齐由分词层标准号规范化 token 承担（正文级）。

        Args:
            cache_key: 缓存键 "{id(client)}::{collection_name}"——不同 ChromaDB
                       目录下同名 collection（如各用户的 qms_doc_uploads）互不串缓存
            docs: 文档正文列表

        Returns:
            (BM25Okapi_instance, tokenized_corpus)
        """
        from rank_bm25 import BM25Okapi

        chunk_count = len(docs)
        corpus = docs

        with cls._bm25_cache_lock:
            cached = cls._bm25_cache.get(cache_key)
            if cached and cached[0] == chunk_count:
                return cached[1], cached[2]

            # 重建：分词 + 构建 BM25
            tokenizer = get_tokenizer()
            tokenized_corpus = tokenizer.tokenize_corpus(corpus)
            bm25 = BM25Okapi(
                tokenized_corpus,
                k1=1.2,    # 降低高频词惩罚（中文法规文档核心术语频繁出现）
                b=0.6,     # 放宽长文档惩罚（中文 chunk 普遍较长）
                epsilon=0.25
            )

            # 缓存
            cls._bm25_cache[cache_key] = (chunk_count, bm25, tokenized_corpus)

            # LRU 淘汰：超过 10 个缓存项时删除最旧的
            if len(cls._bm25_cache) > 10:
                oldest_key = next(iter(cls._bm25_cache))
                del cls._bm25_cache[oldest_key]

            return bm25, tokenized_corpus

    @classmethod
    def invalidate_bm25_cache(cls, collection_name: str = None):
        """使 BM25 缓存失效（文档摄入后调用）。

        缓存键为 "{id(client)}::{collection_name}"，按后缀匹配清理
        同名 collection 的全部缓存（跨目录全清）。
        """
        with cls._bm25_cache_lock:
            if collection_name:
                suffix = f"::{collection_name}"
                for key in [k for k in cls._bm25_cache if k.endswith(suffix)]:
                    del cls._bm25_cache[key]
            else:
                cls._bm25_cache.clear()

    def _bm25_search(
        self,
        query: str,
        doc_type: Optional[str] = None,
        top_k: int = 10
    ) -> dict:
        """
        BM25 关键词检索 - 从默认 collection 检索

        Returns:
            {chunk_id: {"score", "doc", "meta", "collection"}, ...}
        """
        full_name = f"{self.COLLECTION_NAME_PREFIX}{self.collection_name}"
        return self._bm25_search_collection(self.client, full_name, query, doc_type, top_k)

    def _bm25_search_collection(
        self,
        client,
        collection_name: str,
        query: str,
        doc_type: Optional[str] = None,
        top_k: int = 10
    ) -> dict:
        """
        BM25 关键词检索 - 从指定 collection 检索（jieba 中文分词版）

        改动点：
        1. str.split() → jieba.cut_for_search() 中文分词
        2. 增加 BM25 索引缓存，避免每次查询重新构建
        3. doc_type 过滤后若为空，直接返回空字典（避免无效分词）
        4. [SEC 2026-09-28] 返回值携带 doc/meta/collection，供调用方做密级
           候选复核（§5.4：缓存不变、候选复核）与 bm25-only 结果合并

        Args:
            client: ChromaDB 客户端
            collection_name: collection 名称
            query: 查询文本
            doc_type: 文档类型过滤
            top_k: 返回数量

        Returns:
            {chunk_id: {"score": bm25_score, "doc": text, "meta": meta,
                        "collection": collection_name}, ...}
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return {}

        try:
            coll = client.get_collection(name=collection_name)

            # 根据是否过滤选择加载方式
            if doc_type:
                result = coll.get(include=["documents", "metadatas"])

                if not result["ids"]:
                    return {}

                # doc_type 过滤
                ids, docs, metas = [], [], []
                for i, meta in enumerate(result["metadatas"]):
                    if meta and meta.get("doc_type") == doc_type:
                        ids.append(result["ids"][i])
                        docs.append(result["documents"][i])
                        metas.append(meta)

                if not docs:
                    return {}

                # 小批量手动构建 BM25（不缓存，因为过滤后的子集每次可能不同）
                tokenizer = get_tokenizer()
                tokenized_corpus = tokenizer.tokenize_corpus(docs)
                bm25 = BM25Okapi(
                    tokenized_corpus,
                    k1=1.2,
                    b=0.6,
                    epsilon=0.25
                )
            else:
                # 无过滤：使用缓存
                result = coll.get(include=["documents", "metadatas"])

                if not result["ids"]:
                    return {}

                ids = result["ids"]
                docs = result["documents"]
                metas = result["metadatas"]

                bm25, _tokenized_corpus = self._get_or_build_bm25(
                    f"{id(client)}::{collection_name}", docs)

            # 查询分词
            tokenizer = get_tokenizer()
            query_tokens = list(tokenizer.tokenize(query))

            if not query_tokens:
                return {}

            scores = bm25.get_scores(query_tokens)

            # 返回 top_k
            top_indices = sorted(
                range(len(scores)),
                key=lambda i: scores[i],
                reverse=True
            )[:top_k]

            return {
                ids[i]: {
                    "score": scores[i],
                    "doc": docs[i],
                    "meta": metas[i] or {},
                    "collection": collection_name,
                }
                for i in top_indices
                if scores[i] > 0
            }

        except Exception as e:
            print(f"    [VectorStore] BM25 检索失败: {e}")
            return {}

    @staticmethod
    def _fuse_rrf(paths: List[List[dict]], rrf_k: float = 60.0) -> List[dict]:
        """跨查询 RRF 融合（方案 §3.1）：每路结果按自身 rrf_score 排名，
        chunk 融合分 = Σ 1/(k+rank)。重复 chunk 保留单路表现最好的一份载荷，
        并附 matched_queries（命中路数）与 mq_rrf_score 字段。输出按融合分降序。

        纯函数（不触 Chroma/模型），可直接单测。
        """
        fused_scores: Dict[str, float] = {}
        best: Dict[str, dict] = {}
        n_hit: Dict[str, int] = {}
        for path in paths:
            ranked = sorted(
                path,
                key=lambda r: (r.get("rrf_score") or 0.0,
                               r.get("similarity") or 0.0),
                reverse=True)
            for rank, r in enumerate(ranked, start=1):
                cid = r.get("chunk_id") or ("text::" + (r.get("text") or "")[:120])
                fused_scores[cid] = fused_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
                n_hit[cid] = n_hit.get(cid, 0) + 1
                cur = best.get(cid)
                if cur is None or (r.get("rrf_score") or 0.0) > (cur.get("rrf_score") or 0.0):
                    best[cid] = r
        out = []
        for cid, score in fused_scores.items():
            item = dict(best[cid])
            item["mq_rrf_score"] = score
            item["matched_queries"] = n_hit[cid]
            out.append(item)
        out.sort(key=lambda x: (-x["mq_rrf_score"], -(x.get("rrf_score") or 0.0)))
        return out

    def retrieve_multi_query(
        self,
        queries: List[str],
        top_k: int = 5,
        candidate_pool_size: int = 30,
        similarity_threshold: float = 0.3,
        min_rerank_score: float = 0.0,
        use_rerank: bool = True,
    ) -> list[dict]:
        """
        多查询融合检索（方案 §3.1）：N 路混合检索 + 跨查询 RRF 融合 + 可选精排。

        把「多查询」从 agent 自觉行为下沉为检索层内部行为：
          1. 每路查询各自 retrieve_hybrid（向量+BM25、单路 RRF、SEC 全链路）
          2. 跨查询按各路 rrf_score 排名做第二轮 RRF 融合（对抗单查询词汇偏置）
          3. use_rerank=True 时精排仅对融合后候选池执行一次（原始查询作为
             精排 query），避免 N 路 × GPU 精排的线性成本

        Args:
            queries: 查询列表（queries[0] 为原始查询，其余为变体）
            top_k: 最终返回数量
            candidate_pool_size: 送入精排的融合候选池大小
            similarity_threshold: 各路向量召回阈值
            min_rerank_score: 精排最低分数阈值（0=不过滤）
            use_rerank: 是否精排

        Returns:
            融合（+精排）后的结果列表
        """
        from concurrent.futures import ThreadPoolExecutor

        queries = [q for q in queries if q and q.strip()]
        if not queries:
            return []

        t_start = time.time()
        print(f"[MultiQuery] {len(queries)} 路查询融合开始")

        per_path_k = candidate_pool_size if use_rerank else top_k

        def _one(q: str) -> list[dict]:
            try:
                return self.retrieve_hybrid(
                    query=q,
                    top_k=per_path_k,
                    similarity_threshold=similarity_threshold,
                )
            except Exception as e:
                print(f"[MultiQuery] 单路检索失败（降级跳过）: {e}")
                return []

        if len(queries) == 1:
            paths = [_one(queries[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(queries))) as ex:
                paths = list(ex.map(_one, queries))

        fused = self._fuse_rrf(paths)
        if not fused:
            return []

        if not use_rerank:
            final = fused[:top_k]
            print(f"[MultiQuery] 融合完成 — {len(final)} 结果 ({time.time() - t_start:.1f}s)")
            return final

        # 精排：仅一次，query 用原始查询（queries[0]）
        from app.services.rag.reranker import Reranker
        reranker = Reranker()
        _ = reranker.model  # 触发模型加载（须在 BM25 大内存分配前，见 retrieve_and_rerank 注释）
        final = reranker.rerank_with_threshold(
            query=queries[0],
            chunks=fused[:candidate_pool_size],
            top_k=top_k,
            min_score=min_rerank_score,
        )
        print(f"[MultiQuery] 融合+精排完成 — {len(final)} 结果 ({time.time() - t_start:.1f}s)")
        return final

    def retrieve_and_rerank(
        self,
        query: str,
        doc_type: Optional[str] = None,
        top_k: int = 5,
        candidate_pool_size: int = 30,
        similarity_threshold: float = 0.3,
        min_rerank_score: float = 0.0,
    ) -> list[dict]:
        """
        两阶段检索：粗召回 + Cross-Encoder 精排

        阶段1 — 粗召回 (高召回率):
          - 向量检索 + BM25 检索各取 candidate_pool_size
          - RRF 排名融合去重（见 retrieve_hybrid）

        阶段2 — 精排 (高精确率):
          - Cross-Encoder (BGE-Reranker-v2-m3) 对候选池逐条打分
          - 按精排分数降序排列，返回 top_k

        Args:
            query: 查询文本
            doc_type: 文档类型过滤（可选）
            top_k: 精排后返回数量（最终输出）
            candidate_pool_size: 粗召回候选池大小（建议 20-40）
            similarity_threshold: 粗召回最低相似度阈值（作用于向量路召回）
            min_rerank_score: 精排最低分数阈值（0-1），0=不过滤

        Returns:
            精排后的检索结果列表
        """
        t_start = time.time()

        # ── 阶段0: 预加载 Reranker 模型 ──
        # 必须在 BM25 加载 9622 文档之前加载 reranker 模型到 GPU，
        # 否则 BM25 大规模内存分配后再初始化 PyTorch+CUDA 会触发 segfault
        from app.services.rag.reranker import Reranker
        reranker = Reranker()
        _ = reranker.model  # 触发模型加载

        # ── 阶段1: 粗召回 ──
        candidates = self.retrieve_hybrid(
            query=query,
            doc_type=doc_type,
            top_k=candidate_pool_size,
            similarity_threshold=similarity_threshold,
        )

        if not candidates:
            print(f"[TwoStage] 粗召回无结果，跳过精排")
            return []

        print(f"[TwoStage] 粗召回完成: {len(candidates)} 候选 ({time.time() - t_start:.1f}s)")

        # ── 阶段2: Cross-Encoder 精排 ──
        t_rerank = time.time()
        results = reranker.rerank_with_threshold(
            query=query,
            chunks=candidates,
            top_k=top_k,
            min_score=min_rerank_score,
        )

        print(f"[TwoStage] 精排完成: {len(results)} 结果 "
              f"({time.time() - t_rerank:.1f}s), "
              f"总耗时 {time.time() - t_start:.1f}s")

        return results

    def count(self) -> int:
        """返回所有查询 collection 中的文档块总数"""
        total = 0
        for coll_name in self.QUERY_COLLECTIONS:
            try:
                coll = self.client.get_collection(name=coll_name)
                total += coll.count()
            except Exception:
                continue
        for db_path, coll_names in self._effective_extra().items():
            try:
                client = self._get_client_for_path(db_path)
                for coll_name in coll_names:
                    try:
                        coll = client.get_collection(name=coll_name)
                        total += coll.count()
                    except Exception:
                        continue
            except Exception:
                continue
        # 如果目标 collection 无数据，回退到默认 collection
        if total == 0:
            return self.collection.count()
        return total

    def clear(self):
        """清空 collection（谨慎使用）"""
        try:
            self.client.delete_collection(
                name=f"{self.COLLECTION_NAME_PREFIX}{self.collection_name}"
            )
            self._collection = None
        except Exception:
            pass

    def delete_by_source(self, source_file: str):
        """
        删除指定来源文件的所有块

        Args:
            source_file: 来源文件名
        """
        try:
            self.collection.delete(
                where={"source_file": source_file}
            )
        except Exception:
            pass

    def get_sources(self) -> list[str]:
        """获取向量库中所有来源文件列表"""
        try:
            result = self.collection.get(include=["metadatas"])
            sources = set()
            for meta in result.get("metadatas", []):
                if meta and meta.get("source_file"):
                    sources.add(meta["source_file"])
            return sorted(list(sources))
        except Exception:
            return []

    def list_uploaded_files(self) -> list[dict]:
        """
        列出上传知识库中所有文件及其统计信息

        遍历 qms_doc_uploads 集合的所有 chunk 元数据，按 source_file 聚合，
        返回每个文件的：文件名、原始文件名、file_id、chunk 数量、入库时间戳，
        按入库时间倒序排列（最新上传的文件排最前）。

        Returns:
            [{"source_file": str, "original_filename": str, "file_id": str,
              "chunk_count": int, "ingested_at": float}, ...]
        """
        try:
            result = self.collection.get(include=["metadatas"])
            files: dict[str, dict] = {}
            for meta in result.get("metadatas", []):
                if not meta:
                    continue
                sf = meta.get("source_file", "")
                if not sf:
                    continue
                if sf not in files:
                    files[sf] = {
                        "source_file": sf,
                        "original_filename": meta.get("original_filename", "") or "",
                        "file_id": meta.get("file_id", "") or "",
                        "ingested_at": meta.get("ingested_at", 0) or 0,
                        "chunk_count": 0,
                    }
                files[sf]["chunk_count"] += 1
                # [SEC 2026-09-29] 聚合该文件各 chunk 的密级（fail-closed：缺失按 3）
                lvl = meta.get("sec_level")
                if not isinstance(lvl, int) or lvl < 0 or lvl > 3:
                    lvl = 3
                    files[sf]["_sec_missing"] = True
                if lvl > files[sf].get("sec_level", -1):
                    files[sf]["sec_level"] = lvl
                if "sec_levels_seen" not in files[sf]:
                    files[sf]["sec_levels_seen"] = {lvl}
                else:
                    files[sf]["sec_levels_seen"].add(lvl)
                # 优先使用非空的 file_id 和 original_filename
                if not files[sf]["file_id"] and meta.get("file_id"):
                    files[sf]["file_id"] = meta["file_id"]
                if not files[sf]["original_filename"] and meta.get("original_filename"):
                    files[sf]["original_filename"] = meta["original_filename"]
                # 取该文件各 chunk 中最新的入库时间（同一文件各 chunk 时间戳相同）
                ts = meta.get("ingested_at", 0) or 0
                if ts > files[sf]["ingested_at"]:
                    files[sf]["ingested_at"] = ts
            # mixed_sec：各 chunk 密级不一致或存在未标注 chunk（台账"立即修复"信号）
            for f in files.values():
                f["mixed_sec"] = bool(f.pop("_sec_missing", False)) \
                    or len(f.pop("sec_levels_seen", set())) > 1
            # 按入库时间倒序：最新上传的文件排最前；旧文件（无时间戳=0）排最后
            return sorted(list(files.values()), key=lambda x: x["ingested_at"], reverse=True)
        except Exception as e:
            print(f"[VectorStore] list_uploaded_files 异常: {e}")
            return []

    def get_text_by_source(self, source_file: str) -> str:
        """
        按来源文件取回全部文本：取该文件所有 chunk，按 chunk_index 排序后拼接。

        用于前端「查看知识库文件内容」：知识库只存分块，不存原文，
        按 chunk_index 顺序拼接分块文本即可近似还原全文。

        Args:
            source_file: 来源文件标识

        Returns:
            拼接后的全文；文件不存在或异常时返回空字符串。
        """
        try:
            result = self.collection.get(
                where={"source_file": source_file},
                include=["documents", "metadatas"],
            )
            docs = result.get("documents", []) or []
            metas = result.get("metadatas", []) or []
            if not docs:
                return ""
            chunks = [
                (meta.get("chunk_index", 0) if meta else 0, doc)
                for doc, meta in zip(docs, metas)
            ]
            chunks.sort(key=lambda x: x[0])
            return "\n\n".join(doc for _, doc in chunks)
        except Exception as e:
            print(f"[VectorStore] get_text_by_source 异常: {e}")
            return ""
