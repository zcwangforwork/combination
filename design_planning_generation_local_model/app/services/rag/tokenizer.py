"""
app/services/rag/tokenizer.py
中文分词器 - jieba 封装，支持领域词典、停用词过滤、缓存

替代 vector_store.py 中原有的 doc.lower().split() 分词逻辑。
"""

import os
import threading
from pathlib import Path
from typing import List, Optional
from functools import lru_cache

import jieba


# ── 路径配置 ──

_BASE_DIR = Path(__file__).parent
_DICT_PATH = _BASE_DIR / "medical_device_dict.txt"
_STOPWORDS_PATH = _BASE_DIR / "stopwords_zh.txt"


# ── 常量 ──

_BUILTIN_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "他", "这", "中", "大",
    "来", "上", "国", "个", "到", "说", "们", "为",
    "子", "你", "地", "出", "也", "时", "要",
    "下", "会", "可", "对", "生", "能", "而", "等",
    "及", "其", "或", "与", "之", "从", "所", "被",
    "并", "将", "已", "以", "且", "但", "若", "该",
    "则", "因", "此", "如", "无", "未", "更", "最",
}


class ChineseTokenizer:
    """中文分词器（线程安全，支持缓存）"""

    def __init__(
        self,
        dict_path: Optional[Path] = None,
        stopwords_path: Optional[Path] = None,
        use_stopwords: bool = True,
        cache_size: int = 16
    ):
        """
        Args:
            dict_path: 领域词典路径，None 则使用默认路径
            stopwords_path: 停用词文件路径，None 则使用内置最小集
            use_stopwords: 是否启用停用词过滤
            cache_size: tokenize() 结果的 LRU 缓存大小
        """
        self.dict_path = dict_path or _DICT_PATH
        self.stopwords_path = stopwords_path or _STOPWORDS_PATH
        self.use_stopwords = use_stopwords
        self._lock = threading.Lock()
        self._dict_loaded = False
        self._stopwords: set = set(_BUILTIN_STOPWORDS)

        # 初始化
        self._load_dict()
        self._load_stopwords()

        # 用 LRU 缓存包装 tokenize 实现
        self.tokenize = lru_cache(maxsize=cache_size)(self._tokenize_impl)

    def _load_dict(self):
        """加载领域词典"""
        dict_path_str = str(self.dict_path)
        if os.path.exists(dict_path_str):
            jieba.load_userdict(dict_path_str)
            self._dict_loaded = True
            print(f"[Tokenizer] 已加载领域词典: {dict_path_str}")
        else:
            print(f"[Tokenizer] 领域词典不存在({dict_path_str})，使用 jieba 默认词典。"
                  f"建议创建该文件以提升医疗法规领域的分词精度。")

    def _load_stopwords(self):
        """加载停用词表"""
        stopwords_path_str = str(self.stopwords_path)
        if os.path.exists(stopwords_path_str):
            with open(stopwords_path_str, 'r', encoding='utf-8') as f:
                file_stopwords = set(
                    line.strip() for line in f
                    if line.strip() and not line.startswith('#')
                )
            self._stopwords.update(file_stopwords)
            print(f"[Tokenizer] 已加载 {len(file_stopwords)} 个停用词")
        else:
            print(f"[Tokenizer] 停用词文件不存在，使用内置最小集 ({len(_BUILTIN_STOPWORDS)} 词)")

    def _tokenize_impl(self, text: str) -> tuple:
        """
        对文本进行分词（内部实现，由 lru_cache 包装）

        策略：
        1. jieba.cut_for_search 搜索引擎模式分词
        2. 英文/数字部分自动保留
        3. 可选停用词过滤

        Returns:
            tuple (用于 LRU 缓存的可哈希类型)
        """
        if not text or not text.strip():
            return ()

        text = text.lower().strip()
        tokens = []

        raw_tokens = jieba.lcut_for_search(text)

        for token in raw_tokens:
            token = token.strip()
            if not token:
                continue
            if len(token) == 1:
                # 保留英文和数字单字符（如 "a", "1"）
                if token.isascii() and (token.isalpha() or token.isdigit()):
                    tokens.append(token)
                # 跳过中文单字符（停用词过滤会处理）
                elif not self.use_stopwords:
                    tokens.append(token)
            elif self.use_stopwords and token in self._stopwords:
                continue
            else:
                tokens.append(token)

        return tuple(tokens)

    def tokenize_corpus(self, docs: List[str]) -> List[List[str]]:
        """
        批量分词（用于 BM25 语料库构建）

        与逐个调用 tokenize() 等价，返回 list 格式。
        """
        return [list(self.tokenize(doc)) for doc in docs]

    def add_term(self, term: str, freq: int = 5):
        """动态添加领域术语（用于运行时发现的新术语）"""
        with self._lock:
            jieba.add_word(term, freq)
            self.tokenize.cache_clear()

    def add_terms(self, terms: List[tuple]):
        """批量添加术语 [(term, freq), ...]"""
        with self._lock:
            for term, freq in terms:
                jieba.add_word(term, freq)
            self.tokenize.cache_clear()

    def clear_cache(self):
        """手动清除 tokenize 缓存"""
        self.tokenize.cache_clear()


# ── 模块级单例 ──

_tokenizer_instance: Optional[ChineseTokenizer] = None
_tokenizer_lock = threading.Lock()


def get_tokenizer(**kwargs) -> ChineseTokenizer:
    """获取全局单例 tokenizer（线程安全）"""
    global _tokenizer_instance
    if _tokenizer_instance is None:
        with _tokenizer_lock:
            if _tokenizer_instance is None:
                _tokenizer_instance = ChineseTokenizer(**kwargs)
    return _tokenizer_instance


def reset_tokenizer():
    """重置 tokenizer 单例（用于测试或热更新词典）"""
    global _tokenizer_instance
    with _tokenizer_lock:
        _tokenizer_instance = None
