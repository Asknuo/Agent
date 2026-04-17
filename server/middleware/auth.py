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

# ── 用户存储（PostgreSQL + 内存回退） ────────────────

_pool: Any = None  # asyncpg.Pool | None
_fallback_users: dict[str, dict[str, Any]] = {
    "admin": {
        "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
        "role": "admin",
    },
}


async def init_user_store(db_url: str) -> None:
    """初始化用户存储的数据库连接池，启动时调用"""
    global _pool
    if not db_url:
        logger.info("user_store_no_db — using in-memory fallback")
        return
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
        logger.info("user_store_connected")
    except Exception as exc:
        logger.error("user_store_connect_failed", exc_info=exc)
        _pool = None


async def close_user_store() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    return _hash_password(password) == password_hash


async def create_user(username: str, password: str, role: str = "user") -> dict[str, Any] | None:
    """注册新用户，用户名已存在返回 None。优先写 PostgreSQL，失败回退内存。"""
    pw_hash = _hash_password(password)
    if _pool:
        try:
            async with _pool.acquire() as conn:
                existing = await conn.fetchrow(
                    "SELECT username FROM users WHERE username = $1", username,
                )
                if existing:
                    return None
                row = await conn.fetchrow(
                    "INSERT INTO users (username, password_hash, role) VALUES ($1, $2, $3) RETURNING id",
                    username, pw_hash, role,
                )
                return {"id": row["id"], "username": username, "role": role}
        except Exception as exc:
            logger.error("user_create_db_failed", exc_info=exc)
            # fall through to in-memory
    # 内存回退
    if username in _fallback_users:
        return None
    _fallback_users[username] = {"password_hash": pw_hash, "role": role}
    return {"username": username, "role": role}


async def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """验证用户名密码。优先查 PostgreSQL，失败回退内存。"""
    pw_hash = _hash_password(password)
    if _pool:
        try:
            async with _pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, username, password_hash, role FROM users WHERE username = $1",
                    username,
                )
                if row and _verify_password(password, row["password_hash"]):
                    return {"id": row["id"], "username": row["username"], "role": row["role"]}
                return None
        except Exception as exc:
            logger.error("user_auth_db_failed", exc_info=exc)
            # fall through to in-memory
    # 内存回退
    user = _fallback_users.get(username)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return {"username": username, "role": user["role"]}


def create_access_token(
    username: str, role: str, secret_key: str, issuer: str = "xiaozhi",
    expires_in: int = 86400, user_id: int | None = None,
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
    if user_id is not None:
        payload["user_id"] = user_id
    return jwt.encode(payload, secret_key, algorithm="HS256")


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT Bearer-token authentication middleware (Requirement 4.1)."""

    def __init__(self, app: Any, secret_key: str, issuer: str = "xiaozhi", enabled: bool = False) -> None:
        super().__init__(app)
        self.secret_key = secret_key
        self.issuer = issuer
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # When auth is disabled, try to extract user from token but don't reject on failure
        if not self.enabled:
            request.state.user_id = "anonymous"
            request.state.tenant_id = "default"
            # Best-effort: try to read JWT if present
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()
                if token:
                    try:
                        payload = jwt.decode(
                            token, self.secret_key, algorithms=["HS256"],
                            options={"verify_exp": True, "verify_iss": True},
                            issuer=self.issuer,
                        )
                        request.state.user_id = str(payload.get("user_id", "")) or payload.get("sub", "anonymous")
                        request.state.username = payload.get("sub", "anonymous")
                        request.state.tenant_id = payload.get("tenant_id", "default")
                    except JWTError:
                        pass  # auth disabled, ignore errors
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
            request.state.user_id = str(payload.get("user_id", "")) or payload.get("sub", "anonymous")
            request.state.username = payload.get("sub", "anonymous")
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
