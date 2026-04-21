"""多轮澄清检测与生成模块（需求 4）"""

from __future__ import annotations

import logging

from server.core.config import AppConfig
from server.core.models import IntentCategory, SessionContext

logger = logging.getLogger(__name__)

# ── 意图 → 澄清选项模板映射 ──────────────────────────

CLARIFICATION_TEMPLATES: dict[IntentCategory, list[str]] = {
    IntentCategory.REFUND_REQUEST: [
        "查询退款进度",
        "申请新的退款",
        "了解退款政策",
    ],
    IntentCategory.ORDER_STATUS: [
        "查询订单物流状态",
        "修改订单信息",
        "取消订单",
    ],
    IntentCategory.PRODUCT_INQUIRY: [
        "查询手机回收价格",
        "了解手机成色标准",
        "咨询购买二手手机",
    ],
    IntentCategory.TECHNICAL_SUPPORT: [
        "设备故障报修",
        "App 使用问题",
        "账号相关问题",
    ],
    IntentCategory.COMPLAINT: [
        "投诉服务态度",
        "投诉产品质量",
        "投诉物流问题",
    ],
}


class ClarificationDetector:
    """意图澄清检测器（需求 4.1, 4.2, 4.3, 4.6）"""

    def __init__(self, config: AppConfig) -> None:
        self._threshold = config.clarification_confidence_threshold
        self._max_rounds = 2

    def should_clarify(
        self, confidence: float, session_context: SessionContext
    ) -> bool:
        """
        判断是否需要澄清。

        当置信度 < 阈值 且 当前澄清轮次 < 最大轮次时返回 True。
        """
        return (
            confidence < self._threshold
            and session_context.clarification_round < self._max_rounds
        )

    def should_escalate_to_human(
        self, session_context: SessionContext
    ) -> bool:
        """连续 2 轮澄清后仍不明确时触发转人工。"""
        return session_context.clarification_round >= self._max_rounds

    def generate_clarification(
        self, intent: IntentCategory, user_text: str
    ) -> str:
        """
        根据意图生成选项式澄清问题。

        有模板时使用模板选项；模板缺失时生成通用澄清问题。
        """
        options = CLARIFICATION_TEMPLATES.get(intent)

        if options:
            numbered = "\n".join(
                f"{i}. {opt}" for i, opt in enumerate(options, 1)
            )
            return (
                f"我不太确定您的具体需求，请问您是想：\n"
                f"{numbered}\n"
                f"请选择或直接描述您的问题。"
            )

        # 模板缺失 → 通用澄清
        logger.warning(
            "clarification_template_missing",
            extra={"extra_fields": {"intent": intent.value}},
        )
        return "抱歉，我不太确定您的意思，能否再详细描述一下您的问题？"


def merge_clarification_messages(
    original_message: str, clarification_reply: str
) -> str:
    """
    合并原始模糊消息与用户澄清回复（需求 4.5）。

    合并后的文本同时包含原始消息内容和澄清回复内容，
    供 Supervisor 重新进行意图分类。
    """
    return f"{original_message}\n用户补充：{clarification_reply}"
