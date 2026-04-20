"""
用户画像学习模块

基于对话内容推断用户画像维度：沟通风格、高频主题、满意度趋势。

需求: 2.1, 2.2, 2.4, 2.7
"""

from __future__ import annotations

import re
from collections import Counter

from server.core.models import (
    CommunicationStyle,
    IntentCategory,
    Message,
    Sentiment,
    UserProfile,
)

# ── 常量 ──────────────────────────────────────────────

# 正式用语标记
_FORMAL_MARKERS = ("您好", "请问", "麻烦", "烦请", "敬请", "贵公司", "尊敬")

# 表情符号正则（匹配 Unicode emoji 范围，排除 CJK 字符）
_EMOJI_PATTERN = re.compile(
    "[\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U00002702-\U000027b0"  # dingbats
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols extended-A
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U0000200d"             # zero width joiner
    "]+",
    flags=re.UNICODE,
)

# 情绪到满意度分数映射
_SENTIMENT_SCORE_MAP: dict[Sentiment, float] = {
    Sentiment.POSITIVE: 1.0,
    Sentiment.NEUTRAL: 0.6,
    Sentiment.CONFUSED: 0.4,
    Sentiment.NEGATIVE: 0.2,
    Sentiment.FRUSTRATED: 0.0,
}

# 满意度历史最大长度
_MAX_SATISFACTION_HISTORY = 20


# ── 画像分析函数 ──────────────────────────────────────

def analyze_communication_style(messages: list[Message]) -> CommunicationStyle:
    """
    基于三个信号推断沟通风格（需求 2.7）：

    规则：
    - 包含正式用语标记 → formal
    - 平均消息长度 > 100 字 → formal
    - 平均消息长度 < 30 字且不含正式用语 → concise
    - 包含表情符号 → casual
    - 其余情况 → casual
    """
    if not messages:
        return CommunicationStyle.CASUAL

    # 只分析用户消息
    user_messages = [m for m in messages if m.role == "user"]
    if not user_messages:
        return CommunicationStyle.CASUAL

    # 计算平均消息长度
    total_length = sum(len(m.content) for m in user_messages)
    avg_length = total_length / len(user_messages)

    # 检查正式用语标记
    has_formal_markers = any(
        marker in m.content for m in user_messages for marker in _FORMAL_MARKERS
    )

    # 检查表情符号
    has_emoji = any(_EMOJI_PATTERN.search(m.content) for m in user_messages)

    # 推断规则（需求 2.7）
    if has_formal_markers or avg_length > 100:
        return CommunicationStyle.FORMAL

    if avg_length < 30 and not has_formal_markers:
        if has_emoji:
            return CommunicationStyle.CASUAL
        return CommunicationStyle.CONCISE

    return CommunicationStyle.CASUAL


def extract_frequent_topics(
    messages: list[Message], current_intent: IntentCategory | None
) -> list[str]:
    """
    从历史意图分类中提取高频主题（需求 2.1, 2.2）。

    收集消息 metadata 中的 intent 字段，统计频次，
    将当前意图也计入，返回按频次降序排列的主题列表。
    """
    intent_counter: Counter[str] = Counter()

    for msg in messages:
        if msg.metadata and msg.metadata.intent:
            intent_counter[msg.metadata.intent.value] += 1

    # 将当前意图也计入
    if current_intent:
        intent_counter[current_intent.value] += 1

    # 按频次降序返回主题名称
    return [intent for intent, _ in intent_counter.most_common()]


def update_satisfaction(
    profile: UserProfile, sentiment: Sentiment
) -> list[float]:
    """
    根据情绪更新满意度趋势（需求 2.2）。

    将情绪映射为 0-1 分数，追加到 satisfaction_history，
    保留最近 N 条记录。返回更新后的列表。
    """
    score = _SENTIMENT_SCORE_MAP.get(sentiment, 0.5)
    history = list(profile.satisfaction_history)
    history.append(score)

    # 保留最近 N 条
    if len(history) > _MAX_SATISFACTION_HISTORY:
        history = history[-_MAX_SATISFACTION_HISTORY:]

    return history


# ── 画像 Prompt 注入 ──────────────────────────────────

# 风格提示文本映射（需求 2.4）
_STYLE_HINTS: dict[CommunicationStyle, str] = {
    CommunicationStyle.FORMAL: '请使用正式、礼貌的语气回复，称呼用户为"您"',
    CommunicationStyle.CASUAL: "可以使用轻松友好的语气，适当使用表情符号",
    CommunicationStyle.CONCISE: "请尽量简洁回复，避免冗长解释",
}



def build_profile_prompt_segment(profile: UserProfile) -> str:
    """
    生成画像提示片段，附加到 WORKER_PROMPT 末尾（需求 2.4）。

    包含：
    - communication_style 对应的风格提示文本
    - frequent_topics 前 3 个主题
    - interaction_count 数值
    """
    # 风格提示
    style = profile.communication_style
    if isinstance(style, str):
        # 兼容字符串值
        try:
            style = CommunicationStyle(style)
        except ValueError:
            style = CommunicationStyle.CASUAL

    hint = _STYLE_HINTS.get(style, _STYLE_HINTS[CommunicationStyle.CASUAL])

    # 高频主题（前 3 个）
    topics = "、".join(profile.frequent_topics[:3]) if profile.frequent_topics else "无"

    # 交互次数
    count = profile.interaction_count

    return (
        f"\n\n**用户画像：**\n"
        f"- 沟通风格偏好：{hint}\n"
        f"- 高频咨询主题：{topics}\n"
        f"- 历史交互次数：{count}\n"
    )
