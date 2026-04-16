"""
并发控制 — asyncio.Semaphore 限流 + 等待队列 + 请求超时

Requirements: 10.1, 10.2, 10.3
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

from fastapi import HTTPException

logger = logging.getLogger("concurrency")


class ConcurrencyController:
    """
    Semaphore-based concurrency limiter with bounded wait queue.

    * At most *max_concurrent* coroutines execute simultaneously (Req 10.1).
    * When the semaphore is fully acquired, up to *max_queue* extra callers
      may wait.  Beyond that the request is rejected with HTTP 503 (Req 10.2).
    * Each execution is wrapped in ``asyncio.wait_for`` with *timeout*
      seconds; on timeout HTTP 504 is raised (Req 10.3).
    """

    def __init__(
        self,
        max_concurrent: int = 20,
        max_queue: int = 50,
        timeout: int = 120,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._max_queue = max_queue
        self._timeout = timeout
        # Number of callers currently waiting to acquire the semaphore
        self._waiting: int = 0

    # ── public API ────────────────────────────────────

    async def execute(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Run *coro* under concurrency + timeout control."""

        # If the semaphore is fully acquired, check queue capacity
        if self._semaphore.locked():
            if self._waiting >= self._max_queue:
                logger.warning(
                    "concurrency_queue_full",
                    extra={
                        "extra_fields": {
                            "waiting": self._waiting,
                            "max_queue": self._max_queue,
                        }
                    },
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server busy, please retry later",
                )

        self._waiting += 1
        try:
            async with self._semaphore:
                self._waiting -= 1
                try:
                    return await asyncio.wait_for(coro, timeout=self._timeout)
                except asyncio.TimeoutError:
                    logger.error(
                        "request_timeout",
                        extra={
                            "extra_fields": {"timeout_s": self._timeout}
                        },
                    )
                    raise HTTPException(
                        status_code=504,
                        detail="Request timeout",
                    )
        except HTTPException:
            raise
        except BaseException:
            # Ensure waiting counter stays consistent on unexpected errors
            if self._waiting > 0:
                self._waiting -= 1
            raise

    # ── introspection helpers (useful for metrics / tests) ─

    @property
    def waiting(self) -> int:
        return self._waiting

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def max_queue(self) -> int:
        return self._max_queue

    @property
    def timeout(self) -> int:
        return self._timeout
