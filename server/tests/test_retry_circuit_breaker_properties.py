"""
Property-based tests for RetryEngine and CircuitBreaker.

Property 8:  Exponential backoff — N+1 attempts with correct delay pattern
Property 10: Circuit breaker state transitions — CLOSED→OPEN→HALF_OPEN→CLOSED

Validates: Requirements 7.1, 7.4, 7.5
"""

from __future__ import annotations

import asyncio
import sys
import time
from unittest.mock import AsyncMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from server.retry import RetryEngine, RetryExhaustedError
from server.circuit_breaker import CircuitBreaker, CircuitOpenError


# ===========================================================================
# Helpers
# ===========================================================================


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_failing_then_ok(fail_count: int):
    """Return an async function that fails *fail_count* times then succeeds."""
    calls: list[float] = []

    async def func():
        calls.append(time.monotonic())
        if len(calls) <= fail_count:
            raise RuntimeError(f"fail #{len(calls)}")
        return "ok"

    return func, calls


# ===========================================================================
# Property 8: Exponential backoff
# Feature: enterprise-agent-optimization, Property 8: 指数退避重试
# ===========================================================================


@given(
    max_retries=st.integers(min_value=1, max_value=6),
    fail_count=st.integers(min_value=0, max_value=6),
    base_delay=st.sampled_from([0.0]),  # zero delay for fast tests
)
@settings(max_examples=25)
def test_retry_attempt_count(max_retries: int, fail_count: int, base_delay: float) -> None:
    """
    **Validates: Requirements 7.1**

    Property 8a: For any async function that fails *fail_count* times then
    succeeds, the retry engine SHALL execute exactly min(fail_count, max_retries) + 1
    attempts when fail_count <= max_retries, or max_retries + 1 attempts when
    fail_count > max_retries (raising RetryExhaustedError).
    """
    engine = RetryEngine(max_retries=max_retries, base_delay=base_delay)
    func, calls = _make_failing_then_ok(fail_count)

    if fail_count <= max_retries:
        result = _run(engine.execute(func))
        assert result == "ok"
        assert len(calls) == fail_count + 1, (
            f"Expected {fail_count + 1} attempts, got {len(calls)}"
        )
    else:
        try:
            _run(engine.execute(func))
            assert False, "Expected RetryExhaustedError"
        except RetryExhaustedError as exc:
            assert exc.attempts == max_retries + 1
            assert len(calls) == max_retries + 1, (
                f"Expected {max_retries + 1} attempts, got {len(calls)}"
            )


@given(
    max_retries=st.integers(min_value=1, max_value=4),
    base_delay=st.floats(min_value=0.001, max_value=0.01),
)
@settings(max_examples=15, deadline=None)
def test_retry_exponential_delay_pattern(max_retries: int, base_delay: float) -> None:
    """
    **Validates: Requirements 7.1**

    Property 8b: Between consecutive retry attempts the delay SHALL follow
    the pattern base_delay * 2^attempt (attempt starting from 0).
    We verify that measured inter-attempt gaps are at least the expected delay.
    """
    # Always fail so we exercise all retries
    func, calls = _make_failing_then_ok(max_retries + 1)
    engine = RetryEngine(max_retries=max_retries, base_delay=base_delay)

    try:
        _run(engine.execute(func))
    except RetryExhaustedError:
        pass

    assert len(calls) == max_retries + 1

    for i in range(1, len(calls)):
        gap = calls[i] - calls[i - 1]
        expected_delay = base_delay * (2 ** (i - 1))
        # Allow small timing tolerance (asyncio.sleep is not perfectly precise)
        assert gap >= expected_delay * 0.8, (
            f"Attempt {i}: gap {gap:.4f}s < expected {expected_delay:.4f}s"
        )


@given(max_retries=st.integers(min_value=0, max_value=5))
@settings(max_examples=15)
def test_retry_success_on_first_attempt_no_delay(max_retries: int) -> None:
    """
    **Validates: Requirements 7.1**

    Property 8c: When the function succeeds on the first attempt, the retry
    engine SHALL return immediately with exactly 1 attempt and no delay.
    """
    engine = RetryEngine(max_retries=max_retries, base_delay=1.0)
    func, calls = _make_failing_then_ok(0)  # never fails

    result = _run(engine.execute(func))
    assert result == "ok"
    assert len(calls) == 1


@given(max_retries=st.integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_retry_exhausted_wraps_last_exception(max_retries: int) -> None:
    """
    **Validates: Requirements 7.1**

    Property 8d: When all retries are exhausted, RetryExhaustedError SHALL
    contain the total attempt count and the last exception.
    """
    engine = RetryEngine(max_retries=max_retries, base_delay=0.0)
    call_count = 0

    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise ValueError(f"error-{call_count}")

    try:
        _run(engine.execute(always_fail))
        assert False, "Expected RetryExhaustedError"
    except RetryExhaustedError as exc:
        assert exc.attempts == max_retries + 1
        assert isinstance(exc.last_exception, ValueError)
        assert f"error-{max_retries + 1}" in str(exc.last_exception)


# ===========================================================================
# Property 10: Circuit breaker state transitions
# Feature: enterprise-agent-optimization, Property 10: 熔断器状态转换
# ===========================================================================


@given(failure_threshold=st.integers(min_value=1, max_value=10))
@settings(max_examples=25)
def test_circuit_closed_to_open_after_threshold(failure_threshold: int) -> None:
    """
    **Validates: Requirements 7.4**

    Property 10a: The circuit breaker SHALL transition from CLOSED to OPEN
    after exactly *failure_threshold* consecutive failures.
    Before that threshold, it SHALL remain CLOSED.
    """
    cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)

    async def fail():
        raise RuntimeError("boom")

    for i in range(failure_threshold):
        if i < failure_threshold - 1:
            # Not yet at threshold — state should still be CLOSED
            try:
                _run(cb.call(fail))
            except RuntimeError:
                pass
            assert cb.state == CircuitBreaker.CLOSED, (
                f"Expected CLOSED after {i + 1} failures, got {cb.state}"
            )
        else:
            # This failure hits the threshold — should transition to OPEN
            try:
                _run(cb.call(fail))
            except RuntimeError:
                pass
            assert cb.state == CircuitBreaker.OPEN, (
                f"Expected OPEN after {failure_threshold} failures, got {cb.state}"
            )


@given(failure_threshold=st.integers(min_value=1, max_value=10))
@settings(max_examples=25)
def test_circuit_open_rejects_immediately(failure_threshold: int) -> None:
    """
    **Validates: Requirements 7.4**

    Property 10b: While the circuit breaker is OPEN, calling it SHALL raise
    CircuitOpenError without executing the wrapped function.
    """
    cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)

    async def fail():
        raise RuntimeError("boom")

    # Drive to OPEN
    for _ in range(failure_threshold):
        try:
            _run(cb.call(fail))
        except RuntimeError:
            pass

    assert cb.state == CircuitBreaker.OPEN

    # Subsequent calls should raise CircuitOpenError, not RuntimeError
    call_executed = False

    async def should_not_run():
        nonlocal call_executed
        call_executed = True
        return "nope"

    try:
        _run(cb.call(should_not_run))
        assert False, "Expected CircuitOpenError"
    except CircuitOpenError:
        pass

    assert not call_executed, "Function should not have been executed while OPEN"


@given(
    failure_threshold=st.integers(min_value=1, max_value=5),
    recovery_timeout=st.floats(min_value=0.01, max_value=0.05),
)
@settings(max_examples=15, deadline=None)
def test_circuit_open_to_half_open_after_timeout(
    failure_threshold: int, recovery_timeout: float
) -> None:
    """
    **Validates: Requirements 7.5**

    Property 10c: After *recovery_timeout* seconds in OPEN state, the circuit
    breaker SHALL transition to HALF_OPEN.
    """
    cb = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )

    async def fail():
        raise RuntimeError("boom")

    # Drive to OPEN
    for _ in range(failure_threshold):
        try:
            _run(cb.call(fail))
        except RuntimeError:
            pass

    assert cb.state == CircuitBreaker.OPEN

    # Wait for recovery timeout
    time.sleep(recovery_timeout + 0.01)

    # Accessing state should now show HALF_OPEN
    assert cb.state == CircuitBreaker.HALF_OPEN


@given(
    failure_threshold=st.integers(min_value=1, max_value=5),
    recovery_timeout=st.floats(min_value=0.01, max_value=0.05),
)
@settings(max_examples=15, deadline=None)
def test_circuit_half_open_to_closed_on_success(
    failure_threshold: int, recovery_timeout: float
) -> None:
    """
    **Validates: Requirements 7.5**

    Property 10d: When in HALF_OPEN state, a successful call SHALL transition
    the circuit breaker back to CLOSED and reset the failure count.
    """
    cb = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )

    async def fail():
        raise RuntimeError("boom")

    async def succeed():
        return "ok"

    # Drive to OPEN
    for _ in range(failure_threshold):
        try:
            _run(cb.call(fail))
        except RuntimeError:
            pass

    assert cb.state == CircuitBreaker.OPEN

    # Wait for recovery timeout → HALF_OPEN
    time.sleep(recovery_timeout + 0.01)
    assert cb.state == CircuitBreaker.HALF_OPEN

    # Successful call → CLOSED
    result = _run(cb.call(succeed))
    assert result == "ok"
    assert cb.state == CircuitBreaker.CLOSED
    assert cb._failure_count == 0


@given(
    failure_threshold=st.integers(min_value=1, max_value=5),
    recovery_timeout=st.floats(min_value=0.01, max_value=0.05),
)
@settings(max_examples=15, deadline=None)
def test_circuit_half_open_to_open_on_failure(
    failure_threshold: int, recovery_timeout: float
) -> None:
    """
    **Validates: Requirements 7.5**

    Property 10e: When in HALF_OPEN state, a failed call SHALL transition
    the circuit breaker back to OPEN.
    """
    cb = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )

    async def fail():
        raise RuntimeError("boom")

    # Drive to OPEN
    for _ in range(failure_threshold):
        try:
            _run(cb.call(fail))
        except RuntimeError:
            pass

    assert cb.state == CircuitBreaker.OPEN

    # Wait for recovery timeout → HALF_OPEN
    time.sleep(recovery_timeout + 0.01)
    assert cb.state == CircuitBreaker.HALF_OPEN

    # Failed call → back to OPEN
    try:
        _run(cb.call(fail))
    except RuntimeError:
        pass

    assert cb.state == CircuitBreaker.OPEN


@given(
    failure_threshold=st.integers(min_value=2, max_value=6),
    successes_before_failures=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=25)
def test_circuit_success_resets_failure_count(
    failure_threshold: int, successes_before_failures: int
) -> None:
    """
    **Validates: Requirements 7.4**

    Property 10f: A successful call while CLOSED SHALL reset the consecutive
    failure count, so non-consecutive failures do not trigger the breaker.
    """
    cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=9999)

    async def fail():
        raise RuntimeError("boom")

    async def succeed():
        return "ok"

    # Accumulate failure_threshold - 1 failures (just below threshold)
    for _ in range(failure_threshold - 1):
        try:
            _run(cb.call(fail))
        except RuntimeError:
            pass

    assert cb.state == CircuitBreaker.CLOSED

    # Interleave successes — should reset failure count
    for _ in range(successes_before_failures):
        _run(cb.call(succeed))

    assert cb._failure_count == 0
    assert cb.state == CircuitBreaker.CLOSED


@given(failure_threshold=st.integers(min_value=1, max_value=10))
@settings(max_examples=25)
def test_circuit_open_error_has_positive_retry_after(failure_threshold: int) -> None:
    """
    **Validates: Requirements 7.4**

    Property 10g: When the circuit is OPEN, CircuitOpenError SHALL include
    a non-negative retry_after value.
    """
    cb = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    # Drive to OPEN
    for _ in range(failure_threshold):
        try:
            _run(cb.call(fail))
        except RuntimeError:
            pass

    assert cb.state == CircuitBreaker.OPEN

    try:
        _run(cb.call(fail))
        assert False, "Expected CircuitOpenError"
    except CircuitOpenError as exc:
        assert exc.retry_after >= 0, (
            f"retry_after should be non-negative, got {exc.retry_after}"
        )
