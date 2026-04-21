"""
基于 LangGraph 的 3-Agent 协作引擎

    ┌──────────────┐
    │  Supervisor   │  路由 + 情绪分析，决定走 Worker 还是直接转人工
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Worker       │  干活 Agent，带全部工具（ReAct 循环）
    │  tools: 5个   │
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Reviewer     │  质检 Agent，审核回复质量 & 情绪适配
    └──────────────┘
"""

from __future__ import annotations
import json as _json
import logging
import re
import time
from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from langchain_core.messages import ToolMessage

from server.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from server.core.config import get_config
from server.core.logging_config import session_id_var, user_id_var, trace_id_var
from server.core.models import (
    KnowledgeEntry, Message, MessageMetadata, Session,
    Sentiment, IntentCategory, SessionStatus, UserProfile,
)
from server.resilience.retry import RetryEngine, RetryExhaustedError
from server.data.session_store import SessionStore
from server.agent.tools import ALL_TOOLS
from server.middleware.tracing import TOOL_CALLS, timed_node, collect_agent_event, start_event_collection, get_collected_events

logger = logging.getLogger("agent")


def _make_llm(**kwargs: Any) -> ChatOpenAI:
    cfg = get_config()
    return ChatOpenAI(
        model=cfg.openai_model,
        api_key=cfg.openai_api_key,
        base_url=cfg.openai_base_url or None,
        **kwargs,
    )


# ── Retry + Circuit Breaker ──────────────────────────

_retry_engine: RetryEngine | None = None
_circuit_breaker: CircuitBreaker | None = None


def _get_retry_engine() -> RetryEngine:
    global _retry_engine
    if _retry_engine is None:
        cfg = get_config()
        _retry_engine = RetryEngine(
            max_retries=cfg.retry_max_attempts,
            base_delay=cfg.retry_base_delay,
        )
    return _retry_engine


def _get_circuit_breaker() -> CircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is None:
        cfg = get_config()
        _circuit_breaker = CircuitBreaker(
            failure_threshold=cfg.circuit_breaker_threshold,
            recovery_timeout=float(cfg.circuit_breaker_recovery_s),
        )
    return _circuit_breaker


async def _resilient_llm_invoke(llm: Any, messages: list, label: str = "llm") -> Any:
    """
    通过 circuit breaker + retry 调用 LLM。

    失败链: 调用 → 重试(指数退避) → 熔断检测 → 抛出
    """
    cb = _get_circuit_breaker()
    retry = _get_retry_engine()

    async def _invoke():
        return await cb.call(lambda: llm.ainvoke(messages))

    try:
        return await retry.execute(_invoke)
    except (RetryExhaustedError, CircuitOpenError) as exc:
        logger.error("llm_call_failed", extra={"extra_fields": {
            "label": label,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }})
        raise


# ── Prompts ───────────────────────────────────────────

SUPERVISOR_PROMPT = """你是智能客服团队的主管。分析用户消息，完成以下任务：

1. **路由决策**（next）：
   - "worker"：交给客服 Agent 处理（大多数情况）
   - "human"：直接转人工（仅当用户明确要求转人工时）

2. **情绪分析**（sentiment）：判断用户情绪
   - "positive"：积极、满意、感谢
   - "neutral"：中性、普通咨询
   - "negative"：不满、差评、投诉
   - "frustrated"：焦急、等待过久、反复追问
   - "confused"：困惑、不理解、不明白

3. **意图分类**（intent）：判断用户意图
   - "product_inquiry"：产品/价格/功能咨询
   - "order_status"：订单/物流/配送查询
   - "refund_request"：退款/退货请求
   - "technical_support"：技术问题/故障报修
   - "complaint"：投诉/举报
   - "general_chat"：闲聊/通用对话
   - "human_handoff"：要求转人工
   - "feedback"：建议/反馈

4. **置信度**（confidence）：对意图分类的置信度，0.0 到 1.0 之间的数值

只回复 JSON，不要其他内容：
{"next": "worker", "sentiment": "neutral", "intent": "general_chat", "confidence": 0.8}"""

WORKER_PROMPT = """你是"小智"，专业友善的AI智能客服。

可用工具：
- search_knowledge_tool：查知识库（政策、会员、支付、配送、回收价格等）
- query_order：查订单状态（模拟数据）
- query_database：查 PostgreSQL 数据库（真实业务数据，只能 SELECT）
- get_db_schema：获取数据库表结构（不确定表名/字段时先调这个）
- calculate_refund：计算退款
- create_ticket：创建工单
- escalate_to_human：转人工

行为准则：
- 遇到任何产品/政策/价格/回收相关问题，必须先调用 search_knowledge_tool 查知识库，不要凭空回答
- 用户问价格、回收报价时，必须先查知识库，知识库里有完整的价格表
- 需要查真实业务数据（订单、用户、商品等），用 query_database
- 不确定表结构时，先调 get_db_schema 了解有哪些表和字段

**货币单位（极其重要）：**
- 本系统所有价格数据（数据库和知识库）的货币单位均为 IDR（印尼盾），显示时必须带上 "Rp" 前缀，例如 "Rp 3,836,000"
- 绝对不要将价格转换为人民币、美元或其他货币，也不要省略货币单位
- 如果查询结果中的价格没有货币标识，默认就是印尼盾 IDR

**数据库表业务说明（查询时务必区分）：**
- recycling_price_standards：回收报价标准表（给用户看的回收价），字段 min_price/max_price 是回收价区间，channel 为 IB 或 BC
- recycling_prices：回收基础价格表（内部参考），字段 min_price/max_price，含 ratio 系数
- crm_base_prices：平台卖出定价表（二手手机售卖价格），字段 platform_price_ib/platform_price_bc 是卖出价，brand_new_price 是全新价
- phone_inventory：手机库存/质检表，recycling_price 是实际回收价，selling_price 是卖出价，含质检详情
- user_order：用户购买订单（买二手手机的订单），amount 是订单金额
- 重要：用户问"回收价格/回收多少钱"时，查 recycling_price_standards；用户问"买手机/售价"时，查 crm_base_prices 或 phone_inventory.selling_price。绝对不要混淆回收价和卖出价！
- 根据用户情绪调整语气，焦急时先安抚
- 回复简洁有条理
- 不要在没有查询知识库的情况下就说"无法回答"或"转人工"

**回复格式规则：**
- 回复要简洁精炼，避免大段文字和大表格
- 如果查到多个型号的价格，只列出关键信息，用简洁的列表格式，不要用表格
- 每次最多列出 3-5 个型号的价格，如果更多则告诉用户可以继续追问具体型号
- 优先回答用户最关心的部分，不要把所有信息一次性全部输出

**语言规则（最高优先级）：**
- 你必须使用与用户消息相同的语言回复
- 用户用英文提问 → 你必须用英文回复，即使知识库内容是中文，也要翻译成英文后回复
- 用户用中文提问 → 你必须用中文回复
- 绝对不要忽略这条规则"""

REVIEWER_PROMPT = """你是客服质检员。审核回复是否：
1. 匹配用户情绪（愤怒→安抚，困惑→耐心）
2. 回答了用户问题
3. 用语专业得体
4. 使用了与用户相同的语言（用户用英文则回复必须是英文，用户用中文则回复必须是中文）
5. 价格货币单位正确：所有价格必须使用 IDR（印尼盾），以 Rp 前缀显示（如 Rp 3,836,000）。如果回复中出现"元"、"¥"、"RMB"、"人民币"等非印尼盾货币，必须修正为正确的 IDR 价格

合格则原样返回，需改进则直接输出改进版（不解释）。必须保持与用户相同的语言。"""


# ── 情绪 & 意图分析 ──────────────────────────────────

_SENTIMENT_RULES: list[tuple[Sentiment, list[str]]] = [
    (Sentiment.NEGATIVE, ["差", "烂", "垃圾", "投诉", "骗", "坑", "怒", "气死", "恶心", "失望", "angry", "terrible", "worst", "hate", "awful"]),
    (Sentiment.FRUSTRATED, ["等了很久", "一直", "还没", "多少次", "到底", "为什么", "still", "waiting", "why"]),
    (Sentiment.CONFUSED, ["怎么", "不懂", "不明白", "什么意思", "如何", "how", "confused", "don't understand"]),
    (Sentiment.POSITIVE, ["谢谢", "感谢", "好的", "满意", "棒", "赞", "不错", "thanks", "great", "good", "awesome"]),
]


def _analyze_sentiment(text: str) -> Sentiment:
    lower = text.lower()
    for sentiment, keywords in _SENTIMENT_RULES:
        if any(kw in lower for kw in keywords):
            return sentiment
    return Sentiment.NEUTRAL


_INTENT_PATTERNS: list[tuple[IntentCategory, list[str], float]] = [
    (IntentCategory.ORDER_STATUS, ["订单", "物流", "快递", "发货", "配送", "order", "delivery", "shipping"], 1.0),
    (IntentCategory.REFUND_REQUEST, ["退款", "退货", "退钱", "refund", "return"], 1.0),
    (IntentCategory.COMPLAINT, ["投诉", "举报", "差评", "complaint"], 1.0),
    (IntentCategory.TECHNICAL_SUPPORT, ["故障", "坏了", "不能用", "报错", "bug", "error", "broken"], 1.0),
    (IntentCategory.PRODUCT_INQUIRY, ["价格", "功能", "规格", "推荐", "price", "feature"], 1.0),
    (IntentCategory.HUMAN_HANDOFF, ["转人工", "人工客服", "真人", "human", "real person"], 1.5),
    (IntentCategory.FEEDBACK, ["建议", "反馈", "意见", "feedback", "suggestion"], 1.0),
]


def _classify_intent(text: str) -> tuple[IntentCategory, float]:
    lower = text.lower()
    best, best_score = IntentCategory.GENERAL_CHAT, 0.0
    for intent, kws, w in _INTENT_PATTERNS:
        score = sum(w for k in kws if k in lower)
        if score > best_score:
            best_score, best = score, intent
    return best, min(best_score / 3, 1.0)


def _detect_language(text: str) -> str:
    return "zh" if len(re.findall(r"[\u4e00-\u9fff]", text)) > len(text) * 0.3 else "en"


# ── Valid enum value sets for LLM response parsing ────

_VALID_SENTIMENTS = {s.value for s in Sentiment}
_VALID_INTENTS = {i.value for i in IntentCategory}


def _parse_supervisor_llm_response(
    content: str,
) -> dict[str, Any] | None:
    """Parse the structured JSON from the supervisor LLM response.

    Returns a dict with keys ``next``, ``sentiment``, ``intent``,
    ``confidence`` on success, or *None* when the content cannot be
    parsed into a valid structure.
    """
    if not content:
        return None

    text = content.strip()

    # Strip markdown code fences if present
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
        elif len(parts) == 2:
            text = parts[1]
        text = text.removeprefix("json").strip()

    try:
        data = _json.loads(text)
    except (ValueError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    # Validate & normalise each field
    next_val = str(data.get("next", "worker")).lower()
    if next_val not in ("worker", "human"):
        next_val = "worker"

    sentiment_val = str(data.get("sentiment", "")).lower()
    if sentiment_val not in _VALID_SENTIMENTS:
        return None  # signal caller to fall back

    intent_val = str(data.get("intent", "")).lower()
    if intent_val not in _VALID_INTENTS:
        return None

    try:
        confidence_val = float(data.get("confidence", 0.0))
    except (ValueError, TypeError):
        confidence_val = 0.0
    confidence_val = max(0.0, min(1.0, confidence_val))

    return {
        "next": next_val,
        "sentiment": Sentiment(sentiment_val),
        "intent": IntentCategory(intent_val),
        "confidence": confidence_val,
    }


# ── LangGraph State ──────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_text: str
    sentiment: Sentiment
    intent: IntentCategory
    confidence: float
    language: str
    tools_used: list[str]
    knowledge_refs: list[str]
    agent_reply: str
    final_reply: str
    should_escalate: bool
    user_profile: UserProfile | None
    conversation_summary: str | None
    recommendations: list[KnowledgeEntry]
    needs_clarification: bool
    clarification_message: str | None
    # 内部传递字段（跨节点共享上下文）
    _session_id: str
    _user_id: str
    _clarification_round: int
    _original_ambiguous_message: str | None


# ── Node 1: Supervisor ───────────────────────────────

_supervisor_llm = _make_llm(temperature=0.0, max_tokens=150)


@timed_node("supervisor")
async def supervisor_node(state: AgentState) -> dict[str, Any]:
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "supervisor", "event": "enter"}})

    user_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_text = str(msg.content)
            break

    # 澄清后重新分类（需求 4.5）：合并原始消息与澄清回复
    original_ambiguous = state.get("_original_ambiguous_message")
    if original_ambiguous and user_text:
        from server.agent.clarification import merge_clarification_messages
        user_text = merge_clarification_messages(original_ambiguous, user_text)
        logger.info("clarification_merge", extra={"extra_fields": {
            "original": original_ambiguous[:50],
            "merged_length": len(user_text),
        }})

    language = _detect_language(user_text)

    # LLM-driven routing + sentiment + intent (需求 14.3: single LLM call)
    parsed: dict[str, Any] | None = None
    try:
        resp = await _resilient_llm_invoke(
            _supervisor_llm,
            [SystemMessage(content=SUPERVISOR_PROMPT), HumanMessage(content=user_text)],
            label="supervisor",
        )
        content = str(resp.content).strip() if resp else ""
        parsed = _parse_supervisor_llm_response(content)
    except (RetryExhaustedError, CircuitOpenError):
        # LLM unavailable — fall back below
        parsed = None

    if parsed is not None:
        # LLM analysis succeeded (需求 14.1, 14.2, 14.5)
        next_step = parsed["next"]
        sentiment = parsed["sentiment"]
        intent = parsed["intent"]
        confidence = parsed["confidence"]
        logger.info("supervisor_llm_analysis", extra={"extra_fields": {
            "source": "llm",
            "sentiment": sentiment.value,
            "intent": intent.value,
            "confidence": confidence,
        }})
    else:
        # Fallback to keyword-based rules (需求 14.4)
        sentiment = _analyze_sentiment(user_text)
        intent, confidence = _classify_intent(user_text)
        next_step = "human" if intent == IntentCategory.HUMAN_HANDOFF else "worker"
        logger.info("supervisor_keyword_fallback", extra={"extra_fields": {
            "source": "keyword",
            "sentiment": sentiment.value,
            "intent": intent.value,
            "confidence": confidence,
        }})

    lang_label = "中文" if language == "zh" else "English"
    ctx = SystemMessage(content=(
        f"[分析] 情绪:{sentiment.value} 意图:{intent.value}"
        f"({confidence*100:.0f}%) 语言:{lang_label}\n"
        f"[重要] 用户使用的语言是{lang_label}，你必须用{lang_label}回复。"
    ))

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "supervisor", "event": "exit", "duration_ms": duration_ms,
        "sentiment": sentiment.value, "intent": intent.value,
    }})

    return {
        "messages": [ctx],
        "user_text": user_text,
        "sentiment": sentiment,
        "intent": intent,
        "confidence": confidence,
        "language": language,
        "should_escalate": next_step == "human",
    }


def supervisor_route(state: AgentState) -> Literal["human_node", "worker_node"]:
    return "human_node" if state.get("should_escalate") else "worker_node"


def human_node(state: AgentState) -> dict[str, Any]:
    reply = (
        "正在为您转接人工客服，预计等待2-5分钟。\n"
        "您可以继续描述问题，人工客服接入后会看到完整记录。"
    )
    return {
        "final_reply": reply,
        "messages": [AIMessage(content=reply)],
        "tools_used": ["escalate_to_human"],
    }


# ── Node 2: Worker Agent (ReAct) ─────────────────────

_worker_llm = None
_tool_executor = None


def _ensure_worker():
    global _worker_llm, _tool_executor
    if _worker_llm is None:
        _worker_llm = _make_llm(temperature=0.7, max_tokens=2048).bind_tools(ALL_TOOLS)
        _tool_executor = ToolNode(ALL_TOOLS)


@timed_node("worker")
async def worker_node(state: AgentState) -> dict[str, Any]:
    _ensure_worker()
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "worker", "event": "enter"}})

    msgs = [SystemMessage(content=WORKER_PROMPT)] + list(state["messages"])

    try:
        resp = await _resilient_llm_invoke(_worker_llm, msgs, label="worker")
    except (RetryExhaustedError, CircuitOpenError):
        # 降级: 返回预定义回复
        sentiment = state.get("sentiment", Sentiment.NEUTRAL)
        intent = state.get("intent", IntentCategory.GENERAL_CHAT)
        fallback = _get_fallback_reply(intent, sentiment)
        resp = AIMessage(content=fallback)

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "worker", "event": "exit", "duration_ms": duration_ms,
    }})
    return {"messages": [resp]}


def worker_should_tool(state: AgentState) -> Literal["tool_node", "worker_done"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tool_node"
    return "worker_done"


@timed_node("tool")
def tool_node(state: AgentState) -> dict[str, Any]:
    _ensure_worker()
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "tool", "event": "enter"}})

    # Identify the pending tool calls for error handling
    last_ai = state["messages"][-1]
    new_tools: list[str] = []
    new_refs: list[str] = []

    try:
        result = _tool_executor.invoke(state)
    except Exception as exc:
        # 结构化异常处理 — 需求 7.2
        logger.error("tool_execution_failed", exc_info=exc, extra={"extra_fields": {
            "node": "tool", "event": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }})
        # 构造 ToolMessage 返回给 Worker，让它选择替代方案
        tool_call_id = ""
        if isinstance(last_ai, AIMessage) and last_ai.tool_calls:
            tool_call_id = last_ai.tool_calls[-1].get("id", "")
            for tc in last_ai.tool_calls:
                tool_name = tc["name"]
                new_tools.append(tool_name)
                TOOL_CALLS.labels(tool_name=tool_name, status="error").inc()
                tool_duration_ms = int((time.time() - node_start) * 1000)
                collect_agent_event({
                    "type": "agent_event",
                    "event": "tool_call",
                    "tool": tool_name,
                    "duration_ms": tool_duration_ms,
                    "timestamp": time.time(),
                })

        error_msg = ToolMessage(
            content=(
                f"工具执行失败: {type(exc).__name__}: {str(exc)}。"
                "请尝试其他方式回答用户。"
            ),
            tool_call_id=tool_call_id,
        )

        duration_ms = int((time.time() - node_start) * 1000)
        logger.info("node_exit", extra={"extra_fields": {
            "node": "tool", "event": "exit", "duration_ms": duration_ms,
            "tools_called": new_tools, "status": "error",
        }})

        return {
            "messages": [error_msg],
            "tools_used": state.get("tools_used", []) + new_tools,
            "knowledge_refs": state.get("knowledge_refs", []) + new_refs,
        }

    if isinstance(last_ai, AIMessage) and last_ai.tool_calls:
        for tc in last_ai.tool_calls:
            tool_name = tc["name"]
            new_tools.append(tool_name)
            TOOL_CALLS.labels(tool_name=tool_name, status="ok").inc()
            if tool_name == "search_knowledge_tool":
                new_refs.append(tc["args"].get("query", ""))
            tool_duration_ms = int((time.time() - node_start) * 1000)
            collect_agent_event({
                "type": "agent_event",
                "event": "tool_call",
                "tool": tool_name,
                "duration_ms": tool_duration_ms,
                "timestamp": time.time(),
            })

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "tool", "event": "exit", "duration_ms": duration_ms,
        "tools_called": new_tools,
    }})

    return {
        **result,
        "tools_used": state.get("tools_used", []) + new_tools,
        "knowledge_refs": state.get("knowledge_refs", []) + new_refs,
    }


def worker_done(state: AgentState) -> dict[str, Any]:
    last = state["messages"][-1]
    reply = str(last.content) if isinstance(last, AIMessage) else ""
    return {"agent_reply": reply}


# ── Node 3: Quality Reviewer ─────────────────────────

_reviewer_llm = _make_llm(temperature=0.1, max_tokens=2048)

# 需要严格审核的情绪/意图组合
_REVIEW_SENTIMENTS = {Sentiment.NEGATIVE, Sentiment.FRUSTRATED}
_REVIEW_INTENTS = {IntentCategory.COMPLAINT, IntentCategory.REFUND_REQUEST}


@timed_node("reviewer")
async def reviewer_node(state: AgentState) -> dict[str, Any]:
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "reviewer", "event": "enter"}})

    agent_reply = state.get("agent_reply", "")
    if not agent_reply:
        logger.info("node_exit", extra={"extra_fields": {
            "node": "reviewer", "event": "exit", "duration_ms": 0, "skipped": True,
        }})
        return {"final_reply": "您好！我是小智，请问有什么可以帮您？"}

    sentiment = state.get("sentiment", Sentiment.NEUTRAL)
    intent = state.get("intent", IntentCategory.GENERAL_CHAT)

    # 快速通道：正面/中性情绪 + 非敏感意图 → 跳过 LLM 审核
    needs_review = sentiment in _REVIEW_SENTIMENTS or intent in _REVIEW_INTENTS
    if not needs_review:
        duration_ms = int((time.time() - node_start) * 1000)
        logger.info("node_exit", extra={"extra_fields": {
            "node": "reviewer", "event": "exit", "duration_ms": duration_ms,
            "skipped": True, "reason": "fast_pass",
        }})
        return {
            "final_reply": agent_reply,
            "messages": [AIMessage(content=agent_reply)],
        }

    try:
        resp = await _resilient_llm_invoke(
            _reviewer_llm,
            [
                SystemMessage(content=REVIEWER_PROMPT),
                HumanMessage(content=(
                    f"用户：{state.get('user_text', '')}\n"
                    f"情绪：{sentiment.value}\n"
                    f"客服回复：\n{agent_reply}"
                )),
            ],
            label="reviewer",
        )
        reviewed = str(resp.content).strip()
    except (RetryExhaustedError, CircuitOpenError):
        reviewed = agent_reply

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "reviewer", "event": "exit", "duration_ms": duration_ms,
    }})

    return {
        "final_reply": reviewed,
        "messages": [AIMessage(content=reviewed)],
    }


# ── 新增智能化节点 ────────────────────────────────────

_summarizer: Any = None
_clarification_detector: Any = None
_recommendation_engine: Any = None
_profile_store: Any = None


def _get_summarizer():
    global _summarizer
    if _summarizer is None:
        from server.agent.summarizer import Summarizer
        cfg = get_config()
        llm = _make_llm(temperature=0.0, max_tokens=1024)
        _summarizer = Summarizer(llm=llm, config=cfg)
    return _summarizer


def _get_clarification_detector():
    global _clarification_detector
    if _clarification_detector is None:
        from server.agent.clarification import ClarificationDetector
        cfg = get_config()
        _clarification_detector = ClarificationDetector(config=cfg)
    return _clarification_detector


def _get_recommendation_engine():
    global _recommendation_engine
    if _recommendation_engine is None:
        from server.agent.recommendation import RecommendationEngine
        cfg = get_config()
        _recommendation_engine = RecommendationEngine(config=cfg)
    return _recommendation_engine


def _get_profile_store():
    global _profile_store
    if _profile_store is None:
        from server.data.profile_store import ProfileStore
        cfg = get_config()
        _profile_store = ProfileStore(db_url=cfg.session_db_url)
    return _profile_store


def set_profile_store(store: Any) -> None:
    """Called by main.py lifespan to inject the initialised store."""
    global _profile_store
    _profile_store = store


@timed_node("clarification_check")
async def clarification_check_node(state: AgentState) -> dict[str, Any]:
    """
    澄清检查节点（需求 4.1, 4.4）。

    调用 ClarificationDetector 判断是否需要澄清，
    更新 SessionContext 澄清状态。
    """
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "clarification_check", "event": "enter"}})

    confidence = state.get("confidence", 1.0)
    detector = _get_clarification_detector()

    # 构建临时 SessionContext 用于检测
    from server.core.models import SessionContext
    ctx = SessionContext(
        pending_clarification=False,
        clarification_round=state.get("_clarification_round", 0),
    )

    needs_clarification = False
    clarification_message = None
    should_escalate = state.get("should_escalate", False)

    if confidence < detector._threshold:
        if detector.should_escalate_to_human(ctx):
            # 连续 2 轮澄清失败 → 转人工（需求 4.6）
            should_escalate = True
            logger.info("clarification_escalate", extra={"extra_fields": {
                "round": ctx.clarification_round,
            }})
        elif detector.should_clarify(confidence, ctx):
            # 触发澄清（需求 4.1）
            intent = state.get("intent", IntentCategory.GENERAL_CHAT)
            user_text = state.get("user_text", "")
            clarification_message = detector.generate_clarification(intent, user_text)
            needs_clarification = True
            logger.info("clarification_triggered", extra={"extra_fields": {
                "confidence": confidence,
                "intent": intent.value,
                "round": ctx.clarification_round,
            }})

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "clarification_check", "event": "exit", "duration_ms": duration_ms,
        "needs_clarification": needs_clarification,
    }})

    return {
        "needs_clarification": needs_clarification,
        "clarification_message": clarification_message,
        "should_escalate": should_escalate,
    }


def clarification_route(state: AgentState) -> Literal["clarify", "escalate", "continue"]:
    """
    澄清路由（需求 4.1, 4.6）。

    - needs_clarification → "clarify" (返回澄清问题，END)
    - should_escalate → "escalate" (转人工)
    - 否则 → "continue" (继续正常流程)
    """
    if state.get("needs_clarification"):
        return "clarify"
    if state.get("should_escalate"):
        return "escalate"
    return "continue"


def clarify_node(state: AgentState) -> dict[str, Any]:
    """返回澄清问题作为最终回复（需求 4.2, 4.4）。"""
    msg = state.get("clarification_message", "抱歉，我不太确定您的意思，能否再详细描述一下？")
    return {
        "final_reply": msg,
        "messages": [AIMessage(content=msg)],
    }


@timed_node("summary_check")
async def summary_check_node(state: AgentState) -> dict[str, Any]:
    """
    摘要检查节点（需求 1.1, 1.3, 1.5）。

    调用 Summarizer.check_and_summarize() 替换 state["messages"]
    中的历史消息。
    """
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "summary_check", "event": "enter"}})

    summarizer = _get_summarizer()

    # 从 state 中获取 session 信息来构建临时 Session 对象
    # 注意：实际 session 在 process_message 中管理，这里通过 state 传递
    session_id = state.get("_session_id", "")
    if session_id:
        session = await get_session(session_id)
        if session and len(session.messages) > 0:
            try:
                compressed_messages = await summarizer.check_and_summarize(session)
                summary_text = None
                if session.context.conversation_summary:
                    summary_text = session.context.conversation_summary.summary_text

                duration_ms = int((time.time() - node_start) * 1000)
                logger.info("node_exit", extra={"extra_fields": {
                    "node": "summary_check", "event": "exit", "duration_ms": duration_ms,
                    "summarized": summary_text is not None,
                }})

                return {
                    "messages": compressed_messages,
                    "conversation_summary": summary_text,
                }
            except Exception as e:
                logger.warning("summary_check_failed", exc_info=e)

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "summary_check", "event": "exit", "duration_ms": duration_ms,
        "summarized": False,
    }})
    return {}


@timed_node("profile_load")
async def profile_load_node(state: AgentState) -> dict[str, Any]:
    """
    画像加载节点（需求 2.4, 2.5, 2.6）。

    调用 ProfileStore.load() 加载画像（3 秒超时降级），
    注入画像 Prompt 到 Worker 消息。
    """
    import asyncio
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "profile_load", "event": "enter"}})

    cfg = get_config()
    store = _get_profile_store()
    user_id = state.get("_user_id", "anonymous")

    profile = None
    try:
        profile = await asyncio.wait_for(
            store.load(user_id),
            timeout=cfg.profile_load_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("profile_load_timeout", extra={"extra_fields": {
            "user_id": user_id, "timeout_s": cfg.profile_load_timeout,
        }})
    except Exception as e:
        logger.warning("profile_load_failed", exc_info=e)

    # 首次对话使用默认画像（需求 2.5）
    if profile is None:
        profile = UserProfile.default(user_id)

    # 注入画像 Prompt 到消息（需求 2.4）
    from server.agent.profile_analyzer import build_profile_prompt_segment
    profile_prompt = build_profile_prompt_segment(profile)
    profile_msg = SystemMessage(content=profile_prompt)

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "profile_load", "event": "exit", "duration_ms": duration_ms,
        "user_id": user_id,
        "style": profile.communication_style.value if hasattr(profile.communication_style, 'value') else str(profile.communication_style),
    }})

    return {
        "user_profile": profile,
        "messages": [profile_msg],
    }


@timed_node("recommend")
async def recommendation_node(state: AgentState) -> dict[str, Any]:
    """
    推荐节点（需求 3.1, 3.6）。

    调用 RecommendationEngine.get_recommendations()，
    记录推荐 ID 到 metadata。
    """
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "recommend", "event": "enter"}})

    engine = _get_recommendation_engine()
    intent = state.get("intent", IntentCategory.GENERAL_CHAT)

    # 从 state 获取主查询结果（knowledge_refs 中的条目）
    from server.core.models import SessionContext
    ctx = SessionContext()

    recommendations: list[KnowledgeEntry] = []
    try:
        recommendations = await engine.get_recommendations(
            intent=intent,
            main_results=[],  # 主查询结果在 tool_node 中处理，这里传空
            session_context=ctx,
        )
    except Exception as e:
        logger.error("recommendation_failed", exc_info=e)

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "recommend", "event": "exit", "duration_ms": duration_ms,
        "count": len(recommendations),
    }})

    return {
        "recommendations": recommendations,
    }


@timed_node("profile_update")
async def profile_update_node(state: AgentState) -> dict[str, Any]:
    """
    画像更新节点（需求 2.2）。

    调用 ProfileAnalyzer 更新画像并持久化。
    """
    node_start = time.time()
    logger.info("node_enter", extra={"extra_fields": {"node": "profile_update", "event": "enter"}})

    profile = state.get("user_profile")
    if profile is None:
        duration_ms = int((time.time() - node_start) * 1000)
        logger.info("node_exit", extra={"extra_fields": {
            "node": "profile_update", "event": "exit", "duration_ms": duration_ms,
            "skipped": True,
        }})
        return {}

    from server.agent.profile_analyzer import (
        analyze_communication_style,
        extract_frequent_topics,
        update_satisfaction,
    )
    from server.core.models import Message

    # 从 state 中提取用户消息用于分析
    user_text = state.get("user_text", "")
    sentiment = state.get("sentiment", Sentiment.NEUTRAL)
    intent = state.get("intent", IntentCategory.GENERAL_CHAT)

    # 构建 Message 对象用于分析
    user_messages = [Message(role="user", content=user_text)] if user_text else []

    try:
        # 更新沟通风格
        style = analyze_communication_style(user_messages)
        profile.communication_style = style

        # 更新高频主题
        topics = extract_frequent_topics(user_messages, intent)
        # 合并已有主题
        existing = set(profile.frequent_topics)
        for t in topics:
            if t not in existing:
                profile.frequent_topics.append(t)
                existing.add(t)

        # 更新满意度
        profile.satisfaction_history = update_satisfaction(profile, sentiment)

        # 递增交互次数
        profile.interaction_count += 1
        profile.updated_at = time.time()

        # 持久化（失败不阻塞）
        store = _get_profile_store()
        await store.save(profile)

    except Exception as e:
        logger.error("profile_update_failed", exc_info=e)

    duration_ms = int((time.time() - node_start) * 1000)
    logger.info("node_exit", extra={"extra_fields": {
        "node": "profile_update", "event": "exit", "duration_ms": duration_ms,
    }})

    return {"user_profile": profile}


# ── 构建 Graph ───────────────────────────────────────

def _build_graph() -> Any:
    """
    supervisor → clarification_check → (clarify→END / escalate→human_node /
    continue→summary_check) → profile_load → worker_node ⇄ tool_node →
    recommend → worker_done → reviewer → profile_update → END
    """
    g = StateGraph(AgentState)

    # 现有节点
    g.add_node("supervisor", supervisor_node)
    g.add_node("human_node", human_node)
    g.add_node("worker_node", worker_node)
    g.add_node("tool_node", tool_node)
    g.add_node("worker_done", worker_done)
    g.add_node("reviewer", reviewer_node)

    # 新增节点
    g.add_node("clarification_check", clarification_check_node)
    g.add_node("clarify", clarify_node)
    g.add_node("summary_check", summary_check_node)
    g.add_node("profile_load", profile_load_node)
    g.add_node("recommend", recommendation_node)
    g.add_node("profile_update", profile_update_node)

    g.set_entry_point("supervisor")

    # Supervisor → 澄清检查
    g.add_edge("supervisor", "clarification_check")

    # 澄清检查 → 路由
    g.add_conditional_edges("clarification_check", clarification_route, {
        "clarify": "clarify",
        "escalate": "human_node",
        "continue": "summary_check",
    })
    g.add_edge("clarify", END)
    g.add_edge("human_node", END)

    # 摘要检查 → 画像加载
    g.add_edge("summary_check", "profile_load")

    # 画像加载 → Worker
    g.add_edge("profile_load", "worker_node")

    # Worker 工具循环
    g.add_conditional_edges("worker_node", worker_should_tool, {
        "tool_node": "tool_node",
        "worker_done": "recommend",  # Worker 完成后先推荐
    })
    g.add_edge("tool_node", "worker_node")

    # 推荐 → Worker Done → Reviewer → 画像更新 → END
    g.add_edge("recommend", "worker_done")
    g.add_edge("worker_done", "reviewer")
    g.add_edge("reviewer", "profile_update")
    g.add_edge("profile_update", END)

    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── 会话管理（SessionStore 持久化）─────────────────────

_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Return the global SessionStore instance (created during lifespan)."""
    global _session_store
    if _session_store is None:
        # Lazy fallback — memory-only store when lifespan hasn't run
        _session_store = SessionStore(db_url="")
    return _session_store


def set_session_store(store: SessionStore) -> None:
    """Called by main.py lifespan to inject the initialised store."""
    global _session_store
    _session_store = store


async def get_or_create_session(sid: str, uid: str) -> Session:
    store = get_session_store()
    existing = await store.load(sid)
    if existing is not None:
        return existing
    s = Session(id=sid, user_id=uid)
    await store.save(s)
    return s


async def get_session(sid: str) -> Optional[Session]:
    return await get_session_store().load(sid)


async def get_all_sessions() -> list[Session]:
    return await get_session_store().get_all()


async def rate_session(sid: str, rating: int) -> bool:
    return await get_session_store().rate(sid, rating)


# ── 对外接口 ──────────────────────────────────────────

async def process_message(
    session_id: str, user_id: str, user_message: str
) -> tuple[str, MessageMetadata]:
    start = time.time()
    session = await get_or_create_session(session_id, user_id)

    # Set context vars for structured logging (需求 1.2)
    session_id_var.set(session_id)
    user_id_var.set(user_id)

    # Start collecting agent events for this request (Requirement 15.1)
    agent_events_bucket = start_event_collection()

    logger.info("process_message_start", extra={"extra_fields": {
        "session_id": session_id, "user_id": user_id,
    }})

    history: list[BaseMessage] = []
    for m in session.messages:
        if m.role == "user":
            history.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            history.append(AIMessage(content=m.content))
    history.append(HumanMessage(content=user_message))

    # 获取当前澄清轮次（用于澄清检查节点）
    clarification_round = session.context.clarification_round
    # 如果处于澄清等待状态，传递原始模糊消息（需求 4.5）
    original_ambiguous = session.context.original_ambiguous_message if session.context.pending_clarification else None

    try:
        result = await _get_graph().ainvoke({
            "messages": history,
            "user_text": user_message,
            "sentiment": Sentiment.NEUTRAL,
            "intent": IntentCategory.GENERAL_CHAT,
            "confidence": 0.0,
            "language": "zh",
            "tools_used": [],
            "knowledge_refs": [],
            "agent_reply": "",
            "final_reply": "",
            "should_escalate": False,
            # 新增字段
            "user_profile": None,
            "conversation_summary": None,
            "recommendations": [],
            "needs_clarification": False,
            "clarification_message": None,
            # 内部传递字段
            "_session_id": session_id,
            "_user_id": user_id,
            "_clarification_round": clarification_round,
            "_original_ambiguous_message": original_ambiguous,
        })

        reply = result.get("final_reply") or result.get("agent_reply") or "抱歉，暂时无法回复。"
        sentiment = result.get("sentiment", Sentiment.NEUTRAL)
        intent = result.get("intent", IntentCategory.GENERAL_CHAT)
        confidence = result.get("confidence", 0.0)
        language = result.get("language", "zh")
        tools_used = result.get("tools_used", [])
        knowledge_refs = result.get("knowledge_refs", [])
        should_escalate = result.get("should_escalate", False)
        recommendations = result.get("recommendations", [])
        needs_clarification = result.get("needs_clarification", False)

        # 推荐内容格式化（需求 3.4）
        if recommendations and not needs_clarification:
            from server.agent.recommendation import format_recommendations
            reply = format_recommendations(reply, recommendations)

    except Exception as e:
        logger.error("agent_execution_failed", exc_info=e, extra={"extra_fields": {
            "session_id": session_id, "user_id": user_id,
        }})
        sentiment = _analyze_sentiment(user_message)
        intent, confidence = _classify_intent(user_message)
        language = _detect_language(user_message)
        reply = _get_fallback_reply(intent, sentiment)
        tools_used, knowledge_refs, should_escalate = [], [], False
        recommendations, needs_clarification = [], False

    # Build AgentEvent model instances from collected raw dicts
    from server.core.models import AgentEvent as AgentEventModel
    collected = get_collected_events()
    agent_event_models = [
        AgentEventModel(**evt) for evt in collected
    ]

    metadata = MessageMetadata(
        sentiment=sentiment, intent=intent, confidence=confidence,
        language=language, tools_used=tools_used,
        knowledge_refs=knowledge_refs,
        response_time_ms=int((time.time() - start) * 1000),
        trace_id=trace_id_var.get(""),
        agent_events=agent_event_models,
        recommended_knowledge_ids=[r.id for r in recommendations] if recommendations else [],
        clarification_triggered=needs_clarification,
        clarification_round=session.context.clarification_round,
    )
    user_msg = Message(
        role="user", content=user_message,
        metadata=MessageMetadata(sentiment=sentiment, intent=intent, confidence=confidence, language=language),
    )
    bot_msg = Message(role="assistant", content=reply, metadata=metadata)

    session.messages.append(user_msg)
    session.messages.append(bot_msg)
    session.context.language = language
    session.context.sentiment_trend.append(sentiment)
    session.context.user_name = session.context.user_name or user_id
    if confidence > 0.3:
        session.context.current_intent = intent

    # 更新澄清状态（需求 4.4）
    if needs_clarification:
        session.context.pending_clarification = True
        session.context.original_ambiguous_message = user_message
        session.context.clarification_round += 1
    elif session.context.pending_clarification:
        # 澄清成功，清除状态
        session.context.pending_clarification = False
        session.context.original_ambiguous_message = None

    if should_escalate:
        session.status = SessionStatus.ESCALATED
    session.updated_at = time.time()

    # Persist session to store (Requirement 3.2)
    store = get_session_store()
    await store.save(session)

    return reply, metadata


def _get_fallback_reply(intent: IntentCategory, sentiment: Sentiment) -> str:
    empathy = "非常抱歉给您带来不好的体验。" if sentiment in (Sentiment.NEGATIVE, Sentiment.FRUSTRATED) else ""
    replies = {
        IntentCategory.PRODUCT_INQUIRY: f"{empathy}建议查看商品详情页，或拨打 400-XXX-XXXX。",
        IntentCategory.ORDER_STATUS: f"{empathy}可在「我的订单」页面查看状态。",
        IntentCategory.REFUND_REQUEST: f"{empathy}退款可在订单详情页操作。",
        IntentCategory.TECHNICAL_SUPPORT: f"{empathy}建议先重启设备，如持续请拨打 400-XXX-XXXX。",
        IntentCategory.COMPLAINT: f"{empathy}请拨打投诉专线 400-XXX-XXXX。",
        IntentCategory.GENERAL_CHAT: "您好！我是小智，请问有什么可以帮您？",
        IntentCategory.HUMAN_HANDOFF: f"{empathy}正在转接人工客服，也可拨打 400-XXX-XXXX。",
        IntentCategory.FEEDBACK: "感谢建议！我们会持续改进。",
    }
    return replies.get(intent, replies[IntentCategory.GENERAL_CHAT])
