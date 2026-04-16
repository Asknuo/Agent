"""
SQL 注入防护加固 — AST 级别 SQL 验证

使用 sqlparse 对 Agent 生成的 SQL 进行语法解析，
仅允许单条 SELECT 语句，限制子查询深度和 UNION 使用。
"""

from __future__ import annotations

import logging

import sqlparse
from sqlparse.sql import Parenthesis
from sqlparse.tokens import DML

logger = logging.getLogger("sql_guard")


class SQLGuard:
    """AST-level SQL validator (Requirements 6.1–6.4)."""

    def __init__(self, max_subquery_depth: int = 2, max_rows: int = 50) -> None:
        self.max_subquery_depth = max_subquery_depth
        self.max_rows = max_rows

    # ── public API ────────────────────────────────────

    def validate(self, sql: str) -> tuple[bool, str]:
        """Validate *sql* and return ``(ok, error_message)``.

        Returns ``(True, "")`` when the statement passes all checks.
        """
        sql = sql.strip()
        if not sql:
            return False, "SQL 语句不能为空"

        # Parse with sqlparse
        parsed = sqlparse.parse(sql)

        # Must be exactly one statement (Req 6.2)
        if len(parsed) != 1:
            return False, "仅允许单条 SQL 语句"

        stmt = parsed[0]

        # Must be a SELECT (Req 6.2)
        if stmt.get_type() != "SELECT":
            return False, "仅允许 SELECT 查询"

        # Reject UNION keyword (Req 6.3)
        if self._contains_union(sql):
            return False, "不允许使用 UNION"

        # Check subquery nesting depth (Req 6.3)
        depth = self._max_subquery_depth(stmt)
        if depth > self.max_subquery_depth:
            return (
                False,
                f"子查询嵌套层数 {depth} 超过限制({self.max_subquery_depth})",
            )

        return True, ""

    def apply_row_limit(self, sql: str) -> str:
        """Append ``LIMIT <max_rows>`` if the statement has no LIMIT clause (Req 6.4)."""
        sql_upper = sql.strip().upper()
        if "LIMIT" not in sql_upper:
            return f"{sql.rstrip(';')} LIMIT {self.max_rows}"
        return sql

    # ── internal helpers ──────────────────────────────

    @staticmethod
    def _contains_union(sql: str) -> bool:
        """Check for UNION keyword using sqlparse tokenisation."""
        for token in sqlparse.parse(sql)[0].flatten():
            if token.ttype is sqlparse.tokens.Keyword and token.normalized.startswith("UNION"):
                return True
        return False

    def _max_subquery_depth(self, token, depth: int = 0) -> int:
        """Recursively compute the maximum subquery nesting depth."""
        max_d = depth
        for child in getattr(token, "tokens", []):
            if isinstance(child, Parenthesis):
                # Check if the parenthesis contains a SELECT
                if self._parenthesis_has_select(child):
                    max_d = max(max_d, self._max_subquery_depth(child, depth + 1))
                else:
                    max_d = max(max_d, self._max_subquery_depth(child, depth))
            elif hasattr(child, "tokens"):
                max_d = max(max_d, self._max_subquery_depth(child, depth))
        return max_d

    @staticmethod
    def _parenthesis_has_select(paren: Parenthesis) -> bool:
        """Return True if *paren* directly contains a SELECT DML token."""
        for tok in paren.flatten():
            if tok.ttype is DML and tok.normalized == "SELECT":
                return True
        return False
