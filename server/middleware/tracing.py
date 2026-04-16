"""
链路追踪与 Prometheus 指标监控

- trace_middleware: 为每次请求生成 trace_id，注入 contextvars，添加 X-Trace-ID 响应头
- Prometheus 指标: 请求总数、延迟分布、活跃会话数、工具调用次数、节点耗时
- timed_node 装饰器: 包装 Agent 图节点，自动记录耗时并上报指标

需求覆盖: 2.1, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from functools import wraps
from typing import Any, Callable

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.core.logging_config import trace_id_var

logger = logging.getLogger("tracing")

# ── Prometheus 指标定义（需求 2.3）────────────────────

REQUEST_COUNT = Counter(
    "agent_requests_total",
    "Total HTTP requests",
    ["endpoint", "method", "status"],
)

REQUEST_LATENCY = Histogram(
    "agent_request_duration_ms",
    "HTTP request latency in milliseconds",
    ["endpoint", "method"],
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000],
)

ACTIVE_SESSIONS = Gauge(
    "agent_active_sessions",
    "Number of active sessions",
)

TOOL_CALLS = Counter(
    "agent_tool_calls_total",
    "Total tool invocations",
    ["tool_name", "status"],
)

NODE_DURATION = Histogram(
    "agent_node_duration_ms",
    "Agent graph node execution time in milliseconds",
    ["node"],
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000],
)


# ── Trace 中间件（需求 2.1）───────────────────────────

class TraceMiddleware(BaseHTTPMiddleware):
    """为每次 HTTP 请求生成唯一 trace_id 并注入上下文。"""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex
        trace_id_var.set(trace_id)

        start = time.time()
        response: Response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        response.headers["X-Trace-ID"] = trace_id

        endpoint = request.url.path
        method = request.method
        status = str(response.status_code)

        REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=status).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(duration_ms)

        return response


# ── timed_node 装饰器（需求 2.2, 2.4）────────────────

def timed_node(node_name: str) -> Callable:
    """
    包装 Agent 图节点函数，自动记录执行耗时到 Prometheus 指标。

    支持同步和异步节点函数。
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start) * 1000
                NODE_DURATION.labels(node=node_name).observe(duration_ms)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start) * 1000
                NODE_DURATION.labels(node=node_name).observe(duration_ms)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ── /metrics 端点辅助（需求 2.3）─────────────────────

def get_metrics_response() -> Response:
    """生成 Prometheus 兼容的 /metrics 响应。"""
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
