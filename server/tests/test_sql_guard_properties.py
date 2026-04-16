"""
Property-based tests for SQLGuard in server/sql_guard.py.

Property 7: SQL safety validation — accept valid single SELECTs,
reject non-SELECT/UNION/deep subqueries.

Validates: Requirements 6.2, 6.3
"""

import sys

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from server.sql_guard import SQLGuard

guard = SQLGuard(max_subquery_depth=2, max_rows=50)

# ---------------------------------------------------------------------------
# Strategies — reusable building blocks for generating SQL fragments
# ---------------------------------------------------------------------------

_table_names = st.sampled_from(["users", "orders", "products", "sessions", "items"])
_column_names = st.sampled_from(["id", "name", "status", "price", "created_at", "user_id"])
_operators = st.sampled_from(["=", ">", "<", ">=", "<=", "!="])
_int_literals = st.integers(min_value=0, max_value=9999).map(str)


def _where_clause() -> st.SearchStrategy[str]:
    """Generate an optional WHERE clause."""
    return st.one_of(
        st.just(""),
        st.tuples(_column_names, _operators, _int_literals).map(
            lambda t: f" WHERE {t[0]} {t[1]} {t[2]}"
        ),
    )


def _simple_select() -> st.SearchStrategy[str]:
    """Generate a valid single SELECT with no subqueries."""
    return st.tuples(
        st.lists(_column_names, min_size=1, max_size=3).map(", ".join),
        _table_names,
        _where_clause(),
    ).map(lambda t: f"SELECT {t[0]} FROM {t[1]}{t[2]}")


def _select_with_depth_1_subquery() -> st.SearchStrategy[str]:
    """SELECT … WHERE col IN (SELECT …) — depth 1."""
    return st.tuples(
        _column_names,
        _table_names,
        _column_names,
        _column_names,
        _table_names,
    ).map(
        lambda t: (
            f"SELECT {t[0]} FROM {t[1]} WHERE {t[2]} IN "
            f"(SELECT {t[3]} FROM {t[4]})"
        )
    )


def _select_with_depth_2_subquery() -> st.SearchStrategy[str]:
    """SELECT … WHERE col IN (SELECT … WHERE col IN (SELECT …)) — depth 2."""
    return st.tuples(
        _column_names, _table_names,
        _column_names, _column_names, _table_names,
        _column_names, _column_names, _table_names,
    ).map(
        lambda t: (
            f"SELECT {t[0]} FROM {t[1]} WHERE {t[2]} IN "
            f"(SELECT {t[3]} FROM {t[4]} WHERE {t[5]} IN "
            f"(SELECT {t[6]} FROM {t[7]}))"
        )
    )


def _select_with_depth_3_subquery() -> st.SearchStrategy[str]:
    """Depth-3 nesting — should be rejected."""
    return st.tuples(
        _column_names, _table_names,
        _column_names, _column_names, _table_names,
        _column_names, _column_names, _table_names,
        _column_names, _column_names, _table_names,
    ).map(
        lambda t: (
            f"SELECT {t[0]} FROM {t[1]} WHERE {t[2]} IN "
            f"(SELECT {t[3]} FROM {t[4]} WHERE {t[5]} IN "
            f"(SELECT {t[6]} FROM {t[7]} WHERE {t[8]} IN "
            f"(SELECT {t[9]} FROM {t[10]})))"
        )
    )


# ---------------------------------------------------------------------------
# Property 7a: Valid single SELECT statements are accepted
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(sql=_simple_select())
@settings(max_examples=25)
def test_valid_single_select_accepted(sql: str) -> None:
    """
    **Validates: Requirements 6.2**

    For any single SELECT statement with no subqueries and no UNION,
    the SQL guard SHALL accept it (return ok=True with empty error).
    """
    ok, err = guard.validate(sql)
    assert ok is True, f"Expected acceptance but got rejection: {err!r} for SQL: {sql}"
    assert err == ""


# ---------------------------------------------------------------------------
# Property 7b: SELECT with subquery depth ≤ 2 is accepted
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(sql=st.one_of(_select_with_depth_1_subquery(), _select_with_depth_2_subquery()))
@settings(max_examples=25)
def test_select_with_allowed_subquery_depth_accepted(sql: str) -> None:
    """
    **Validates: Requirements 6.3**

    For any single SELECT with subquery nesting depth ≤ 2,
    the SQL guard SHALL accept it.
    """
    ok, err = guard.validate(sql)
    assert ok is True, f"Expected acceptance but got rejection: {err!r} for SQL: {sql}"
    assert err == ""


# ---------------------------------------------------------------------------
# Property 7c: Non-SELECT statements are rejected
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


_non_select_stmts = st.sampled_from([
    "INSERT INTO users (name) VALUES ('test')",
    "UPDATE users SET name = 'test' WHERE id = 1",
    "DELETE FROM users WHERE id = 1",
    "DROP TABLE users",
    "CREATE TABLE t (id INT)",
    "ALTER TABLE users ADD COLUMN age INT",
    "TRUNCATE TABLE users",
])


@given(sql=_non_select_stmts)
@settings(max_examples=15)
def test_non_select_statements_rejected(sql: str) -> None:
    """
    **Validates: Requirements 6.2**

    For any non-SELECT SQL statement, the SQL guard SHALL reject it
    with a descriptive error message.
    """
    ok, err = guard.validate(sql)
    assert ok is False, f"Expected rejection but got acceptance for SQL: {sql}"
    assert len(err) > 0, "Error message must be non-empty on rejection"


# ---------------------------------------------------------------------------
# Property 7d: UNION keyword causes rejection
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(
    col=_column_names,
    table1=_table_names,
    table2=_table_names,
    union_variant=st.sampled_from(["UNION", "UNION ALL"]),
)
@settings(max_examples=25)
def test_union_rejected(col: str, table1: str, table2: str, union_variant: str) -> None:
    """
    **Validates: Requirements 6.3**

    For any SELECT containing a UNION keyword, the SQL guard SHALL
    reject it with a descriptive error message mentioning UNION.
    """
    sql = f"SELECT {col} FROM {table1} {union_variant} SELECT {col} FROM {table2}"
    ok, err = guard.validate(sql)
    assert ok is False, f"Expected rejection for UNION SQL: {sql}"
    assert "UNION" in err, f"Error message should mention UNION, got: {err!r}"


# ---------------------------------------------------------------------------
# Property 7e: Subquery depth > max is rejected
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(sql=_select_with_depth_3_subquery())
@settings(max_examples=25)
def test_deep_subquery_rejected(sql: str) -> None:
    """
    **Validates: Requirements 6.3**

    For any SELECT with subquery nesting depth > max_subquery_depth (2),
    the SQL guard SHALL reject it with a descriptive error message
    mentioning the nesting depth.
    """
    ok, err = guard.validate(sql)
    assert ok is False, f"Expected rejection for deep subquery SQL: {sql}"
    assert "嵌套" in err or "depth" in err.lower(), (
        f"Error message should mention nesting depth, got: {err!r}"
    )


# ---------------------------------------------------------------------------
# Property 7f: Multiple statements are rejected
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(
    sql1=_simple_select(),
    sql2=_simple_select(),
)
@settings(max_examples=25)
def test_multiple_statements_rejected(sql1: str, sql2: str) -> None:
    """
    **Validates: Requirements 6.2**

    For any input containing multiple SQL statements (separated by ;),
    the SQL guard SHALL reject it.
    """
    multi = f"{sql1}; {sql2}"
    ok, err = guard.validate(multi)
    assert ok is False, f"Expected rejection for multi-statement SQL: {multi}"
    assert len(err) > 0, "Error message must be non-empty on rejection"


# ---------------------------------------------------------------------------
# Property 7g: Empty / whitespace-only SQL is rejected
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(sql=st.from_regex(r"^\s*$", fullmatch=True))
@settings(max_examples=15)
def test_empty_sql_rejected(sql: str) -> None:
    """
    **Validates: Requirements 6.2**

    For any empty or whitespace-only input, the SQL guard SHALL reject it.
    """
    ok, err = guard.validate(sql)
    assert ok is False, f"Expected rejection for empty SQL: {sql!r}"
    assert len(err) > 0


# ---------------------------------------------------------------------------
# Property 7h: apply_row_limit appends LIMIT when absent
# Feature: enterprise-agent-optimization, Property 7: SQL 安全验证
# ---------------------------------------------------------------------------


@given(sql=_simple_select())
@settings(max_examples=25)
def test_apply_row_limit_adds_limit(sql: str) -> None:
    """
    **Validates: Requirements 6.4**

    For any valid SELECT without a LIMIT clause, apply_row_limit SHALL
    append LIMIT <max_rows>. If LIMIT is already present, the SQL is
    returned unchanged.
    """
    assume("LIMIT" not in sql.upper())
    result = guard.apply_row_limit(sql)
    assert result.rstrip().endswith(f"LIMIT {guard.max_rows}"), (
        f"Expected LIMIT {guard.max_rows} suffix, got: {result}"
    )


@given(
    sql=_simple_select(),
    limit_val=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=25)
def test_apply_row_limit_preserves_existing_limit(sql: str, limit_val: int) -> None:
    """
    **Validates: Requirements 6.4**

    For any SELECT that already contains a LIMIT clause,
    apply_row_limit SHALL return the SQL unchanged.
    """
    sql_with_limit = f"{sql} LIMIT {limit_val}"
    result = guard.apply_row_limit(sql_with_limit)
    assert result == sql_with_limit, (
        f"Expected unchanged SQL, got: {result}"
    )
