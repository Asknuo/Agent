"""
亮点 2：LangChain 标准工具系统
使用 @tool 装饰器，自动生成 schema，无缝接入 LangGraph Agent
"""

from __future__ import annotations
import random
import uuid

from langchain_core.tools import tool

from server.core.models import Ticket, TicketPriority, TicketStatus
from server.data.knowledge_base import search_knowledge

# 内存存储
_tickets: dict[str, Ticket] = {}

# 模拟订单数据
_mock_orders: dict[str, dict[str, str]] = {
    "ORD-20240101": {"status": "已发货", "items": "无线蓝牙耳机 x1", "eta": "预计明天送达"},
    "ORD-20240102": {"status": "配送中", "items": "机械键盘 x1, 鼠标垫 x1", "eta": "预计后天送达"},
    "ORD-20240103": {"status": "已签收", "items": "手机壳 x2", "eta": "已完成"},
}


@tool
def search_knowledge_tool(query: str) -> str:
    """从知识库中检索相关信息来回答用户问题。当用户询问产品政策、退款、配送、会员、支付、安全等问题时使用。"""
    results = search_knowledge(query)
    if not results:
        return "知识库中未找到相关信息。"
    return "\n\n".join(f"【{r.title}】{r.content}" for r in results)


@tool
def query_order(order_id: str) -> str:
    """查询用户订单状态。需要提供订单号，格式如 ORD-XXXXXXXX。"""
    order = _mock_orders.get(order_id)
    if not order:
        return f"未找到订单 {order_id}，请确认订单号是否正确。"
    return (
        f"订单 {order_id}：\n- 商品：{order['items']}\n"
        f"- 状态：{order['status']}\n- 预计：{order['eta']}"
    )


@tool
def create_ticket(title: str, description: str, priority: str) -> str:
    """为用户创建工单，用于需要人工跟进的复杂问题。priority 可选值：low, medium, high, urgent。"""
    ticket = Ticket(
        id=f"TK-{uuid.uuid4().hex[:8].upper()}",
        session_id="agent",
        user_id="user",
        title=title,
        description=description,
        priority=TicketPriority(priority),
        status=TicketStatus.OPEN,
    )
    _tickets[ticket.id] = ticket
    return (
        f"工单已创建成功！\n- 工单号：{ticket.id}\n- 标题：{ticket.title}\n"
        f"- 优先级：{ticket.priority.value}\n我们的专员会尽快处理，请保存好工单号以便查询进度。"
    )


@tool
def escalate_to_human(reason: str) -> str:
    """将对话转接给人工客服。当用户明确要求转人工，或问题超出AI能力范围时使用。"""
    return (
        f"正在为您转接人工客服，转接原因：{reason}。请稍候，预计等待时间约2-5分钟。"
        "在等待期间，您可以继续描述问题，人工客服接入后会看到完整对话记录。"
    )


@tool
def calculate_refund(order_id: str, reason: str) -> str:
    """计算退款金额。需要订单号和退款原因。"""
    refund_amount = round(random.uniform(50, 500), 2)
    return (
        f"订单 {order_id} 退款计算结果：\n- 退款原因：{reason}\n"
        f"- 预计退款金额：¥{refund_amount}\n- 退款方式：原路返回\n"
        "- 预计到账：3-5个工作日\n\n是否确认申请退款？"
    )


# ── 数据库查询工具 ────────────────────────────────────

from server.data.database import is_db_available, get_table_schema, execute_query


@tool
def query_database(sql: str) -> str:
    """执行 SQL 查询 PostgreSQL 数据库。用于查询订单、用户、商品等业务数据。
    只允许 SELECT 查询。请根据用户问题生成合适的 SQL。"""
    return execute_query(sql)


@tool
def get_db_schema() -> str:
    """获取数据库表结构信息。在不确定表结构时先调用此工具了解有哪些表和字段。"""
    return get_table_schema()


# 所有工具列表，供 LangGraph Agent 绑定
_base_tools = [
    search_knowledge_tool,
    query_order,
    create_ticket,
    escalate_to_human,
    calculate_refund,
]

_db_tools = [query_database, get_db_schema]

# 始终包含数据库工具，工具内部会检查连接状态
ALL_TOOLS = _base_tools + _db_tools


def get_all_tickets() -> list[Ticket]:
    return list(_tickets.values())
