"""智能客服系统 — 核心数据模型"""

from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import time
import uuid


# ── 枚举 ──────────────────────────────────────────────

class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"


class IntentCategory(str, Enum):
    PRODUCT_INQUIRY = "product_inquiry"
    ORDER_STATUS = "order_status"
    REFUND_REQUEST = "refund_request"
    TECHNICAL_SUPPORT = "technical_support"
    COMPLAINT = "complaint"
    GENERAL_CHAT = "general_chat"
    HUMAN_HANDOFF = "human_handoff"
    FEEDBACK = "feedback"


class CommunicationStyle(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    CONCISE = "concise"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ── 数据模型 ──────────────────────────────────────────

class ConversationSummary(BaseModel):
    """结构化会话摘要（需求 1, 5）"""
    summary_text: str
    key_entities: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    generated_at: float = Field(default_factory=time.time)

    @classmethod
    def empty(cls) -> "ConversationSummary":
        """返回空摘要（反序列化失败时的降级值）"""
        return cls(summary_text="", key_entities=[], unresolved_issues=[], generated_at=0.0)


class UserProfile(BaseModel):
    """用户画像模型（需求 2）"""
    user_id: str
    preferred_language: str = "zh"
    communication_style: CommunicationStyle = CommunicationStyle.CASUAL
    frequent_topics: list[str] = Field(default_factory=list)
    satisfaction_history: list[float] = Field(default_factory=list)
    interaction_count: int = 0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @classmethod
    def default(cls, user_id: str) -> "UserProfile":
        """首次对话时的默认画像"""
        return cls(user_id=user_id)


class AgentEvent(BaseModel):
    """Agent execution event, pushed to frontend via SSE (Requirement 15.1, 15.3)"""
    type: str = "agent_event"
    event: str  # node_start | node_end | tool_call
    node: Optional[str] = None
    tool: Optional[str] = None
    duration_ms: Optional[int] = None
    timestamp: float = Field(default_factory=time.time)


class MessageMetadata(BaseModel):
    sentiment: Optional[Sentiment] = None
    intent: Optional[IntentCategory] = None
    confidence: Optional[float] = None
    language: Optional[str] = None
    tools_used: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    response_time_ms: Optional[int] = None
    trace_id: Optional[str] = None
    agent_events: list[AgentEvent] = Field(default_factory=list)
    # 新增：推荐相关（需求 3）
    recommended_knowledge_ids: list[str] = Field(default_factory=list)
    # 新增：澄清相关（需求 4）
    clarification_triggered: bool = False
    clarification_round: int = 0


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    role: str  # user | assistant | system
    content: str
    timestamp: float = Field(default_factory=time.time)
    metadata: Optional[MessageMetadata] = None


class SessionContext(BaseModel):
    user_name: Optional[str] = None
    language: str = "zh"
    sentiment_trend: list[Sentiment] = Field(default_factory=list)
    current_intent: Optional[IntentCategory] = None
    extracted_entities: dict[str, str] = Field(default_factory=dict)
    escalation_reason: Optional[str] = None
    ticket_id: Optional[str] = None
    # 新增：摘要相关（需求 1）
    conversation_summary: Optional[ConversationSummary] = None
    # 新增：澄清相关（需求 4）
    pending_clarification: bool = False
    clarification_round: int = 0
    original_ambiguous_message: Optional[str] = None


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str = "anonymous"
    tenant_id: str = "default"
    messages: list[Message] = Field(default_factory=list)
    context: SessionContext = Field(default_factory=SessionContext)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    status: SessionStatus = SessionStatus.ACTIVE
    satisfaction: Optional[int] = None


class Ticket(BaseModel):
    id: str = Field(default_factory=lambda: f"TK-{uuid.uuid4().hex[:8].upper()}")
    session_id: str
    user_id: str
    title: str
    description: str
    priority: TicketPriority
    status: TicketStatus = TicketStatus.OPEN
    created_at: float = Field(default_factory=time.time)


class KnowledgeEntry(BaseModel):
    id: str
    title: str
    content: str
    category: str
    tags: list[str]


# ── 配置相关 ──────────────────────────────────────────

class TenantConfig(BaseModel):
    """租户级配置"""
    tenant_id: str
    rate_limit_rpm: int = 30
    knowledge_dir: str = ""  # 空则使用默认知识库
    custom_prompts: dict[str, str] = Field(default_factory=dict)


# ── 可观测性 ──────────────────────────────────────────

class TraceContext(BaseModel):
    """链路追踪上下文"""
    trace_id: str
    session_id: str = ""
    user_id: str = ""
    tenant_id: str = "default"
    start_time: float = Field(default_factory=time.time)


class NodeSpan(BaseModel):
    """节点执行跨度"""
    node_name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: int = 0
    status: str = "ok"  # ok | error
    metadata: dict[str, Any] = Field(default_factory=dict)


class RequestTrace(BaseModel):
    """完整请求追踪"""
    trace_id: str
    spans: list[NodeSpan] = Field(default_factory=list)
    total_duration_ms: int = 0
    tools_called: list[str] = Field(default_factory=list)


# ── 熔断器状态 ────────────────────────────────────────

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ── 缓存条目 ──────────────────────────────────────────

class CacheEntry(BaseModel):
    key: str
    value: Any
    created_at: float = Field(default_factory=time.time)
    ttl: int = 300


# ── API 请求/响应 ─────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: str = "web-user"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: MessageMetadata


class RateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
