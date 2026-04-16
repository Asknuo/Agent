"""
JWT 认证中间件 + 用户注册/登录

- Bearer Token 提取与 JWT 解码（python-jose）
- 签名、过期时间、issuer 验证
- 可配置的排除路径
- auth_enabled 开关（开发环境默认关闭）
- /api/login 和 /api/register 端点

需求覆盖: 4.1, 4.2, 4.3, 4.5
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("auth")

# Paths that bypass authentication (including login/register)
EXCLUDED_PATHS: set[str] = {
    "/api/health", "/metrics", "/docs", "/openapi.json",
    "/api/login", "/api/register",
}

# ── 用户存储（内存） ─────────────────────────────────

_users: dict[str, dict[str, Any]] = {
    # 预置 admin 用户
    "admin": {
        "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
        "role": "admin",
    },
}


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    return _hash_password(password) == password_hash


def create_user(username: str, password: str, role: str = "user") -> dict[str, Any] | None:
    """注册新用户，用户名已存在返回 None"""
    if username in _users:
        return None
    _users[username] = {
        "password_hash": _hash_password(password),
        "role": role,
    }
    return {"username": username, "role": role}


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """验证用户名密码，成功返回用户信息，失败返回 None"""
    user = _users.get(username)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return {"username": username, "role": user["role"]}


def create_access_token(
    username: str, role: str, secret_key: str, issuer: str = "xiaozhi",
    expires_in: int = 86400,
) -> str:
    """签发 JWT token"""
    now = time.time()
    payload = {
        "sub": username,
        "role": role,
        "iss": issuer,
        "iat": int(now),
        "exp": int(now + expires_in),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


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
