"""
Embedder - 嵌入模型封装

使用本地 Ollama 嵌入 API（qwen3-embedding:4b）生成文本嵌入向量。
通过 HTTP 直接调用 /api/embed 接口。
"""

import os
import time
from pathlib import Path
from typing import Optional

import httpx


class Embedder:
    """嵌入模型封装 - 本地 Ollama 嵌入 API"""

    # 默认模型
    DEFAULT_MODEL = "qwen3-embedding:4b"

    # 默认向量维度 (保持与现有 ChromaDB 一致)
    DEFAULT_DIMENSIONS = 1024

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimensions: int = DEFAULT_DIMENSIONS,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        """
        初始化嵌入模型

        Args:
            model_name: Ollama 嵌入模型名称，默认从 OLLAMA_EMBED_MODEL 环境变量读取
            dimensions: 向量维度，qwen3-embedding:4b 默认 2048
            api_key: 不再使用，保留兼容
            api_url: API URL，默认从 OLLAMA_BASE_URL 读取
        """
        self.model_name = model_name or os.getenv("OLLAMA_EMBED_MODEL", self.DEFAULT_MODEL)
        self.dimensions = dimensions
        self._api_key = api_key  # 保留兼容
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
        self._api_url = api_url or f"{base_url}/api/embed"
        self._api_key_resolved = None

    @property
    def api_key(self):
        """保留兼容接口（Ollama 不需要 API Key）"""
        if self._api_key_resolved is None:
            self._api_key_resolved = self._api_key or "ollama-local"
        return self._api_key_resolved

    def encode(self, texts: list[str], batch_size: int = 20) -> list[list[float]]:
        """
        将文本列表转换为嵌入向量列表

        使用 Ollama 批量嵌入 API，一次调用处理多条文本。

        Args:
            texts: 文本列表
            batch_size: 每批最大文本数，默认 20

        Returns:
            嵌入向量列表
        """
        if not texts:
            return []

        all_embeddings = []

        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start:batch_start + batch_size]

            # 带重试的 API 调用
            last_error = None
            for attempt in range(3):
                try:
                    embeddings = self._call_api_batch(batch)
                    all_embeddings.extend(embeddings)
                    break
                except Exception as e:
                    last_error = e
                    if attempt < 2:
                        wait = 2 ** attempt
                        print(
                            f"    [Embedder] API 请求失败，{wait}s 后重试 "
                            f"(第{attempt + 1}次): {e}"
                        )
                        time.sleep(wait)
                        continue
                    raise ConnectionError(
                        f"嵌入 API 请求失败（已重试3次）: {last_error}"
                    )

            # 进度打印
            done = min(batch_start + batch_size, len(texts))
            print(f"    [Embedder] 已完成 {done}/{len(texts)} 条向量化")

            # 批次间隔避免过载
            if batch_start + batch_size < len(texts):
                time.sleep(0.1)

        return all_embeddings

    def encode_single(self, text: str) -> list[float]:
        """单条文本嵌入"""
        return self.encode([text])[0]

    def _call_api_batch(self, texts: list[str]) -> list[list[float]]:
        """
        调用 Ollama 批量嵌入 API

        Args:
            texts: 待向量化的文本列表

        Returns:
            嵌入向量列表
        """
        # 截断过长文本
        texts = [t[:8000] for t in texts]

        payload = {
            "model": self.model_name,
            "input": texts,
        }

        with httpx.Client(timeout=120, trust_env=False) as client:
            response = client.post(self._api_url, json=payload)

            if response.status_code == 200:
                result = response.json()
                embeddings = result.get("embeddings", [])
                if embeddings:
                    # 截断到目标维度（Ollama 不支持 dimensions 参数，模型原始输出可能大于目标维度）
                    if len(embeddings[0]) > self.dimensions:
                        embeddings = [e[:self.dimensions] for e in embeddings]
                    return embeddings
                raise ValueError(f"API 返回数据格式异常: {str(result)[:200]}")
            else:
                raise ConnectionError(
                    f"API 请求失败 (HTTP {response.status_code}): {response.text[:300]}"
                )

    def _call_api(self, text: str) -> list[float]:
        """
        调用 Ollama 嵌入 API (单条文本，兼容旧接口)

        Args:
            text: 待向量化的文本

        Returns:
            嵌入向量
        """
        return self._call_api_batch([text])[0]
