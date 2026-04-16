"""
Property-based tests for multi-tenant isolation.

Property 19: Tenant session isolation — sessions from tenant A not visible to tenant B
Property 20: Tenant rate limit independence — exhausting A's limit doesn't affect B

Validates: Requirements 13.2, 13.5
"""

from __future__ import annotations

import asyncio
import sys

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from server.models import Session, SessionStatus
from server.session_store import SessionStore
from server.rate_limiter import SlidingWindowRateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously for Hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_store() -> SessionStore:
    """Create an in-memory-only SessionStore (no DB URL)."""
    store = SessionStore(db_url="")
    _run(store.init())
    return store


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_tenant_ids = st.text(
    min_size=1, max_size=24, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
)

_user_ids = st.text(
    min_size=1, max_size=24, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
)

_session_ids = st.text(
    min_size=8, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
)

_statuses = st.sampled_from(list(SessionStatus))


# ---------------------------------------------------------------------------
# Property 19: Tenant session isolation
# Feature: enterprise-agent-optimization, Property 19: 多租户会话隔离
#
# For any two distinct tenant_ids, sessions created under tenant A SHALL NOT
# appear in query results for tenant B, and vice versa.
# Validates: Requirements 13.2
# ---------------------------------------------------------------------------

@given(
    tenant_a=_tenant_ids,
    tenant_b=_tenant_ids,
    user_id=_user_ids,
    count_a=st.integers(min_value=1, max_value=6),
    count_b=st.integers(min_value=1, max_value=6),
)
@settings(max_examples=100)
def test_tenant_sessions_isolated_by_list_by_user(
    tenant_a: str,
    tenant_b: str,
    user_id: str,
    count_a: int,
    count_b: int,
) -> None:
    """
    Sessions saved under tenant A must not appear when querying tenant B,
    even when the user_id is the same across both tenants.
    """
    assume(tenant_a != tenant_b)

    store = _make_store()

    ids_a: set[str] = set()
    ids_b: set[str] = set()

    for i in range(count_a):
        sid = f"ta_{i}"
        s = Session(id=sid, user_id=user_id, tenant_id=tenant_a)
        _run(store.save(s))
        ids_a.add(sid)

    for i in range(count_b):
        sid = f"tb_{i}"
        s = Session(id=sid, user_id=user_id, tenant_id=tenant_b)
        _run(store.save(s))
        ids_b.add(sid)

    # Query tenant A — must see only A's sessions
    results_a = _run(store.list_by_user(user_id, tenant_id=tenant_a))
    result_ids_a = {s.id for s in results_a}

    assert ids_a == result_ids_a, (
        f"Tenant A expected {ids_a}, got {result_ids_a}"
    )
    assert result_ids_a.isdisjoint(ids_b), (
        f"Tenant A results leaked B's sessions: {result_ids_a & ids_b}"
    )

    # Query tenant B — must see only B's sessions
    results_b = _run(store.list_by_user(user_id, tenant_id=tenant_b))
    result_ids_b = {s.id for s in results_b}

    assert ids_b == result_ids_b, (
        f"Tenant B expected {ids_b}, got {result_ids_b}"
    )
    assert result_ids_b.isdisjoint(ids_a), (
        f"Tenant B results leaked A's sessions: {result_ids_b & ids_a}"
    )


@given(
    tenant_a=_tenant_ids,
    tenant_b=_tenant_ids,
    user_id=_user_ids,
    count_a=st.integers(min_value=1, max_value=5),
    count_b=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=100)
def test_get_all_filters_by_tenant(
    tenant_a: str,
    tenant_b: str,
    user_id: str,
    count_a: int,
    count_b: int,
) -> None:
    """
    get_all(tenant_id=X) must return only sessions belonging to tenant X.
    Sessions from other tenants must not leak through.
    """
    assume(tenant_a != tenant_b)

    store = _make_store()

    ids_a: set[str] = set()
    ids_b: set[str] = set()

    for i in range(count_a):
        sid = f"ga_{i}"
        s = Session(id=sid, user_id=user_id, tenant_id=tenant_a)
        _run(store.save(s))
        ids_a.add(sid)

    for i in range(count_b):
        sid = f"gb_{i}"
        s = Session(id=sid, user_id=user_id, tenant_id=tenant_b)
        _run(store.save(s))
        ids_b.add(sid)

    # get_all for tenant A
    all_a = _run(store.get_all(tenant_id=tenant_a))
    all_a_ids = {s.id for s in all_a}
    assert ids_a == all_a_ids
    assert all_a_ids.isdisjoint(ids_b)

    # get_all for tenant B
    all_b = _run(store.get_all(tenant_id=tenant_b))
    all_b_ids = {s.id for s in all_b}
    assert ids_b == all_b_ids
    assert all_b_ids.isdisjoint(ids_a)


@given(
    tenant_a=_tenant_ids,
    tenant_b=_tenant_ids,
    num_sessions=st.integers(min_value=2, max_value=8),
)
@settings(max_examples=50)
def test_tenant_isolation_with_multiple_users(
    tenant_a: str,
    tenant_b: str,
    num_sessions: int,
) -> None:
    """
    Even with different users across tenants, session isolation holds.
    No session from tenant A should appear in tenant B's results.
    """
    assume(tenant_a != tenant_b)

    store = _make_store()

    ids_a: set[str] = set()
    ids_b: set[str] = set()

    for i in range(num_sessions):
        sid_a = f"mu_a_{i}"
        s_a = Session(id=sid_a, user_id=f"user_a_{i}", tenant_id=tenant_a)
        _run(store.save(s_a))
        ids_a.add(sid_a)

        sid_b = f"mu_b_{i}"
        s_b = Session(id=sid_b, user_id=f"user_b_{i}", tenant_id=tenant_b)
        _run(store.save(s_b))
        ids_b.add(sid_b)

    all_a = _run(store.get_all(tenant_id=tenant_a))
    all_a_ids = {s.id for s in all_a}
    assert ids_a == all_a_ids
    assert all_a_ids.isdisjoint(ids_b)

    all_b = _run(store.get_all(tenant_id=tenant_b))
    all_b_ids = {s.id for s in all_b}
    assert ids_b == all_b_ids
    assert all_b_ids.isdisjoint(ids_a)


# ---------------------------------------------------------------------------
# Property 20: Tenant rate limit independence
# Feature: enterprise-agent-optimization, Property 20: 租户级速率限制独立性
#
# For any two tenants with different configured rate limits, exhausting
# tenant A's rate limit SHALL NOT affect tenant B's remaining quota.
# Validates: Requirements 13.5
# ---------------------------------------------------------------------------

@given(
    tenant_a=_tenant_ids,
    tenant_b=_tenant_ids,
    user_id=_user_ids,
    max_requests=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=100)
def test_exhausting_tenant_a_does_not_affect_tenant_b(
    tenant_a: str,
    tenant_b: str,
    user_id: str,
    max_requests: int,
) -> None:
    """
    After fully exhausting tenant A's rate limit, tenant B must still
    have its full quota available.
    """
    assume(tenant_a != tenant_b)

    limiter = SlidingWindowRateLimiter(max_requests=max_requests, window_seconds=60)

    key_a = f"{tenant_a}:{user_id}"
    key_b = f"{tenant_b}:{user_id}"

    # Exhaust tenant A's quota
    for _ in range(max_requests):
        allowed, _ = limiter.is_allowed(key_a)
        assert allowed, "Tenant A should be allowed within quota"

    # Tenant A is now exhausted
    allowed_a, retry_after = limiter.is_allowed(key_a)
    assert not allowed_a, "Tenant A should be rate-limited after exhaustion"
    assert retry_after > 0

    # Tenant B must still have full quota
    for i in range(max_requests):
        allowed_b, _ = limiter.is_allowed(key_b)
        assert allowed_b, (
            f"Tenant B should be allowed (request {i+1}/{max_requests}) "
            f"but was rejected — tenant A's limit leaked"
        )


@given(
    tenant_a=_tenant_ids,
    tenant_b=_tenant_ids,
    user_id=_user_ids,
    limit_a=st.integers(min_value=1, max_value=20),
    limit_b=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100)
def test_separate_limiters_enforce_independent_quotas(
    tenant_a: str,
    tenant_b: str,
    user_id: str,
    limit_a: int,
    limit_b: int,
) -> None:
    """
    With per-tenant rate limiters having different max_requests, each
    tenant's quota is enforced independently.
    """
    assume(tenant_a != tenant_b)

    limiter_a = SlidingWindowRateLimiter(max_requests=limit_a, window_seconds=60)
    limiter_b = SlidingWindowRateLimiter(max_requests=limit_b, window_seconds=60)

    key_a = f"{tenant_a}:{user_id}"
    key_b = f"{tenant_b}:{user_id}"

    # Use up all of A's quota
    for _ in range(limit_a):
        allowed, _ = limiter_a.is_allowed(key_a)
        assert allowed

    # A is exhausted
    allowed_a, _ = limiter_a.is_allowed(key_a)
    assert not allowed_a

    # B still has its full independent quota
    for i in range(limit_b):
        allowed_b, _ = limiter_b.is_allowed(key_b)
        assert allowed_b, f"Tenant B rejected at request {i+1}/{limit_b}"

    # B is now exhausted too
    allowed_b, _ = limiter_b.is_allowed(key_b)
    assert not allowed_b


@given(
    tenant_a=_tenant_ids,
    tenant_b=_tenant_ids,
    user_a=_user_ids,
    user_b=_user_ids,
    max_requests=st.integers(min_value=2, max_value=30),
    requests_a=st.integers(min_value=1, max_value=30),
)
@settings(max_examples=100)
def test_shared_limiter_tenant_keyed_isolation(
    tenant_a: str,
    tenant_b: str,
    user_a: str,
    user_b: str,
    max_requests: int,
    requests_a: int,
) -> None:
    """
    Using a single SlidingWindowRateLimiter with composite keys
    ({tenant_id}:{user_id}), consuming requests under tenant A's key
    does not reduce tenant B's available quota.
    """
    assume(tenant_a != tenant_b)
    requests_a = min(requests_a, max_requests)

    limiter = SlidingWindowRateLimiter(max_requests=max_requests, window_seconds=60)

    key_a = f"{tenant_a}:{user_a}"
    key_b = f"{tenant_b}:{user_b}"

    # Consume some of A's quota
    for _ in range(requests_a):
        limiter.is_allowed(key_a)

    # B must still have full quota regardless of A's usage
    for i in range(max_requests):
        allowed_b, _ = limiter.is_allowed(key_b)
        assert allowed_b, (
            f"Tenant B rejected at request {i+1}/{max_requests} "
            f"after tenant A consumed {requests_a} requests"
        )
