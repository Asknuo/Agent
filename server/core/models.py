"""智能客服系统 — 核心数据模型"""

from __future__ import annotations
from enum import Enum
from typing import Optional
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
