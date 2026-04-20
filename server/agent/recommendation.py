"""
主动知识推荐引擎 — 基于意图关联主题推送补充知识

根据当前意图从 RAG 管线中额外检索相关知识条目，
去重后附加在主回复之后，超时自动降级。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from server.core.models import IntentCategory, KnowledgeEntry, SessionContext

if TYPE_CHECKING:
    from server.core.config import AppConfig

logger = logging.getLogger("recommendation")

# ── 意图 → 推荐查询词映射（需求 3.2）─────────────────

INTENT_TOPIC_MAP: dict[IntentCategory, list[str]] = {
    IntentCategory.REFUND_REQUEST: ["退换货流程", "售后政策"],
    IntentCategory.ORDER_STATUS: ["配送时效", "物流查询"],
    IntentCategory.PRODUCT_INQUIRY: ["回收价格标准", "手机成色等级"],
    IntentCategory.TECHNICAL_SUPPORT: ["常见问题FAQ", "故障排查"],
    IntentCategory.COMPLAINT: ["投诉处理流程", "售后保障"],
}


class RecommendationEngine:
    """主动知识推荐引擎（需求 3）"""

    def __init__(self, config: "AppConfig"):
        self._enabled = config.recommendation_enabled
        self._timeout = config.recommendation_timeout
        self._max_items = 2

    async def get_recommendations(
        self,
        intent: IntentCategory,
        main_results: list[KnowledgeEntry],
        session_context: SessionContext,
    ) -> list[KnowledgeEntry]:
        """
        基于意图获取推荐知识，去重后返回最多 2 条。

        - 功能关闭时直接返回空列表（需求 3.5）
        - 超时自动放弃返回空列表（需求 3.7）
        - 基于 ID 去重，过滤与主查询结果重复的条目（需求 3.3）
        """
        if not self._enabled:
            return []

        try:
            return await asyncio.wait_for(
                self._fetch_recommendations(intent, main_results, session_context),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("recommendation_timeout", extra={"extra_fields": {
                "intent": intent.value,
                "timeout_s": self._timeout,
            }})
            return []
        except Exception as e:
            logger.error("recommendation_failed", exc_info=e, extra={"extra_fields": {
                "intent": intent.value,
            }})
            return []

    async def _fetch_recommendations(
        self,
        intent: IntentCategory,
        main_results: list[KnowledgeEntry],
        session_context: SessionContext,
    ) -> list[KnowledgeEntry]:
        """执行推荐检索并去重"""
        from server.data.knowledge_base import search_knowledge_async

        topics = INTENT_TOPIC_MAP.get(intent)
        if not topics:
            return []

        candidates: list[KnowledgeEntry] = []
        for topic in topics:
            results = await search_knowledge_async(topic, top_k=2)
            candidates.extend(results)

        deduplicated = self._deduplicate(candidates, main_results)
        return deduplicated[: self._max_items]

    def _deduplicate(
        self,
        candidates: list[KnowledgeEntry],
        main_results: list[KnowledgeEntry],
    ) -> list[KnowledgeEntry]:
        """基于 ID 去重，过滤与主查询结果重复的条目（需求 3.3）"""
        main_ids = {entry.id for entry in main_results}
        seen: set[str] = set()
        unique: list[KnowledgeEntry] = []

        for entry in candidates:
            if entry.id in main_ids:
                continue
            if entry.id in seen:
                continue
            seen.add(entry.id)
            unique.append(entry)

        return unique



def format_recommendations(
    main_reply: str,
    recommendations: list[KnowledgeEntry],
) -> str:
    """
    将推荐知识附加到主回复之后（需求 3.4）。

    - 非空推荐时附加"您可能还想了解"分隔标记
    - 空推荐时返回原始回复
    """
    if not recommendations:
        return main_reply

    lines = [
        "",
        "---",
        "💡 您可能还想了解：",
    ]
    for entry in recommendations:
        # 取 content 前 80 字符作为摘要
        snippet = entry.content[:80].replace("\n", " ")
        if len(entry.content) > 80:
            snippet += "..."
        lines.append(f"• {entry.title}：{snippet}")

    return main_reply + "\n".join(lines)
