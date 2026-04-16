"""
JWT 认证中间件

- Bearer Token 提取与 JWT 解码（python-jose）
- 签名、过期时间、issuer 验证
- 可配置的排除路径
- auth_enabled 开关（开发环境默认关闭）

需求覆盖: 4.1, 4.2, 4.3, 4.5
"""

from __future__ import annotations

import logging
from typing import Any

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("auth")

# Paths that bypass authentication
EXCLUDED_PATHS: set[str] = {"/api/health", "/metrics", "/docs", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT Bearer-token authentication middleware (Requirement 4.1)."""

    def __init__(self, app: Any, secret_key: str, issuer: str = "xiaozhi", enabled: bool = False) -> None:
        super().__init__(app)
        self.secret_key = secret_key
        self.issuer = issuer
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # When auth is disabled, pass through (dev mode)
        if not self.enabled:
            request.state.user_id = "anonymous"
            request.state.tenant_id = "default"
            return await call_next(request)

        # Skip excluded paths
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        # Extract Bearer token (Requirement 4.1)
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authentication token"},
            )

        # Decode and verify JWT (Requirement 4.3)
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={"verify_exp": True, "verify_iss": True},
                issuer=self.issuer,
            )
            request.state.user_id = payload.get("sub", "anonymous")
            request.state.tenant_id = payload.get("tenant_id", "default")
        except JWTError as exc:
            # Requirement 4.5 — log WARNING on auth failures
            logger.warning("auth_failed", extra={"extra_fields": {"error": str(exc), "path": request.url.path}})
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        return await call_next(request)


def verify_ws_token(token: str, secret_key: str, issuer: str = "xiaozhi") -> dict:
    """
    Verify a JWT token for WebSocket connections (Requirement 4.4).

    Returns the decoded payload on success.
    Raises JWTError on failure.
    """
    return jwt.decode(
        token,
        secret_key,
        algorithms=["HS256"],
        options={"verify_exp": True, "verify_iss": True},
        issuer=issuer,
    )
