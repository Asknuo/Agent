"""
多租户中间件 — 从请求中提取 tenant_id 并注入上下文

提取优先级：X-Tenant-ID 请求头 > JWT payload > 默认值
设置到 contextvars 和 request.state 供下游使用。

需求覆盖: 13.1, 13.4
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.core.config import get_config
from server.core.logging_config import tenant_id_var

logger = logging.getLogger("tenant")


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Extract tenant_id from the request and propagate it via contextvars
    and request.state (Requirement 13.1, 13.4).

    Resolution order:
      1. X-Tenant-ID header
      2. request.state.tenant_id (set by AuthMiddleware from JWT)
      3. config.default_tenant_id
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        cfg = get_config()

        tenant_id = (
            request.headers.get("X-Tenant-ID")
            or getattr(request.state, "tenant_id", None)
            or cfg.default_tenant_id
        )

        # Propagate to contextvars for structured logging / downstream access
        tenant_id_var.set(tenant_id)
        request.state.tenant_id = tenant_id

        logger.debug("tenant_resolved", extra={"extra_fields": {
            "tenant_id": tenant_id,
            "path": request.url.path,
        }})

        return await call_next(request)
