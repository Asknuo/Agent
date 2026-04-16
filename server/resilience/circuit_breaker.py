"""
熔断器 — 需求 7.4, 7.5

三态状态机:
  CLOSED  ──(连续 failure_threshold 次失败)──▶  OPEN
  OPEN    ──(recovery_timeout 秒后)──▶          HALF_OPEN
  HALF_OPEN ──(成功)──▶ CLOSED
  HALF_OPEN ──(失败)──▶ OPEN
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger("circuit_breaker")


class CircuitOpenError(Exception):
    """熔断器处于 OPEN 状态时抛出。"""

    def __init__(self, retry_after: float = 0.0):
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker is OPEN. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """异步熔断器，保护下游服务调用。"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state: str = self.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0

    # ── 公开属性 ──────────────────────────────────────

    @property
    def state(self) -> str:
        """当前状态（会自动检测 OPEN → HALF_OPEN 转换）。"""
        if (
            self._state == self.OPEN
            and time.time() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = self.HALF_OPEN
            logger.info("circuit_state_change", extra={"extra_fields": {
                "from": self.OPEN, "to": self.HALF_OPEN,
            }})
        return self._state

    # ── 核心方法 ──────────────────────────────────────

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        通过熔断器执行 *func*。

        - CLOSED / HALF_OPEN: 正常执行
        - OPEN: 直接抛出 CircuitOpenError
        """
        current = self.state  # 触发自动 OPEN→HALF_OPEN 检测

        if current == self.OPEN:
            retry_after = (
                self.recovery_timeout
                - (time.time() - self._last_failure_time)
            )
            raise CircuitOpenError(max(retry_after, 0.0))

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    # ── 内部状态转换 ──────────────────────────────────

    def _on_success(self) -> None:
        if self._state == self.HALF_OPEN:
            logger.info("circuit_state_change", extra={"extra_fields": {
                "from": self.HALF_OPEN, "to": self.CLOSED,
            }})
            self._state = self.CLOSED
        self._failure_count = 0

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            if self._state != self.OPEN:
                logger.warning("circuit_state_change", extra={"extra_fields": {
                    "from": self._state, "to": self.OPEN,
                    "failure_count": self._failure_count,
                }})
            self._state = self.OPEN

    def reset(self) -> None:
        """手动重置为 CLOSED（用于测试或运维操作）。"""
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
