"""
集中式配置管理 — YAML 文件 + 环境变量覆盖

加载优先级：代码默认值 < config.yaml < 环境变量
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class AppConfig(BaseModel):
    """应用全局配置，所有可选项均有文档化默认值（需求 11.3）"""

    # ── LLM ───────────────────────────────────────────
    openai_api_key: str = ""
    openai_base_url: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # ── 日志 ──────────────────────────────────────────
    log_level: str = "INFO"
    log_file: Optional[str] = None

    # ── 认证 ──────────────────────────────────────────
    jwt_secret: str = "xiaozhi-dev-secret-key-change-in-production"
    jwt_issuer: str = "xiaozhi"
    auth_enabled: bool = False

    # ── 速率限制 ──────────────────────────────────────
    rate_limit_rpm: int = Field(default=30, ge=1)
    rate_limit_enabled: bool = True

    # ── 缓存 ──────────────────────────────────────────
    cache_ttl: int = Field(default=300, ge=0)
    cache_max_size: int = Field(default=1000, ge=1)

    # ── 并发 ──────────────────────────────────────────
    max_concurrent_requests: int = Field(default=20, ge=1)
    request_timeout: int = Field(default=120, ge=1)
    max_queue_size: int = Field(default=50, ge=0)

    # ── 数据库 ────────────────────────────────────────
    db_url: str = ""
    db_allowed_tables: list[str] = Field(default_factory=list)
    db_readonly: bool = True
    sql_max_rows: int = Field(default=50, ge=1)
    sql_max_subquery_depth: int = Field(default=2, ge=1)

    # ── Embedding 批处理 ──────────────────────────────
    embedding_batch_size: int = Field(default=32, ge=1)
    embedding_batch_delay_ms: int = Field(default=100, ge=0)

    # ── 熔断器 ────────────────────────────────────────
    circuit_breaker_threshold: int = Field(default=5, ge=1)
    circuit_breaker_recovery_s: int = Field(default=60, ge=1)

    # ── 重试 ──────────────────────────────────────────
    retry_max_attempts: int = Field(default=3, ge=0)
    retry_base_delay: float = Field(default=1.0, ge=0)

    # ── 多租户 ────────────────────────────────────────
    default_tenant_id: str = "default"

    # ── 外部 RAG API（可选）────────────────────────────
    rag_api_url: str = ""
    rag_api_key: str = ""
    rag_query_field: str = "query"
    rag_response_path: str = "data"
    rag_content_field: str = "content"
    rag_title_field: str = "title"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got '{v}'")
        return upper



# ── 环境变量 → 配置字段映射 ────────────────────────────

_ENV_MAPPING: dict[str, str] = {
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_BASE_URL": "openai_base_url",
    "OPENAI_MODEL": "openai_model",
    "EMBEDDING_MODEL": "embedding_model",
    "LOG_LEVEL": "log_level",
    "LOG_FILE": "log_file",
    "JWT_SECRET": "jwt_secret",
    "JWT_ISSUER": "jwt_issuer",
    "AUTH_ENABLED": "auth_enabled",
    "RATE_LIMIT_RPM": "rate_limit_rpm",
    "RATE_LIMIT_ENABLED": "rate_limit_enabled",
    "CACHE_TTL": "cache_ttl",
    "CACHE_MAX_SIZE": "cache_max_size",
    "MAX_CONCURRENT_REQUESTS": "max_concurrent_requests",
    "REQUEST_TIMEOUT": "request_timeout",
    "MAX_QUEUE_SIZE": "max_queue_size",
    "DB_URL": "db_url",
    "DB_ALLOWED_TABLES": "db_allowed_tables",
    "DB_READONLY": "db_readonly",
    "SQL_MAX_ROWS": "sql_max_rows",
    "SQL_MAX_SUBQUERY_DEPTH": "sql_max_subquery_depth",
    "EMBEDDING_BATCH_SIZE": "embedding_batch_size",
    "EMBEDDING_BATCH_DELAY_MS": "embedding_batch_delay_ms",
    "CIRCUIT_BREAKER_THRESHOLD": "circuit_breaker_threshold",
    "CIRCUIT_BREAKER_RECOVERY_S": "circuit_breaker_recovery_s",
    "RETRY_MAX_ATTEMPTS": "retry_max_attempts",
    "RETRY_BASE_DELAY": "retry_base_delay",
    "DEFAULT_TENANT_ID": "default_tenant_id",
    "RAG_API_URL": "rag_api_url",
    "RAG_API_KEY": "rag_api_key",
    "RAG_QUERY_FIELD": "rag_query_field",
    "RAG_RESPONSE_PATH": "rag_response_path",
    "RAG_CONTENT_FIELD": "rag_content_field",
    "RAG_TITLE_FIELD": "rag_title_field",
}

# Fields that need special type coercion from env string values
_BOOL_FIELDS = {"auth_enabled", "rate_limit_enabled", "db_readonly"}
_INT_FIELDS = {
    "rate_limit_rpm", "cache_ttl", "cache_max_size",
    "max_concurrent_requests", "request_timeout", "max_queue_size",
    "sql_max_rows", "sql_max_subquery_depth",
    "embedding_batch_size", "embedding_batch_delay_ms",
    "circuit_breaker_threshold", "circuit_breaker_recovery_s",
    "retry_max_attempts",
}
_FLOAT_FIELDS = {"retry_base_delay"}
_LIST_FIELDS = {"db_allowed_tables"}


def _coerce_env_value(field: str, raw: str) -> object:
    """Convert a raw env-var string to the appropriate Python type."""
    if field in _BOOL_FIELDS:
        return raw.lower() in ("true", "1", "yes")
    if field in _INT_FIELDS:
        return int(raw)
    if field in _FLOAT_FIELDS:
        return float(raw)
    if field in _LIST_FIELDS:
        return [t.strip() for t in raw.split(",") if t.strip()]
    return raw


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """
    从 YAML 加载配置，环境变量覆盖（需求 11.1）。
    缺失 YAML 文件时全部走环境变量 + 默认值。
    Pydantic 校验确保必填项和格式正确（需求 11.2, 11.4）。
    """
    data: dict[str, object] = {}

    # 1. YAML 文件
    path = Path(config_path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                data.update(loaded)

    # 2. 环境变量覆盖
    for env_key, config_key in _ENV_MAPPING.items():
        raw = os.getenv(env_key)
        if raw is not None:
            data[config_key] = _coerce_env_value(config_key, raw)

    return AppConfig(**data)


# ── 全局单例 ──────────────────────────────────────────

_config: AppConfig | None = None


def get_config() -> AppConfig:
    """获取已加载的全局配置，未初始化时自动加载。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def init_config(config_path: str = "config.yaml") -> AppConfig:
    """启动时显式初始化配置（由 main.py lifespan 调用）。"""
    global _config
    _config = load_config(config_path)
    return _config
