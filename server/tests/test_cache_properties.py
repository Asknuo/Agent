"""
Property-based tests for LRUCache in server/cache.py.

Property 11: Cache round trip + TTL — get within TTL returns value, after TTL returns None
Property 12: Pattern invalidation — matching keys removed, non-matching preserved
Property 13: LRU eviction — size never exceeds max, LRU entry evicted

Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

import sys
import time
from unittest.mock import patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from server.cache import LRUCache, make_cache_key


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_cache_keys = st.text(min_size=1, max_size=64, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-")
_cache_values = st.one_of(
    st.text(min_size=0, max_size=128),
    st.integers(),
    st.lists(st.integers(), max_size=10),
)
_ttl_values = st.integers(min_value=1, max_value=3600)
_max_sizes = st.integers(min_value=1, max_value=100)


# ---------------------------------------------------------------------------
# Property 11: Cache round trip + TTL
# ---------------------------------------------------------------------------

@given(key=_cache_keys, value=_cache_values, ttl=_ttl_values)
@settings(max_examples=50)
def test_get_within_ttl_returns_stored_value(key: str, value, ttl: int) -> None:
    """Put a value, then get it immediately — must return the same value."""
    cache = LRUCache(max_size=100, ttl=ttl)
    cache.put(key, value)
    assert cache.get(key) == value


@given(key=_cache_keys, value=_cache_values, ttl=_ttl_values)
@settings(max_examples=50)
def test_get_after_ttl_returns_none(key: str, value, ttl: int) -> None:
    """Put a value, then simulate time past TTL — get must return None."""
    cache = LRUCache(max_size=100, ttl=ttl)
    cache.put(key, value)

    # Simulate time advancing past TTL
    future = time.time() + ttl + 1
    with patch("server.cache.time.time", return_value=future):
        assert cache.get(key) is None


@given(key=_cache_keys, value=_cache_values)
@settings(max_examples=25)
def test_get_missing_key_returns_none(key: str, value) -> None:
    """Getting a key that was never stored must return None."""
    cache = LRUCache(max_size=100, ttl=300)
    assert cache.get(key) is None


@given(
    key=_cache_keys,
    value1=_cache_values,
    value2=_cache_values,
)
@settings(max_examples=25)
def test_put_overwrites_existing_key(key: str, value1, value2) -> None:
    """Putting the same key twice must return the latest value."""
    cache = LRUCache(max_size=100, ttl=300)
    cache.put(key, value1)
    cache.put(key, value2)
    assert cache.get(key) == value2


# ---------------------------------------------------------------------------
# Property 12: Pattern invalidation
# ---------------------------------------------------------------------------

@given(
    prefix=st.text(min_size=1, max_size=8, alphabet="abcdefghij"),
    suffix=st.text(min_size=1, max_size=8, alphabet="klmnopqrst"),
    pattern=st.text(min_size=1, max_size=4, alphabet="abcdefghij"),
    non_matching_keys=st.lists(
        st.text(min_size=1, max_size=16, alphabet="uvwxyz0123456789"),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=50)
def test_invalidate_pattern_removes_matching_keys(
    prefix: str, suffix: str, pattern: str, non_matching_keys: list[str],
) -> None:
    """
    Keys containing the pattern must be removed.
    Keys NOT containing the pattern must be preserved.
    """
    # Ensure non-matching keys truly don't contain the pattern
    non_matching_keys = [k for k in non_matching_keys if pattern not in k]

    cache = LRUCache(max_size=1000, ttl=300)

    # Insert matching keys (contain the pattern)
    matching_key = f"{prefix}{pattern}{suffix}"
    cache.put(matching_key, "match")

    # Insert non-matching keys
    for k in non_matching_keys:
        cache.put(k, "no_match")

    removed = cache.invalidate_pattern(pattern)

    # Matching key must be gone
    assert cache.get(matching_key) is None
    assert removed >= 1

    # Non-matching keys must still be present
    for k in non_matching_keys:
        assert cache.get(k) == "no_match"


@given(
    keys=st.lists(
        st.text(min_size=1, max_size=16, alphabet="abcdefghijklmnop"),
        min_size=1,
        max_size=20,
        unique=True,
    ),
    pattern=st.text(min_size=1, max_size=4, alphabet="abcdefghijklmnop"),
)
@settings(max_examples=50)
def test_invalidate_pattern_count_matches_removed(
    keys: list[str], pattern: str,
) -> None:
    """The return value of invalidate_pattern must equal the number of removed keys."""
    cache = LRUCache(max_size=1000, ttl=300)
    for k in keys:
        cache.put(k, "v")

    expected_removed = sum(1 for k in keys if pattern in k)
    size_before = cache.size

    actual_removed = cache.invalidate_pattern(pattern)

    assert actual_removed == expected_removed
    assert cache.size == size_before - actual_removed


# ---------------------------------------------------------------------------
# Property 13: LRU eviction
# ---------------------------------------------------------------------------

@given(
    max_size=st.integers(min_value=1, max_value=50),
    num_inserts=st.integers(min_value=1, max_value=200),
)
@settings(max_examples=50)
def test_cache_size_never_exceeds_max(max_size: int, num_inserts: int) -> None:
    """After any number of puts, cache size must never exceed max_size."""
    cache = LRUCache(max_size=max_size, ttl=300)
    for i in range(num_inserts):
        cache.put(f"key_{i}", i)
        assert cache.size <= max_size


@given(max_size=st.integers(min_value=2, max_value=30))
@settings(max_examples=50)
def test_lru_entry_evicted_first(max_size: int) -> None:
    """
    When cache is full and a new entry is inserted, the least-recently-used
    entry (the one inserted first and never accessed) must be evicted.
    """
    cache = LRUCache(max_size=max_size, ttl=300)

    # Fill the cache: key_0 is the oldest / LRU
    for i in range(max_size):
        cache.put(f"key_{i}", i)

    # Access all keys except key_0 to make them recently used
    for i in range(1, max_size):
        cache.get(f"key_{i}")

    # Insert one more — should evict key_0 (LRU)
    cache.put("new_key", "new_value")

    assert cache.get("key_0") is None, "LRU entry key_0 should have been evicted"
    assert cache.get("new_key") == "new_value"
    assert cache.size == max_size


@given(max_size=st.integers(min_value=2, max_value=30))
@settings(max_examples=50)
def test_accessing_key_prevents_eviction(max_size: int) -> None:
    """
    Accessing a key via get() moves it to most-recently-used position,
    so it should NOT be evicted when the cache overflows.
    """
    cache = LRUCache(max_size=max_size, ttl=300)

    # Fill the cache
    for i in range(max_size):
        cache.put(f"key_{i}", i)

    # Access key_0 to make it recently used
    cache.get("key_0")

    # Insert one more — should evict key_1 (now the LRU), NOT key_0
    cache.put("new_key", "new_value")

    assert cache.get("key_0") == 0, "key_0 was accessed and should NOT be evicted"
    assert cache.get("key_1") is None, "key_1 should be evicted as the new LRU"
    assert cache.size == max_size
