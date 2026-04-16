"""
滑动窗口速率限制器 + FastAPI 中间件

- 基于 key（IP 或 user_id）的滑动窗口算法
- 可配置 max_requests 和 window_seconds
- 返回 (is_allowed, retry_after_seconds) 元组
- 中间件对 /api/chat 和 /api/chat/stream 施加限制
- 超限返回 HTTP 429 + Retry-After 头

需求覆盖: 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("rate_limiter")


class SlidingWindowRateLimiter:
    """
    滑动窗口速率限制器（需求 5.4）。

    每个 key 维护一个时间戳队列，窗口内超过 max_requests 则拒绝。
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        判断 key 是否允许请求。

        Returns:
            (True, 0) — 允许
            (False, retry_after) — 拒绝，retry_after 为建议等待秒数
        """
        now = time.time()
        window = self._windows[key]

        # 清除过期记录
        cutoff = now - self._window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= self._max_requests:
            retry_after = int(window[0] + self._window_seconds - now) + 1
            return False, max(retry_after, 1)

        window.append(now)
        return True, 0


# ── Rate-limit 中间件路径 ─────────────────────────────

RATE_LIMITED_PATHS: set[str] = {"/api/chat", "/api/chat/stream"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    速率限制中间件（需求 5.1, 5.3）。

    仅对 RATE_LIMITED_PATHS 中的端点生效。
    限制键优先使用 user_id（由 AuthMiddleware 设置），回退到客户端 IP。
    """

    def __init__(self, app: Any, limiter: SlidingWindowRateLimiter, enabled: bool = True) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not self.enabled:
            return await call_next(request)

        if request.url.path not in RATE_LIMITED_PATHS:
            return await call_next(request)

        # 限制键：优先 user_id，回退 IP（需求 5.1）
        key = getattr(request.state, "user_id", None) or (
            request.client.host if request.client else "unknown"
        )

        allowed, retry_after = self.limiter.is_allowed(key)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={"extra_fields": {"key": key, "retry_after": retry_after}},
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests, please try again later"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
