"""
LRU 缓存层 — OrderedDict 实现，支持 TTL 过期和模式失效

需求 8.1: 缓存知识库检索结果
需求 8.2: 可配置过期时间（默认 300s）
需求 8.3: 知识库更新时清除相关缓存
需求 8.4: LRU 淘汰策略，上限默认 1000 条
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("cache")


def make_cache_key(text: str) -> str:
    """基于查询文本生成 SHA256 缓存键。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LRUCache:
    """
    基于 OrderedDict 的 LRU 缓存，支持 TTL 过期和模式失效。

    - get: 命中时移到末尾（最近使用），过期则删除返回 None
    - put: 插入/更新条目，超出 max_size 时淘汰最久未使用的条目
    - invalidate_pattern: 删除键中包含 pattern 的所有条目
    """

    def __init__(self, max_size: int = 1000, ttl: int = 300) -> None:
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max(max_size, 1)
        self._ttl = ttl

    # ── 读取 ──────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        ts, value = self._cache[key]
        if self._ttl > 0 and time.time() - ts > self._ttl:
            del self._cache[key]
            logger.debug("cache_expired", extra={"extra_fields": {"key": key[:16]}})
            return None
        self._cache.move_to_end(key)
        logger.debug("cache_hit", extra={"extra_fields": {"key": key[:16]}})
        return value

    # ── 写入 ──────────────────────────────────────────

    def put(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        while len(self._cache) > self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug("cache_evicted", extra={"extra_fields": {"key": evicted_key[:16]}})

    # ── 模式失效 ──────────────────────────────────────

    def invalidate_pattern(self, pattern: str) -> int:
        """删除键中包含 *pattern* 的所有条目，返回删除数量。"""
        keys_to_remove = [k for k in self._cache if pattern in k]
        for k in keys_to_remove:
            del self._cache[k]
        if keys_to_remove:
            logger.info("cache_invalidated", extra={"extra_fields": {
                "pattern": pattern, "removed": len(keys_to_remove),
            }})
        return len(keys_to_remove)

    # ── 全量清除 ──────────────────────────────────────

    def clear(self) -> None:
        count = len(self._cache)
        self._cache.clear()
        logger.info("cache_cleared", extra={"extra_fields": {"removed": count}})

    # ── 辅助 ──────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._cache)

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ts, _ = self._cache[key]
        if self._ttl > 0 and time.time() - ts > self._ttl:
            del self._cache[key]
            return False
        return True
