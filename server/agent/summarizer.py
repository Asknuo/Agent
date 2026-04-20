"""长会话摘要压缩模块（需求 1, 5）

完整的 Summarizer 类将在 Task 4.1 中实现。
此文件当前仅包含 safe_deserialize_summary 辅助函数。
"""

from __future__ import annotations

import json
import logging

from server.core.models import ConversationSummary

logger = logging.getLogger(__name__)


def safe_deserialize_summary(json_str: str) -> ConversationSummary:
    """
    安全反序列化 JSON 字符串为 ConversationSummary。

    对于任何非法输入（空字符串、截断 JSON、缺字段、类型错误等），
    返回 ConversationSummary.empty() 而不抛出异常。

    验证: 需求 5.3
    """
    if not json_str or not json_str.strip():
        return ConversationSummary.empty()

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.error("summary_deserialize_json_error", extra={"raw": json_str[:200]})
        return ConversationSummary.empty()

    if not isinstance(data, dict):
        logger.error("summary_deserialize_not_dict", extra={"type": type(data).__name__})
        return ConversationSummary.empty()

    try:
        return ConversationSummary.model_validate(data)
    except Exception:
        logger.error("summary_deserialize_validation_error", extra={"raw": json_str[:200]})
        return ConversationSummary.empty()
