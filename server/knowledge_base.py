"""
RAG 知识库 — 三级检索策略 + FAISS 持久化

优先级：
1. 外部 RAG API（配了 RAG_API_URL 就走这个）
2. 本地 FAISS 向量检索（持久化到磁盘）
3. 关键词匹配（兜底）

文档切分策略：
- 使用 RecursiveCharacterTextSplitter
- 按 Markdown 标题 / 空行 / 句号等自然边界切分
- chunk_size=500, overlap=80，适合中文 FAQ + 价格表场景
"""

from __future__ import annotations
import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from server.cache import LRUCache, make_cache_key
from server.config import get_config
from server.models import KnowledgeEntry

logger = logging.getLogger("knowledge_base")

# ── 知识库检索缓存 ───────────────────────────────────

_search_cache: LRUCache | None = None


def _get_cache() -> LRUCache:
    """延迟初始化缓存实例，使用全局配置的 TTL 和 max_size。"""
    global _search_cache
    if _search_cache is None:
        cfg = get_config()
        _search_cache = LRUCache(max_size=cfg.cache_max_size, ttl=cfg.cache_ttl)
    return _search_cache

# ── FAISS 索引持久化路径 ─────────────────────────────

KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"
FAISS_INDEX_DIR = Path(__file__).parent.parent / "data" / "faiss_index"


# ── 从文件加载（原始条目，用于关键词兜底） ──────────────

def _load_from_files() -> list[KnowledgeEntry]:
    """从 data/knowledge/ 加载 .txt/.md 文件为 KnowledgeEntry"""
    entries: list[KnowledgeEntry] = []
    if not KNOWLEDGE_DIR.exists():
        return entries
    for i, fp in enumerate(sorted(KNOWLEDGE_DIR.glob("*"))):
        if fp.suffix.lower() not in (".txt", ".md"):
            continue
        try:
            text = fp.read_text(encoding="utf-8").strip()
            if not text:
                continue
            lines = text.split("\n")
            title = lines[0].strip()
            category, tags, start = "general", [], 1
            if len(lines) > 1 and ":" in lines[1] and len(lines[1]) < 100:
                parts = lines[1].split(":", 1)
                category = parts[0].strip()
                tags = [t.strip() for t in parts[1].split(",") if t.strip()]
                start = 2
            content = "\n".join(lines[start:]).strip() or title
            entries.append(KnowledgeEntry(
                id=f"kb-file-{i:03d}", title=title,
                content=content, category=category, tags=tags or [title],
            ))
        except Exception as e:
            logger.error("load_knowledge_file_failed", exc_info=e, extra={"extra_fields": {"file": str(fp)}})
    return entries


# ── 文档切分 + FAISS 向量化 ──────────────────────────

def _load_and_split_documents() -> list:
    """
    加载所有知识文件，用 RecursiveCharacterTextSplitter 切分。
    切分策略：
    - chunk_size=500：中文场景下约 250 个汉字，足够包含一个完整 FAQ 或一段价格表
    - chunk_overlap=80：保留上下文衔接，避免切断句子
    - separators：优先按 Markdown 标题、空行、句号切分
    """
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", "；", ".", " "],
        keep_separator=True,
    )

    all_docs: list[Document] = []

    # 1. 文件知识 — 内置条目已全部移到 data/knowledge/ 目录
    for entry in _knowledge_base:
        all_docs.append(Document(
            page_content=f"{entry.title}\n{entry.content}",
            metadata={"id": entry.id, "source": "file", "category": entry.category,
                       "tags": ",".join(entry.tags), "title": entry.title},
        ))

    # 2. 文件知识 — 切分长文档
    if not KNOWLEDGE_DIR.exists():
        return all_docs

    for fp in sorted(KNOWLEDGE_DIR.glob("*")):
        if fp.suffix.lower() not in (".txt", ".md"):
            continue
        try:
            text = fp.read_text(encoding="utf-8").strip()
            if not text:
                continue

            lines = text.split("\n")
            title = lines[0].strip()
            category, tags_str = "general", ""
            start = 1
            if len(lines) > 1 and ":" in lines[1] and len(lines[1]) < 100:
                parts = lines[1].split(":", 1)
                category = parts[0].strip()
                tags_str = parts[1].strip()
                start = 2

            body = "\n".join(lines[start:]).strip()
            if not body:
                continue

            chunks = splitter.split_text(body)
            for ci, chunk in enumerate(chunks):
                all_docs.append(Document(
                    page_content=f"[{title}]\n{chunk}",
                    metadata={
                        "id": f"kb-{fp.stem}-{ci:03d}",
                        "source": fp.name,
                        "category": category,
                        "tags": tags_str,
                        "title": title,
                        "chunk_index": ci,
                    },
                ))
        except Exception as e:
            logger.error("split_knowledge_file_failed", exc_info=e, extra={"extra_fields": {"file": str(fp)}})

    return all_docs


# ── 豆包多模态 Embedding 自定义类 ────────────────────

import httpx as _httpx
from langchain_core.embeddings import Embeddings as _Embeddings


class DoubaoMultimodalEmbeddings(_Embeddings):
    """
    调用豆包 ARK 的 /embeddings/multimodal 接口。
    将纯文本包装成 {"type":"text","text":"..."} 格式发送。
    """

    def __init__(self, model: str, api_key: str, base_url: str):
        self._model = model
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/embeddings/multimodal"

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """逐条调用 embedding API（多模态端点单条返回 dict 而非数组）"""
        all_embeddings: list[list[float]] = []

        for t in texts:
            resp = _httpx.post(
                self._url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json={"model": self._model, "input": [{"type": "text", "text": t}]},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()

            # 豆包多模态端点：data 可能是 dict 或 list
            result = data["data"]
            if isinstance(result, dict):
                all_embeddings.append(result["embedding"])
            elif isinstance(result, list):
                all_embeddings.append(result[0]["embedding"])
            else:
                raise ValueError(f"Unexpected data format: {type(result)}")

        return all_embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._call_api(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._call_api([text])[0]


def _make_embeddings():
    """
    创建 embedding 实例。
    如果是豆包多模态端点，使用自定义类调用 /embeddings/multimodal 接口；
    否则走标准 OpenAIEmbeddings。
    """
    cfg = get_config()
    model = cfg.embedding_model
    base_url = cfg.openai_base_url
    api_key = cfg.openai_api_key

    is_ark = model.startswith("ep-") or (base_url and "volces.com" in base_url)

    if is_ark:
        return DoubaoMultimodalEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url or "https://ark.cn-beijing.volces.com/api/v3",
        )

    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=model, api_key=api_key, base_url=base_url)


def _batch_embed(
    texts: list[str],
    embeddings_model: object,
    batch_size: int = 32,
    delay_ms: int = 100,
    max_retries: int = 2,
) -> list[list[float] | None]:
    """
    分批发送 Embedding 请求（需求 9.1, 9.2, 9.3）。

    - batch_size: 每批最多文档数（默认 32）
    - delay_ms: 批间延迟毫秒数（默认 100），避免 API 速率限制
    - max_retries: 每批最大重试次数（默认 2），失败后跳过该批

    返回与 texts 等长的向量列表，失败批次对应位置为 None。
    """
    all_vectors: list[list[float] | None] = []
    total_batches = math.ceil(len(texts) / batch_size) if texts else 0

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = start + batch_size
        batch_texts = texts[start:end]
        batch_vectors: list[list[float]] | None = None

        for attempt in range(max_retries + 1):
            try:
                batch_vectors = embeddings_model.embed_documents(batch_texts)
                break
            except Exception as e:
                if attempt < max_retries:
                    retry_delay = delay_ms / 1000 * (attempt + 1)
                    logger.warning("embedding_batch_retry", extra={"extra_fields": {
                        "batch_index": batch_idx,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": str(e),
                        "retry_delay_s": retry_delay,
                    }})
                    time.sleep(retry_delay)
                else:
                    logger.warning("embedding_batch_failed", extra={"extra_fields": {
                        "batch_index": batch_idx,
                        "batch_size": len(batch_texts),
                        "error": str(e),
                    }})

        if batch_vectors is not None:
            all_vectors.extend(batch_vectors)
        else:
            # Mark failed batch positions as None
            all_vectors.extend([None] * len(batch_texts))

        # Inter-batch delay to avoid API rate limits (需求 9.2)
        if batch_idx < total_batches - 1 and delay_ms > 0:
            time.sleep(delay_ms / 1000)

    return all_vectors


def _build_faiss_from_batch(docs: list, embeddings_model: object) -> Optional[object]:
    """
    Build a FAISS index using batch embedding instead of FAISS.from_documents.
    Skips documents whose embedding failed (returned None).
    """
    from langchain_community.vectorstores import FAISS

    cfg = get_config()
    texts = [doc.page_content for doc in docs]
    vectors = _batch_embed(
        texts,
        embeddings_model,
        batch_size=cfg.embedding_batch_size,
        delay_ms=cfg.embedding_batch_delay_ms,
    )

    # Filter out docs whose embedding failed
    valid_docs = []
    valid_vectors = []
    skipped = 0
    for doc, vec in zip(docs, vectors):
        if vec is not None:
            valid_docs.append(doc)
            valid_vectors.append(vec)
        else:
            skipped += 1

    if skipped > 0:
        logger.warning("embedding_batch_skipped_docs", extra={"extra_fields": {
            "skipped": skipped, "total": len(docs),
        }})

    if not valid_docs:
        return None

    # Build FAISS index from pre-computed embeddings
    text_embeddings = list(zip([d.page_content for d in valid_docs], valid_vectors))
    metadatas = [d.metadata for d in valid_docs]
    vs = FAISS.from_embeddings(text_embeddings, embeddings_model, metadatas=metadatas)
    return vs


def _build_or_load_faiss(docs: list) -> Optional[object]:
    """
    增量构建 FAISS 索引：
    - 首次：全量构建并保存（使用批处理 embedding）
    - 文档数不变：直接从本地加载
    - 文档数增加：加载已有索引，只对新增文档做 embedding，合并后保存
    - 文档数减少或其他变化：全量重建
    """
    try:
        from langchain_community.vectorstores import FAISS
        import json as _json

        embeddings = _make_embeddings()

        index_path = FAISS_INDEX_DIR
        meta_file = index_path / "doc_count.txt"
        ids_file = index_path / "doc_ids.json"

        # 当前文档 ID 集合
        current_ids = {doc.metadata.get("id", f"doc-{i}") for i, doc in enumerate(docs)}

        # 尝试加载已有索引
        if index_path.exists() and meta_file.exists():
            saved_count = int(meta_file.read_text().strip())

            # 加载已索引的文档 ID
            saved_ids: set[str] = set()
            if ids_file.exists():
                saved_ids = set(_json.loads(ids_file.read_text()))

            if saved_count == len(docs) and saved_ids == current_ids:
                # 完全一致，直接加载
                logger.info("faiss_load_local", extra={"extra_fields": {
                    "index_path": str(index_path), "doc_count": saved_count,
                }})
                vs = FAISS.load_local(
                    str(index_path), embeddings,
                    allow_dangerous_deserialization=True,
                )
                return vs

            elif saved_ids and current_ids > saved_ids:
                # 只有新增，增量构建（使用批处理 embedding）
                new_docs = [d for d in docs if d.metadata.get("id", "") not in saved_ids]
                logger.info("faiss_incremental_update", extra={"extra_fields": {
                    "existing": len(saved_ids), "new": len(new_docs),
                }})

                vs = FAISS.load_local(
                    str(index_path), embeddings,
                    allow_dangerous_deserialization=True,
                )
                if new_docs:
                    new_vs = _build_faiss_from_batch(new_docs, embeddings)
                    if new_vs is not None:
                        vs.merge_from(new_vs)

                    # 保存更新后的索引
                    vs.save_local(str(index_path))
                    meta_file.write_text(str(len(docs)))
                    ids_file.write_text(_json.dumps(sorted(current_ids)))
                    logger.info("faiss_incremental_done", extra={"extra_fields": {
                        "total_docs": len(docs),
                    }})

                return vs
            else:
                logger.info("faiss_doc_changed", extra={"extra_fields": {
                    "old_count": saved_count, "new_count": len(docs),
                }})

        if not docs:
            logger.warning("faiss_no_documents")
            return None

        # 全量构建（使用批处理 embedding）
        logger.info("faiss_building", extra={"extra_fields": {"doc_count": len(docs)}})
        vs = _build_faiss_from_batch(docs, embeddings)

        if vs is None:
            logger.error("faiss_build_failed_all_batches")
            return None

        # 持久化
        index_path.mkdir(parents=True, exist_ok=True)
        vs.save_local(str(index_path))
        meta_file.write_text(str(len(docs)))
        ids_file.write_text(_json.dumps(sorted(current_ids)))
        logger.info("faiss_saved", extra={"extra_fields": {"index_path": str(index_path)}})

        return vs

    except Exception as e:
        logger.error("faiss_init_failed", exc_info=e)
        return None


# ── 外部 RAG API 检索 ────────────────────────────────

def _resolve_json_path(data: Any, path: str) -> Any:
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            return None
    return data


async def _search_external_rag(query: str, top_k: int = 3) -> list[KnowledgeEntry] | None:
    cfg = get_config()
    rag_url = cfg.rag_api_url.strip()
    if not rag_url:
        return None

    rag_key = cfg.rag_api_key.strip()
    query_field = cfg.rag_query_field.strip()
    response_path = cfg.rag_response_path.strip()
    content_field = cfg.rag_content_field.strip()
    title_field = cfg.rag_title_field.strip()

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if rag_key:
        headers["Authorization"] = f"Bearer {rag_key}"

    body: dict[str, Any] = {query_field: query, "top_k": top_k}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(rag_url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = _resolve_json_path(data, response_path)
        if not isinstance(results, list):
            return None

        entries: list[KnowledgeEntry] = []
        for i, item in enumerate(results[:top_k]):
            if isinstance(item, dict):
                content = str(item.get(content_field, ""))
                title = str(item.get(title_field, f"外部知识-{i+1}"))
            elif isinstance(item, str):
                content, title = item, f"外部知识-{i+1}"
            else:
                continue
            if content:
                entries.append(KnowledgeEntry(
                    id=f"kb-ext-{i:03d}", title=title,
                    content=content, category="external", tags=["external"],
                ))
        return entries if entries else None

    except Exception as e:
        logger.error("external_rag_api_failed", exc_info=e)
        return None


# ── 全局状态 ─────────────────────────────────────────

_knowledge_base: list[KnowledgeEntry] = []
_id_to_entry: dict[str, KnowledgeEntry] = {}
_vector_store: Optional[object] = None
_all_docs: list = []  # 切分后的 Document 列表


def init_rag() -> None:
    """启动时初始化：加载文件 → 切分 → 向量化 → 持久化。清除搜索缓存。"""
    global _knowledge_base, _id_to_entry, _vector_store, _all_docs

    # 清除搜索缓存（知识库内容更新，需求 8.3）
    cache = _get_cache()
    cache.clear()

    # 1. 加载原始条目（用于关键词兜底和 API 返回）
    file_entries = _load_from_files()
    _knowledge_base = file_entries
    _id_to_entry = {e.id: e for e in _knowledge_base}
    logger.info("knowledge_base_loaded", extra={"extra_fields": {
        "total_entries": len(_knowledge_base), "file_entries": len(file_entries),
    }})

    # 2. 切分文档
    _all_docs = _load_and_split_documents()
    logger.info("documents_split", extra={"extra_fields": {"chunk_count": len(_all_docs)}})

    # 3. 构建/加载 FAISS 索引
    _vector_store = _build_or_load_faiss(_all_docs)

    cfg = get_config()
    rag_url = cfg.rag_api_url.strip()
    if rag_url:
        logger.info("external_rag_configured", extra={"extra_fields": {"url": rag_url}})
    else:
        logger.info("using_local_faiss")


# ── 统一检索入口 ─────────────────────────────────────

async def search_knowledge_async(query: str, top_k: int = 3) -> list[KnowledgeEntry]:
    """三级检索：缓存 → 外部 RAG → 本地 FAISS → 关键词"""
    cache = _get_cache()
    cache_key = make_cache_key(f"{query}::{top_k}")

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("search_cache_hit", extra={"extra_fields": {"query": query[:50]}})
        return cached

    ext_results = await _search_external_rag(query, top_k)
    if ext_results:
        cache.put(cache_key, ext_results)
        return ext_results

    if _vector_store is not None:
        try:
            results = _vector_store.similarity_search_with_score(query, k=top_k)
            entries = []
            for doc, score in results:
                meta = doc.metadata
                entries.append(KnowledgeEntry(
                    id=meta.get("id", "unknown"),
                    title=meta.get("title", ""),
                    content=doc.page_content,
                    category=meta.get("category", "general"),
                    tags=meta.get("tags", "").split(","),
                ))
            if entries:
                cache.put(cache_key, entries)
                return entries
        except Exception as e:
            logger.error("faiss_search_failed", exc_info=e)

    results = _keyword_search(query, top_k)
    if results:
        cache.put(cache_key, results)
    return results


def search_knowledge(query: str, top_k: int = 3) -> list[KnowledgeEntry]:
    """同步版本（供 @tool 调用），带缓存"""
    cache = _get_cache()
    cache_key = make_cache_key(f"{query}::{top_k}")

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("search_cache_hit_sync", extra={"extra_fields": {"query": query[:50]}})
        return cached

    if _vector_store is not None:
        try:
            results = _vector_store.similarity_search_with_score(query, k=top_k)
            entries = []
            for doc, score in results:
                meta = doc.metadata
                entries.append(KnowledgeEntry(
                    id=meta.get("id", "unknown"),
                    title=meta.get("title", ""),
                    content=doc.page_content,
                    category=meta.get("category", "general"),
                    tags=meta.get("tags", "").split(","),
                ))
            if entries:
                cache.put(cache_key, entries)
                return entries
        except Exception:
            pass

    results = _keyword_search(query, top_k)
    if results:
        cache.put(cache_key, results)
    return results


def _keyword_search(query: str, top_k: int = 3) -> list[KnowledgeEntry]:
    query_lower = query.lower()
    scored: list[tuple[KnowledgeEntry, float]] = []
    for entry in _knowledge_base:
        score = sum(3 for t in entry.tags if t in query_lower)
        if entry.title.lower() in query_lower:
            score += 2
        score += sum(1 for w in query_lower.split() if len(w) > 1 and w in entry.content)
        if score > 0:
            scored.append((entry, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [e for e, _ in scored[:top_k]]


def get_all_knowledge() -> list[KnowledgeEntry]:
    return _knowledge_base
