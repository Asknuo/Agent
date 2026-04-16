"""
Property-based tests for ConcurrencyController in server/concurrency.py.

Property 15: Concurrency limit — at most max_concurrent processing simultaneously,
             503 on queue overflow, 504 on timeout.

Validates: Requirements 10.1, 10.2
"""

from __future__ import annotations

import asyncio
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, ".")

from fastapi import HTTPException
from server.concurrency import ConcurrencyController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Property 15a: Concurrency limit enforcement
# ---------------------------------------------------------------------------


@given(
    max_concurrent=st.integers(min_value=1, max_value=10),
    num_tasks=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100, deadline=None)
def test_concurrency_limit_enforced(max_concurrent: int, num_tasks: int) -> None:
    """
    **Validates: Requirements 10.1**

    Property 15a: At no point in time should more than max_concurrent
    coroutines be executing inside the semaphore simultaneously.
    """
    controller = ConcurrencyController(
        max_concurrent=max_concurrent, max_queue=100, timeout=30
    )
    peak = 0

    async def run_all():
        nonlocal peak
        active = 0
        lock = asyncio.Lock()

        async def task():
            nonlocal active, peak
            async with lock:
                active += 1
                if active > peak:
                    peak = active
            # Yield control so other tasks can start
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

        coros = [controller.execute(task()) for _ in range(num_tasks)]
        results = await asyncio.gather(*coros, return_exceptions=True)
        # All tasks within capacity should succeed
        for r in results:
            assert not isinstance(r, Exception), f"Unexpected exception: {r}"

    _run(run_all())
    assert peak <= max_concurrent, (
        f"Peak concurrency {peak} exceeded max_concurrent {max_concurrent}"
    )


# ---------------------------------------------------------------------------
# Property 15b: 503 on queue overflow
# ---------------------------------------------------------------------------


@given(
    max_concurrent=st.integers(min_value=1, max_value=5),
    max_queue=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100, deadline=None)
def test_503_on_queue_overflow(max_concurrent: int, max_queue: int) -> None:
    """
    **Validates: Requirements 10.2**

    Property 15b: When the semaphore is fully acquired AND the wait queue
    is at capacity, the next call to execute() SHALL raise HTTPException
    with status_code 503.
    """
    controller = ConcurrencyController(
        max_concurrent=max_concurrent, max_queue=max_queue, timeout=30
    )

    async def run_overflow():
        barrier = asyncio.Event()

        async def blocking_task():
            await barrier.wait()

        # Fill all processing slots + queue
        total_capacity = max_concurrent + max_queue
        tasks = []
        for _ in range(total_capacity):
            tasks.append(asyncio.ensure_future(controller.execute(blocking_task())))
        # Give tasks time to start and fill slots/queue
        await asyncio.sleep(0.05)

        # The next request should get 503
        overflow_coro = blocking_task()
        try:
            await controller.execute(overflow_coro)
            assert False, "Expected HTTPException 503"
        except HTTPException as exc:
            assert exc.status_code == 503, f"Expected 503, got {exc.status_code}"
            # Close the unawaited coroutine to suppress RuntimeWarning
            overflow_coro.close()
        finally:
            # Release all blocked tasks
            barrier.set()
            await asyncio.gather(*tasks, return_exceptions=True)

    _run(run_overflow())


# ---------------------------------------------------------------------------
# Property 15c: All tasks within capacity complete successfully
# ---------------------------------------------------------------------------


@given(
    max_concurrent=st.integers(min_value=1, max_value=10),
    num_tasks=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100, deadline=None)
def test_tasks_within_capacity_complete(max_concurrent: int, num_tasks: int) -> None:
    """
    **Validates: Requirements 10.1**

    Property 15c: When the total number of submitted tasks is at most
    max_concurrent, all tasks SHALL complete successfully without error.
    """
    from hypothesis import assume
    assume(num_tasks <= max_concurrent)

    controller = ConcurrencyController(
        max_concurrent=max_concurrent, max_queue=50, timeout=30
    )

    async def run_all():
        results = []

        async def task(i: int):
            await asyncio.sleep(0.001)
            return f"result-{i}"

        coros = [controller.execute(task(i)) for i in range(num_tasks)]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for i, r in enumerate(results):
            assert not isinstance(r, Exception), f"Task {i} failed: {r}"
            assert r == f"result-{i}"

    _run(run_all())


# ---------------------------------------------------------------------------
# Property 15d: Timeout produces 504
# ---------------------------------------------------------------------------


@given(
    max_concurrent=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=50, deadline=None)
def test_timeout_produces_504(max_concurrent: int) -> None:
    """
    **Validates: Requirements 10.1, 10.2**

    Property 15d: When a coroutine exceeds the configured timeout,
    ConcurrencyController SHALL raise HTTPException with status_code 504.
    """
    # Use a very short timeout to trigger quickly
    controller = ConcurrencyController(
        max_concurrent=max_concurrent, max_queue=50, timeout=0.05
    )

    async def run_timeout():
        async def slow_task():
            await asyncio.sleep(10)  # Much longer than timeout

        try:
            await controller.execute(slow_task())
            assert False, "Expected HTTPException 504"
        except HTTPException as exc:
            assert exc.status_code == 504, f"Expected 504, got {exc.status_code}"

    _run(run_timeout())
