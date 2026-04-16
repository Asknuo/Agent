"""
PostgreSQL 数据库接入层
Agent 通过 @tool 调用，自动根据用户问题生成 SQL 查询
"""

from __future__ import annotations
import logging
import re
from typing import Optional

from server.config import get_config
from server.sql_guard import SQLGuard

logger = logging.getLogger("database")

_engine = None
_allowed_tables: list[str] = []
_readonly: bool = True
_db_available: bool = False
_sql_guard: SQLGuard | None = None


def init_db() -> None:
    """启动时初始化数据库连接"""
    global _engine, _allowed_tables, _readonly, _db_available, _sql_guard

    config = get_config()

    # Initialise SQL guard with config values
    _sql_guard = SQLGuard(
        max_subquery_depth=config.sql_max_subquery_depth,
        max_rows=config.sql_max_rows,
    )

    db_url = config.db_url.strip()
    if not db_url:
        logger.info("db_not_configured")
        return

    try:
        from sqlalchemy import create_engine, text
        _engine = create_engine(db_url, pool_size=5, max_overflow=10, pool_pre_ping=True)

        # 测试连接
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        _allowed_tables = config.db_allowed_tables
        _readonly = config.db_readonly
        _db_available = True

        table_info = f"限定表: {_allowed_tables}" if _allowed_tables else "所有表"
        logger.info("db_connected", extra={"extra_fields": {
            "tables": table_info, "readonly": _readonly,
        }})

    except Exception as e:
        logger.error("db_connection_failed", exc_info=e)
        _db_available = False


def is_db_available() -> bool:
    return _db_available


def get_table_schema() -> str:
    """获取允许查询的表结构，供 Agent 了解数据库 schema"""
    if not _db_available or not _engine:
        return "数据库不可用"

    try:
        from sqlalchemy import inspect
        inspector = inspect(_engine)
        tables = _allowed_tables or inspector.get_table_names()
        schema_parts: list[str] = []

        for table in tables:
            try:
                columns = inspector.get_columns(table)
                cols_desc = ", ".join(f"{c['name']} {c['type']}" for c in columns)
                schema_parts.append(f"表 {table}: {cols_desc}")
            except Exception:
                schema_parts.append(f"表 {table}: (无法读取结构)")

        return "\n".join(schema_parts) if schema_parts else "无可用表"
    except Exception as e:
        return f"获取 schema 失败: {e}"


def _validate_sql(sql: str) -> Optional[str]:
    """SQL 安全校验，返回错误信息或 None（通过）。

    Uses SQLGuard for AST-level validation, then checks table allow-list.
    """
    # AST-level validation via SQLGuard
    if _sql_guard is not None:
        ok, err = _sql_guard.validate(sql)
        if not ok:
            return err
    else:
        # Fallback: basic keyword check when guard not initialised
        sql_upper = sql.strip().upper()
        if _readonly and not sql_upper.startswith("SELECT"):
            return "只读模式，仅允许 SELECT 查询"

    # 禁止危险操作 (belt-and-suspenders alongside SQLGuard)
    sql_upper = sql.strip().upper()
    dangerous = ["DROP ", "TRUNCATE ", "DELETE ", "ALTER ", "GRANT ", "REVOKE "]
    for d in dangerous:
        if d in sql_upper:
            return f"禁止执行危险操作: {d.strip()}"

    # 检查表名是否在允许列表内
    if _allowed_tables:
        table_refs = re.findall(r'\b(?:FROM|JOIN)\s+(\w+)', sql, re.IGNORECASE)
        for t in table_refs:
            if t.lower() not in [a.lower() for a in _allowed_tables]:
                return f"不允许查询表: {t}（允许: {', '.join(_allowed_tables)}）"

    return None


def execute_query(sql: str, limit: int = 20) -> str:
    """执行 SQL 查询，返回格式化结果"""
    if not _db_available or not _engine:
        return "数据库未连接"

    # 安全校验
    error = _validate_sql(sql)
    if error:
        return f"查询被拒绝: {error}"

    # Apply row limit via SQLGuard (Req 6.4)
    if _sql_guard is not None:
        sql = _sql_guard.apply_row_limit(sql)
    else:
        # Fallback: manual LIMIT
        sql_upper = sql.strip().upper()
        if "LIMIT" not in sql_upper and sql_upper.startswith("SELECT"):
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

    try:
        from sqlalchemy import text
        with _engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())

            if not rows:
                return "查询结果为空"

            # 格式化为表格
            header = " | ".join(columns)
            separator = "-" * len(header)
            lines = [header, separator]
            for row in rows:
                lines.append(" | ".join(str(v) for v in row))

            return f"共 {len(rows)} 条结果：\n" + "\n".join(lines)

    except Exception as e:
        return f"查询执行失败: {e}"
