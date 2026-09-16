"""
Cross-Encoder 重排序模块

使用 BGE-Reranker-v2-m3 对粗召回结果进行精排，提升检索精确率。

架构：
  粗召回候选(30条) → Cross-Encoder → 精排Top-N → LLM

模型选型：
  BAAI/bge-reranker-v2-m3 (568M, Apache 2.0, 中文最优)

部署方式：
  FlagEmbedding — Python原生，支持batch推理，GPU FP16
"""

from typing import Optional
import os
import threading
import pathlib

# 使用 HuggingFace 镜像，避免直连 huggingface.co 超时
# 必须在 import FlagEmbedding / transformers 之前设置
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 离线时禁用遥测，减少网络请求
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# 检测模型是否已本地缓存，若已缓存则启用离线模式，避免 DNS 解析失败导致的重试
# (hf-mirror.com 在某些网络环境下 DNS 解析会超时，每次加载重试5次浪费~30秒)
_RERANKER_MODEL_NAME = 'BAAI/bge-reranker-v2-m3'
_HF_CACHE_DIR = pathlib.Path.home() / ".cache" / "huggingface" / "hub"
_MODEL_CACHE_DIR = _HF_CACHE_DIR / f"models--{_RERANKER_MODEL_NAME.replace('/', '--')}"

if _MODEL_CACHE_DIR.exists() and _MODEL_CACHE_DIR.is_dir():
    # 模型已缓存，启用离线模式，跳过所有网络请求
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    _OFFLINE_MODE = True
else:
    _OFFLINE_MODE = False


class Reranker:
    """
    Cross-Encoder 重排序器（单例，惰性加载）

    使用方式:
        reranker = Reranker()
        results = reranker.rerank(query="ISO 14971 风险分析", chunks=chunks, top_k=5)
    """

    _instance: Optional['Reranker'] = None
    _lock = threading.Lock()

    def __new__(cls, model_name: str = 'BAAI/bge-reranker-v2-m3'):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._model = None
                    obj._model_name = model_name
                    cls._instance = obj
        return cls._instance

    @property
    def model(self):
        """惰性加载模型（首次调用时加载到 GPU FP16）"""
        if self._model is not None:
            return self._model

        from FlagEmbedding import FlagReranker

        self._model = FlagReranker(
            self._model_name,
            use_fp16=True,
            devices=['cuda:0'],
        )
        offline_tag = " [OFFLINE]" if _OFFLINE_MODE else ""
        print(f"[Reranker] 已加载 {self._model_name} 到 GPU (FP16){offline_tag}")
        return self._model

    def rerank(
        self,
        query: str,
        chunks: list[dict],
        top_k: int = 5,
        max_chunk_length: int = 1500,
    ) -> list[dict]:
        """
        对粗召回结果进行 Cross-Encoder 精排

        Args:
            query: 原始查询文本
            chunks: 粗召回结果列表，每个元素需包含 'text' 字段
            top_k: 精排后保留的数量
            max_chunk_length: 单个 chunk 送入模型的最大字符数

        Returns:
            精排后的结果列表，每个元素新增 'rerank_score' 字段
        """
        if not chunks:
            return []

        # 构建 (query, document) 配对
        pairs = [
            (query, c['text'][:max_chunk_length])
            for c in chunks
        ]

        try:
            # batch 推理 + 归一化（使分数跨批次可比）
            scores = self.model.compute_score(pairs, normalize=True)
        except Exception as e:
            print(f"[Reranker] 精排失败: {e}，返回原始排序")
            return chunks[:top_k]

        # 单条输入时 scores 为 float，统一为 list
        if isinstance(scores, (int, float)):
            scores = [float(scores)]
        else:
            scores = [float(s) for s in scores]

        # 写入精排分数
        for c, s in zip(chunks, scores):
            c['rerank_score'] = s

        # 按精排分数降序排列
        chunks.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)

        return chunks[:top_k]

    def rerank_with_threshold(
        self,
        query: str,
        chunks: list[dict],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict]:
        """
        带分数阈值的精排（过滤低相关度文档）

        Args:
            min_score: 最低精排分数阈值（0-1），低于此分数的文档被丢弃
        """
        ranked = self.rerank(query, chunks, top_k=len(chunks))
        filtered = [c for c in ranked if c.get('rerank_score', 0) >= min_score]
        return filtered[:top_k]
