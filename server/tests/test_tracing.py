"""
Unit tests for trace middleware and Prometheus metrics recording.

Tests:
- trace_id generation and propagation (Requirement 2.1)
- Prometheus metric increments (Requirement 2.3)
- timed_node decorator timing (Requirement 2.2)

Validates: Requirements 2.1, 2.3
"""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

sys.path.insert(0, ".")

from prometheus_client import CollectorRegistry
from starlette.testclient import TestClient
from fastapi import FastAPI

from server.core.logging_config import trace_id_var
from server.middleware.tracing import (
    TraceMiddleware,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    NODE_DURATION,
    TOOL_CALLS,
    timed_node,
    get_metrics_response,
)


# ── Helpers ───────────────────────────────────────────


def _build_app() -> FastAPI:
    """Create a minimal FastAPI app with TraceMiddleware for testing."""
    test_app = FastAPI()
    test_app.add_middleware(TraceMiddleware)

    @test_app.get("/ping")
    async def ping():
        return {"trace_id": trace_id_var.get("")}

    @test_app.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    return test_app


# ── trace_id generation and propagation (Req 2.1) ────


class TestTraceIdGeneration:
    """Verify trace_id is generated, propagated, and returned in headers."""

    def test_auto_generates_trace_id(self):
        """When no X-Trace-ID header is sent, middleware generates one."""
        client = TestClient(_build_app())
        resp = client.get("/ping")

        assert resp.status_code == 200
        # Response must include X-Trace-ID header
        assert "x-trace-id" in resp.headers
        trace_id = resp.headers["x-trace-id"]
        assert len(trace_id) == 32  # uuid4().hex is 32 chars

    def test_propagates_client_trace_id(self):
        """When client sends X-Trace-ID, middleware uses it instead of generating."""
        client = TestClient(_build_app())
        custom_id = "my-custom-trace-id-12345"
        resp = client.get("/ping", headers={"X-Trace-ID": custom_id})

        assert resp.status_code == 200
        assert resp.headers["x-trace-id"] == custom_id

    def test_trace_id_available_in_contextvar(self):
        """The trace_id set by middleware is accessible via contextvars inside the handler."""
        client = TestClient(_build_app())
        custom_id = "ctx-check-abc"
        resp = client.get("/ping", headers={"X-Trace-ID": custom_id})

        body = resp.json()
        assert body["trace_id"] == custom_id

    def test_different_requests_get_different_trace_ids(self):
        """Each request without a client-supplied trace_id gets a unique one."""
        client = TestClient(_build_app())
        ids = set()
        for _ in range(5):
            resp = client.get("/ping")
            ids.add(resp.headers["x-trace-id"])
        assert len(ids) == 5


# ── Prometheus metric increments (Req 2.3) ───────────


class TestPrometheusMetrics:
    """Verify that TraceMiddleware increments Prometheus counters and histograms."""

    def test_request_count_incremented(self):
        """REQUEST_COUNT counter increments for each request."""
        client = TestClient(_build_app())

        before = REQUEST_COUNT.labels(
            endpoint="/ping", method="GET", status="200"
        )._value.get()

        client.get("/ping")

        after = REQUEST_COUNT.labels(
            endpoint="/ping", method="GET", status="200"
        )._value.get()

        assert after == before + 1

    def test_request_count_multiple_increments(self):
        """Multiple requests increment the counter accordingly."""
        client = TestClient(_build_app())

        before = REQUEST_COUNT.labels(
            endpoint="/ping", method="GET", status="200"
        )._value.get()

        n = 3
        for _ in range(n):
            client.get("/ping")

        after = REQUEST_COUNT.labels(
            endpoint="/ping", method="GET", status="200"
        )._value.get()

        assert after == before + n

    def test_request_latency_observed(self):
        """REQUEST_LATENCY histogram records observations."""
        client = TestClient(_build_app())

        before_count = REQUEST_LATENCY.labels(
            endpoint="/ping", method="GET"
        )._sum.get()

        client.get("/ping")

        after_count = REQUEST_LATENCY.labels(
            endpoint="/ping", method="GET"
        )._sum.get()

        # Sum should have increased (latency > 0)
        assert after_count > before_count

    def test_metrics_endpoint_returns_prometheus_format(self):
        """get_metrics_response returns text/plain Prometheus exposition format."""
        resp = get_metrics_response()
        assert resp.media_type.startswith("text/plain")
        body = resp.body.decode("utf-8")
        # Should contain at least one of our defined metrics
        assert "agent_requests_total" in body

    def test_tool_calls_counter(self):
        """TOOL_CALLS counter can be incremented and read back."""
        before = TOOL_CALLS.labels(
            tool_name="test_tool", status="ok"
        )._value.get()

        TOOL_CALLS.labels(tool_name="test_tool", status="ok").inc()

        after = TOOL_CALLS.labels(
            tool_name="test_tool", status="ok"
        )._value.get()

        assert after == before + 1


# ── timed_node decorator (Req 2.2) ───────────────────


class TestTimedNode:
    """Verify timed_node records node execution duration to NODE_DURATION."""

    def test_sync_node_records_duration(self):
        """Wrapping a sync function records its duration in NODE_DURATION."""
        before_count = NODE_DURATION.labels(node="test_sync")._sum.get()

        @timed_node("test_sync")
        def my_sync_node(state):
            time.sleep(0.02)
            return {"result": "ok"}

        result = my_sync_node({"input": "x"})

        after_count = NODE_DURATION.labels(node="test_sync")._sum.get()

        assert result == {"result": "ok"}
        # Duration sum should have increased by at least ~20ms
        assert after_count - before_count >= 15

    def test_async_node_records_duration(self):
        """Wrapping an async function records its duration in NODE_DURATION."""
        before_count = NODE_DURATION.labels(node="test_async")._sum.get()

        @timed_node("test_async")
        async def my_async_node(state):
            await asyncio.sleep(0.02)
            return {"result": "async_ok"}

        result = asyncio.run(my_async_node({"input": "y"}))

        after_count = NODE_DURATION.labels(node="test_async")._sum.get()

        assert result == {"result": "async_ok"}
        assert after_count - before_count >= 15

    def test_sync_node_propagates_exception(self):
        """timed_node still records duration even when the wrapped function raises."""
        before_count = NODE_DURATION.labels(node="test_err")._sum.get()

        @timed_node("test_err")
        def failing_node(state):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing_node({})

        after_count = NODE_DURATION.labels(node="test_err")._sum.get()
        # Duration should still be recorded despite the exception
        assert after_count > before_count

    def test_decorated_function_preserves_name(self):
        """timed_node preserves the original function name via functools.wraps."""

        @timed_node("whatever")
        def my_special_node(state):
            return state

        assert my_special_node.__name__ == "my_special_node"
