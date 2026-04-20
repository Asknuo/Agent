"""
长会话摘要压缩模块

当会话消息数超过可配置阈值时，使用 LLM 将早期历史压缩为结构化摘要，
替代硬编码的"取最近 18 条"策略。

需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 5.1, 5.3
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from server.core.config import AppConfig
from server.core.models import ConversationSummary, Message, Session

logger = logging.getLogger("agent.summarizer")

# ── 摘要 Prompt ───────────────────────────────────────

_SUMMARY_SYSTEM_PROMPT = """\
你是一个对话摘要助手。请将以下客服对话历史压缩为结构化摘要。

要求：
1. 提取用户的核心诉求
2. 列出已解决和未解决的问题
3. 保留提及的订单号、手机型号等关键实体
4. 记录情绪变化趋势

以 JSON 格式输出：
{
  "summary_text": "摘要文本",
  "key_entities": ["实体1", "实体2"],
  "unresolved_issues": ["问题1"],
  "generated_at": <当前时间戳>
}
"""


# ── 安全反序列化 ──────────────────────────────────────

def safe_deserialize_summary(json_str: str) -> ConversationSummary:
    """
    安全反序列化摘要 JSON 字符串。

    非法 JSON 返回 ConversationSummary.empty() 而不抛异常。
    需求 5.3
    """
    if not json_str or not isinstance(json_str, str):
        return ConversationSummary.empty()
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return ConversationSummary.empty()
        return ConversationSummary.model_validate(data)
    except (json.JSONDecodeError, TypeError, ValueError, Exception) as e:
        logger.error("summary_deserialize_failed", extra={"extra_fields": {
            "error": str(e),
        }})
        return ConversationSummary.empty()


# ── Summarizer 类 ─────────────────────────────────────

class Summarizer:
    """长会话摘要压缩器"""

    def __init__(self, llm: ChatOpenAI, config: AppConfig):
        self._llm = llm
        self._threshold = config.summary_threshold        # 默认 20
        self._recent_count = config.summary_recent_count  # 默认 8

    async def check_and_summarize(self, session: Session) -> list[BaseMessage]:
        """
        检查是否需要摘要，返回用于 LLM 的消息列表。

        返回格式：
        - 需要摘要且成功时: [SystemMessage(摘要内容)] + 最近 N 条原始消息
        - 已有可复用摘要时: [SystemMessage(摘要内容)] + 最近 N 条原始消息
        - 不需要摘要时: 全部原始消息（转为 BaseMessage）
        - LLM 失败时: 最近 18 条原始消息（回退策略）
        """
        messages = session.messages
        msg_count = len(messages)
        existing_summary = session.context.conversation_summary

        # 已有摘要且消息数未重新超过阈值 → 复用（需求 1.7）
        if existing_summary and existing_summary.summary_text and msg_count <= self._threshold:
            return self._build_with_summary(existing_summary, messages)

        # 消息数未超阈值 → 不需要摘要
        if msg_count <= self._threshold:
            return self._messages_to_langchain(messages)

        # 需要生成/更新摘要（需求 1.1）
        try:
            summary = await self._generate_summary(messages)
            # 存储到 SessionContext（需求 1.4）
            session.context.conversation_summary = summary
            return self._build_with_summary(summary, messages)
        except Exception as e:
            # LLM 失败 → 回退到最近 18 条（需求 1.5）
            logger.warning("summary_generation_failed", exc_info=e)
            return self._messages_to_langchain(messages[-18:])

    async def _generate_summary(self, messages: list[Message]) -> ConversationSummary:
        """调用 LLM 生成结构化摘要（需求 1.2, 5.1）"""
        prompt = self._build_summary_prompt(messages)
        response = await self._llm.ainvoke(prompt)

        # 解析 LLM 返回的 JSON
        content = response.content if hasattr(response, "content") else str(response)
        summary = safe_deserialize_summary(content)

        # 如果解析出空摘要但 LLM 确实返回了内容，用原始文本作为摘要
        if not summary.summary_text and content.strip():
            summary = ConversationSummary(
                summary_text=content.strip()[:500],
                key_entities=[],
                unresolved_issues=[],
                generated_at=time.time(),
            )

        return summary

    def _build_summary_prompt(self, messages: list[Message]) -> list[BaseMessage]:
        """构建摘要生成的 Prompt"""
        # 将消息格式化为对话文本
        conversation_lines: list[str] = []
        for msg in messages:
            role_label = "用户" if msg.role == "user" else "客服"
            conversation_lines.append(f"{role_label}: {msg.content}")

        conversation_text = "\n".join(conversation_lines)

        return [
            SystemMessage(content=_SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=f"以下是需要压缩的对话历史：\n\n{conversation_text}"),
        ]

    def _build_with_summary(
        self, summary: ConversationSummary, messages: list[Message]
    ) -> list[BaseMessage]:
        """
        构建 [摘要SystemMessage] + 最近 N 条原始消息（需求 1.3）
        """
        # 摘要作为 SystemMessage
        summary_text = f"[对话历史摘要]\n{summary.summary_text}"
        if summary.key_entities:
            summary_text += f"\n关键实体: {', '.join(summary.key_entities)}"
        if summary.unresolved_issues:
            summary_text += f"\n未解决问题: {', '.join(summary.unresolved_issues)}"

        result: list[BaseMessage] = [SystemMessage(content=summary_text)]

        # 附加最近 N 条原始消息
        recent = messages[-self._recent_count:] if len(messages) > self._recent_count else messages
        result.extend(self._messages_to_langchain(recent))

        return result

    @staticmethod
    def _messages_to_langchain(messages: list[Message]) -> list[BaseMessage]:
        """将 Message 列表转为 LangChain BaseMessage 列表"""
        result: list[BaseMessage] = []
        for m in messages:
            if m.role == "user":
                result.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                result.append(AIMessage(content=m.content))
            elif m.role == "system":
                result.append(SystemMessage(content=m.content))
        return result
