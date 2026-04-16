"""
Property-based tests for tool exception handling in tool_node.

Property 9: Structured error on tool failure — exceptions produce structured
            error messages rather than propagating.

Validates: Requirements 7.2
"""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from langchain_core.messages import AIMessage, ToolMessage


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate arbitrary exception types and messages
_EXCEPTION_TYPES = [
    ValueError,
    TypeError,
    RuntimeError,
    KeyError,
    ConnectionError,
    TimeoutError,
    OSError,
    AttributeError,
    ZeroDivisionError,
    PermissionError,
]

exception_type_st = st.sampled_from(_EXCEPTION_TYPES)
exception_msg_st = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
tool_name_st = st.sampled_from([
    "search_knowledge_tool",
    "query_database_tool",
    "get_order_status_tool",
    "calculate_recycle_price_tool",
    "get_current_time_tool",
])
tool_call_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=8, max_size=32
)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_state_with_tool_call(tool_name: str, tool_call_id: str) -> dict:
    """Build a minimal AgentState with a pending tool call from an AIMessage."""
    from server.core.models import Sentiment, IntentCategory

    ai_msg = AIMessage(
        content="",
        tool_calls=[{"id": tool_call_id, "name": tool_name, "args": {}}],
    )
    return {
        "messages": [ai_msg],
        "user_text": "test",
        "sentiment": Sentiment.NEUTRAL,
        "intent": IntentCategory.GENERAL_CHAT,
        "confidence": 0.5,
        "language": "zh",
        "tools_used": [],
        "knowledge_refs": [],
        "agent_reply": "",
        "final_reply": "",
        "should_escalate": False,
    }


# ---------------------------------------------------------------------------
# Property 9 — Structured error on tool failure
# ---------------------------------------------------------------------------


@settings(max_examples=25, deadline=None)
@given(
    exc_type=exception_type_st,
    exc_msg=exception_msg_st,
    tool_name=tool_name_st,
    tool_call_id=tool_call_id_st,
)
def test_tool_exception_returns_structured_error(
    exc_type: type,
    exc_msg: str,
    tool_name: str,
    tool_call_id: str,
) -> None:
    """Feature: enterprise-agent-optimization, Property 9: 工具异常结构化处理

    For any exception thrown during tool execution, tool_node SHALL catch it
    and return a structured error message containing the exception type and
    description, rather than propagating the exception.
    """
    state = _build_state_with_tool_call(tool_name, tool_call_id)

    exc_instance = exc_type(exc_msg)
    # str() representation varies by exception type (e.g. KeyError adds repr quoting)
    exc_str = str(exc_instance)

    mock_executor = MagicMock()
    mock_executor.invoke.side_effect = exc_instance

    with (
        patch("server.agent.engine._tool_executor", mock_executor),
        patch("server.agent.engine._worker_llm", MagicMock()),  # skip _ensure_worker guard
    ):
        from server.agent.engine import tool_node

        result = tool_node(state)

    # 1. Must not propagate — we got a result dict
    assert isinstance(result, dict), "tool_node must return a dict, not raise"

    # 2. Must contain a messages list with exactly one ToolMessage
    msgs = result.get("messages", [])
    assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
    err_msg = msgs[0]
    assert isinstance(err_msg, ToolMessage), "Error message must be a ToolMessage"

    # 3. ToolMessage content must contain the exception type name
    assert exc_type.__name__ in err_msg.content, (
        f"Error content must include exception type '{exc_type.__name__}'"
    )

    # 4. ToolMessage content must contain the exception's str() representation
    assert exc_str in err_msg.content, (
        f"Error content must include exception str '{exc_str}'"
    )

    # 5. tool_call_id must match the original tool call
    assert err_msg.tool_call_id == tool_call_id, (
        f"tool_call_id mismatch: expected '{tool_call_id}', got '{err_msg.tool_call_id}'"
    )


@settings(max_examples=25, deadline=None)
@given(
    exc_type=exception_type_st,
    exc_msg=exception_msg_st,
    tool_name=tool_name_st,
    tool_call_id=tool_call_id_st,
)
def test_tool_exception_records_tool_in_tools_used(
    exc_type: type,
    exc_msg: str,
    tool_name: str,
    tool_call_id: str,
) -> None:
    """Feature: enterprise-agent-optimization, Property 9 (supplement):
    On tool failure the tool name is still recorded in tools_used."""
    state = _build_state_with_tool_call(tool_name, tool_call_id)

    mock_executor = MagicMock()
    mock_executor.invoke.side_effect = exc_type(exc_msg)

    with (
        patch("server.agent.engine._tool_executor", mock_executor),
        patch("server.agent.engine._worker_llm", MagicMock()),
    ):
        from server.agent.engine import tool_node

        result = tool_node(state)

    assert tool_name in result.get("tools_used", []), (
        f"tools_used should contain '{tool_name}' even on failure"
    )


@settings(max_examples=15, deadline=None)
@given(
    exc_type=exception_type_st,
    exc_msg=exception_msg_st,
    tool_name=tool_name_st,
    tool_call_id=tool_call_id_st,
)
def test_tool_exception_never_propagates(
    exc_type: type,
    exc_msg: str,
    tool_name: str,
    tool_call_id: str,
) -> None:
    """Feature: enterprise-agent-optimization, Property 9 (core invariant):
    tool_node must never let a tool exception propagate to the caller."""
    state = _build_state_with_tool_call(tool_name, tool_call_id)

    mock_executor = MagicMock()
    mock_executor.invoke.side_effect = exc_type(exc_msg)

    with (
        patch("server.agent.engine._tool_executor", mock_executor),
        patch("server.agent.engine._worker_llm", MagicMock()),
    ):
        from server.agent.engine import tool_node

        # This must NOT raise — that's the whole point of Property 9
        try:
            result = tool_node(state)
        except Exception as unexpected:
            raise AssertionError(
                f"tool_node propagated {type(unexpected).__name__}: {unexpected}"
            ) from unexpected

    assert "messages" in result
