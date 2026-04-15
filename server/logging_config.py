"""
结构化日志系统 — JSON 格式输出 + contextvars 链路追踪

基于 Python 标准库 logging + 自定义 JSONFormatter，不引入额外依赖。
通过 contextvars 在异步调用链中传递 trace_id、session_id 等上下文信息。

需求覆盖: 1.1, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone

# ── 请求级上下文变量 ──────────────────────────────────

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="default")


class JSONFormatter(logging.Formatter):
    """
    将日志记录格式化为单行 JSON（需求 1.1）。

    每条日志包含: timestamp, level, module, message, trace_id,
    session_id, user_id, tenant_id。
    支持通过 extra={"extra_fields": {...}} 附加自定义字段。
    异常信息包含 type, message, stack_summary（最后 3 帧）。
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
            "trace_id": trace_id_var.get(""),
            "session_id": session_id_var.get(""),
            "user_id": user_id_var.get(""),
            "tenant_id": tenant_id_var.get("default"),
        }

        # 附加自定义字段
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_entry.update(record.extra_fields)

        # 异常信息（需求 1.3）
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "stack_summary": traceback.format_exception(
                    *record.exc_info
                )[-3:],
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """
    初始化日志系统（需求 1.4, 1.5）。

    Args:
        level: 日志级别，支持 DEBUG/INFO/WARNING/ERROR
        log_file: 可选的日志文件路径，为 None 时仅输出到 stdout
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    formatter = JSONFormatter()

    # stdout handler（需求 1.5）
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    # 文件 handler（需求 1.5）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
