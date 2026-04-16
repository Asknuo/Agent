"""
Property-based tests for JSONFormatter in server/logging_config.py.

Validates: Requirements 1.1, 1.3
"""

import json
import logging
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure server package is importable
sys.path.insert(0, ".")

from server.core.logging_config import (
    JSONFormatter,
    session_id_var,
    tenant_id_var,
    trace_id_var,
    user_id_var,
)

REQUIRED_FIELDS = {
    "timestamp",
    "level",
    "module",
    "message",
    "trace_id",
    "session_id",
    "user_id",
    "tenant_id",
}

LOG_LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
LEVEL_NAMES = {logging.DEBUG: "DEBUG", logging.INFO: "INFO", logging.WARNING: "WARNING", logging.ERROR: "ERROR"}

formatter = JSONFormatter()


# ---------------------------------------------------------------------------
# Property 1: JSON log format completeness
# **Validates: Requirements 1.1**
# All required fields present in output; level and context values match input.
# ---------------------------------------------------------------------------


@given(
    level=st.sampled_from(LOG_LEVELS),
    module_name=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N"))),
    message=st.text(min_size=1, max_size=100),
    trace_id=st.text(min_size=1, max_size=50),
    session_id=st.text(min_size=1, max_size=50),
    user_id=st.text(min_size=1, max_size=50),
    tenant_id=st.text(min_size=1, max_size=50),
)
@settings(max_examples=25)
def test_json_log_format_completeness(
    level: int,
    module_name: str,
    message: str,
    trace_id: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
) -> None:
    """
    **Validates: Requirements 1.1**

    Property 1: JSON log format completeness — all required fields present in output.
    For any combination of log level, module, message, and trace context values,
    the formatted output must be valid JSON containing every required field, and
    the level / context values must match the inputs.
    """
    # Set context variables
    t_trace = trace_id_var.set(trace_id)
    t_session = session_id_var.set(session_id)
    t_user = user_id_var.set(user_id)
    t_tenant = tenant_id_var.set(tenant_id)

    try:
        record = logging.LogRecord(
            name="test",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=message,
            args=None,
            exc_info=None,
        )
        record.module = module_name

        output = formatter.format(record)

        # Must be valid JSON
        parsed = json.loads(output)

        # All required fields must be present
        assert REQUIRED_FIELDS.issubset(parsed.keys()), (
            f"Missing fields: {REQUIRED_FIELDS - parsed.keys()}"
        )

        # Level must match input
        assert parsed["level"] == LEVEL_NAMES[level]

        # Context values must match what was set
        assert parsed["trace_id"] == trace_id
        assert parsed["session_id"] == session_id
        assert parsed["user_id"] == user_id
        assert parsed["tenant_id"] == tenant_id
    finally:
        # Reset context variables to avoid cross-test contamination
        trace_id_var.reset(t_trace)
        session_id_var.reset(t_session)
        user_id_var.reset(t_user)
        tenant_id_var.reset(t_tenant)


# ---------------------------------------------------------------------------
# Property 2: Exception log structure
# **Validates: Requirements 1.3**
# Exception entries contain type, message, and stack_summary.
# ---------------------------------------------------------------------------


@given(
    exc_type_name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
    exc_message=st.text(min_size=0, max_size=100),
)
@settings(max_examples=25)
def test_exception_log_structure(exc_type_name: str, exc_message: str) -> None:
    """
    **Validates: Requirements 1.3**

    Property 2: Exception log structure — exception entries contain type, stack_summary.
    When a log record includes exc_info, the formatted JSON must contain an "exception"
    key whose value has "type" (non-empty string), "message" (string), and
    "stack_summary" (non-empty list). The type must match the raised exception class.
    """
    # Dynamically create an exception type so we can vary the class name
    ExcClass = type(exc_type_name, (Exception,), {})

    try:
        raise ExcClass(exc_message)
    except ExcClass:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="error occurred",
        args=None,
        exc_info=exc_info,
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    # "exception" key must exist
    assert "exception" in parsed, "Missing 'exception' key in log output"

    exc_data = parsed["exception"]

    # Must contain type, message, stack_summary
    assert "type" in exc_data, "Missing 'type' in exception data"
    assert "message" in exc_data, "Missing 'message' in exception data"
    assert "stack_summary" in exc_data, "Missing 'stack_summary' in exception data"

    # type must be a non-empty string matching the exception class name
    assert isinstance(exc_data["type"], str) and len(exc_data["type"]) > 0
    assert exc_data["type"] == exc_type_name

    # message must be a string
    assert isinstance(exc_data["message"], str)

    # stack_summary must be a non-empty list
    assert isinstance(exc_data["stack_summary"], list)
    assert len(exc_data["stack_summary"]) > 0
