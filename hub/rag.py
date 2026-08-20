# -*- coding: utf-8 -*-
"""
RAG 知识库（rag.py）

本地文档 → 分块 → jieba 分词 → BM25 索引 → 语义检索。
供 skills/rag_search 技能调用，让 Agent 能基于项目文档回答问题。

流程：
    RagIndex.build()  扫描 docs_dir 下文档（.md/.txt/.yaml/.py 等）→ 段落分块 → BM25 索引
    RagIndex.query()  问题分词 → BM25 top-k → 返回带来源的文本片段

用法：
    from rag import get_index
    idx = get_index()
    print(idx.query("协议 v2.0 新增了什么"))
"""
import logging
import math
import os
import re
import threading
from typing import Dict, List, Optional, Tuple

from settings import get

logger = logging.getLogger("rag")

# 默认扫描的扩展名
DEFAULT_EXTS = (".md", ".txt", ".yaml", ".yml", ".py", ".json", ".ino", ".cpp", ".h", ".html")
# 默认分块大小（字符）
CHUNK_SIZE = 400
# 默认 top_k
DEFAULT_TOP_K = 3


# =====================================================================
# BM25 检索器（自实现，无外部依赖）
# =====================================================================
class BM25:
    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(1, self.n)
        self.df: Dict[str, int] = {}
        for d in docs:
            for t in set(d):
                self.df[t] = self.df.get(t, 0) + 1

    def _score(self, query: List[str], doc_idx: int) -> float:
        doc = self.docs[doc_idx]
        dl = len(doc)
        s = 0.0
        for t in query:
            tf = doc.count(t)
            if tf == 0:
                continue
            idf = math.log(1 + (self.n - self.df.get(t, 0) + 0.5) / (self.df.get(t, 0) + 0.5))
            denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            s += idf * tf * (self.k1 + 1) / denom
        return s

    def search(self, query: List[str], top_k: int = DEFAULT_TOP_K) -> List[Tuple[float, int]]:
        scored = sorted(((self._score(query, i), i) for i in range(self.n)),
                        key=lambda x: x[0], reverse=True)
        return [(s, i) for s, i in scored if s > 0][:top_k]


# =====================================================================
# 分词工具（jieba）
# =====================================================================
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "等", "一个", "我们", "你", "我",
    "他", "她", "它", "这", "那", "之", "于", "对", "为", "把", "被", "也", "都",
    "很", "有", "没", "不", "就", "而", "并", "且", "将", "从", "到", "向", "说",
    "要", "会", "能", "可", "以", "对", "中", "里", "下", "上", "后", "前", "时",
}

_jieba_loaded = False
_jieba_lock = threading.Lock()


def _tokenize(text: str) -> List[str]:
    global _jieba_loaded
    if not _jieba_loaded:
        with _jieba_lock:
            if not _jieba_loaded:
                import jieba
                jieba.initialize()
                _jieba_loaded = True
    import jieba
    toks = []
    for w in jieba.cut(text.lower()):
        w = w.strip()
        if len(w) < 2 or w in _STOPWORDS:
            continue
        if re.fullmatch(r"[\w\u4e00-\u9fff]+", w):
            toks.append(w)
    return toks


# =====================================================================
# RAG 索引
# =====================================================================
def _chunk_text(text: str, size: int = CHUNK_SIZE) -> List[str]:
    """按空行段落分块，相邻小段合并到接近 size。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            chunks.append(cur)
            cur = ""
        cur += p + "\n"
    if cur:
        chunks.append(cur)
    return chunks


class RagIndex:
    def __init__(self, docs_dir: Optional[str] = None, exts=DEFAULT_EXTS):
        cfg = get("rag", {}) or {}
        self.docs_dir = docs_dir or cfg.get("docs_dir") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.exts = tuple(exts or cfg.get("exts") or DEFAULT_EXTS)
        self.chunks: List[dict] = []   # [{text, source}]
        self._bm25: Optional[BM25] = None
        self._built = False
        self._lock = threading.Lock()

    # ---------- 构建 ----------
    def build(self) -> int:
        """扫描文档目录并构建索引，返回分块数。"""
        with self._lock:
            self.chunks = []
            files = self._scan_files()
            for path in files:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read(500000)
                except OSError:
                    continue
                rel = os.path.relpath(path, self.docs_dir)
                for c in _chunk_text(text):
                    self.chunks.append({"text": c.strip(), "source": rel})
            tokenized = [_tokenize(c["text"]) for c in self.chunks]
            self._bm25 = BM25(tokenized) if self.chunks else None
            self._built = True
            logger.info("[rag] 索引完成：%d 个文档 → %d 个分块", len(files), len(self.chunks))
            return len(self.chunks)

    def _scan_files(self) -> List[str]:
        found = []
        for dirpath, dirnames, filenames in os.walk(self.docs_dir):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith((".", "$", "node_modules", ".venv", "__pycache__", "build", ".workbuddy"))]
            for fn in filenames:
                if fn.endswith(self.exts):
                    found.append(os.path.join(dirpath, fn))
        return found

    # ---------- 检索 ----------
    def query(self, question: str, top_k: int = DEFAULT_TOP_K) -> str:
        """检索与问题最相关的文档片段，返回带来源的文本。"""
        if not self._built:
            self.build()
        if not self._bm25 or not self.chunks:
            return "（知识库为空：docs_dir 下没有可检索文档）"

        q = _tokenize(question)
        if not q:
            return "（无法从问题中提取有效关键词）"

        hits = self._bm25.search(q, top_k=top_k)
        if not hits:
            return f"（知识库中未找到与「{question}」相关的内容）"

        parts = []
        for i, (score, idx_) in enumerate(hits):
            c = self.chunks[idx_]
            parts.append(f"[知识库检索] 相关片段 {i + 1}/{len(hits)}：")
            parts.append(f"--- 片段 {i + 1}（来源 {c['source']}）---\n{c['text'][:500]}")
        return "\n\n".join(parts)

    def stats(self) -> str:
        if not self._built:
            self.build()
        return f"知识库：{len(self.chunks)} 个片段（目录 {self.docs_dir}）"


# 全局单例（懒构建）
_index: Optional[RagIndex] = None
_index_lock = threading.Lock()


def get_index(docs_dir: Optional[str] = None) -> RagIndex:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = RagIndex(docs_dir=docs_dir)
    return _index


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    idx = get_index()
    print(idx.stats())
    q = sys.argv[1] if len(sys.argv) > 1 else "通信协议 v2.0 新增了什么"
    print()
    print(idx.query(q))
