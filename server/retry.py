"""
指数退避重试引擎 — 需求 7.1

延迟模式: base_delay * 2^attempt  (默认 1s, 2s, 4s)
每次重试记录 WARNING 日志，重试耗尽后抛出原始异常。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable, TypeVar

T = TypeVar("T")

logger = logging.getLogger("retry")


class RetryExhaustedError(Exception):
    """所有重试均失败后抛出，包装最后一次异常。"""

    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"All {attempts} attempts failed. Last error: {last_exception}"
        )


class RetryEngine:
    """可配置的异步指数退避重试器。"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        执行 *func* 并在失败时自动重试。

        总共最多执行 max_retries + 1 次（1 次初始 + max_retries 次重试）。
        延迟: base_delay * 2^attempt  (attempt 从 0 开始)
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "retry_attempt",
                        extra={"extra_fields": {
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "delay_s": delay,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }},
                    )
                    await asyncio.sleep(delay)

        # 所有重试耗尽
        raise RetryExhaustedError(self.max_retries + 1, last_exc)  # type: ignore[arg-type]
