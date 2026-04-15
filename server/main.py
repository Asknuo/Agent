"""
服务端入口 — FastAPI + WebSocket + SSE 流式
"""

from __future__ import annotations
import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from server.config import init_config
from server.logging_config import setup_logging
from server.models import ChatRequest, ChatResponse, RateRequest
from server.agent import (
    process_message, get_session, get_all_sessions, rate_session,
)
from server.knowledge_base import get_all_knowledge, init_rag
from server.database import init_db
from server.tools import get_all_tickets

logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化配置 → 日志 → RAG 向量库 → 数据库连接"""
    config = init_config()

    # 初始化结构化日志系统（需求 1.4, 1.5）
    setup_logging(level=config.log_level, log_file=config.log_file)

    # 校验关键配置（需求 11.2）
    if not config.openai_api_key:
        raise RuntimeError(
            "Missing required config: openai_api_key. "
            "Set it in config.yaml or via OPENAI_API_KEY env var."
        )

    init_db()
    init_rag()
    yield


app = FastAPI(title="小智 AI 智能客服", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST API ──────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or uuid.uuid4().hex
    reply, metadata = await process_message(session_id, req.user_id, req.message)
    return ChatResponse(session_id=session_id, reply=reply, metadata=metadata)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE 流式输出：先跑完 agent，再逐块推送回复"""
    session_id = req.session_id or uuid.uuid4().hex

    async def event_generator():
        # 发送 session_id
        yield f"data: {json.dumps({'type': 'session', 'sessionId': session_id})}\n\n"

        # 运行 agent 获取完整回复
        reply, metadata = await process_message(session_id, req.user_id, req.message)

        # 逐块推送文本（每次 ~4 个字符，模拟打字效果）
        chunk_size = 4
        for i in range(0, len(reply), chunk_size):
            chunk = reply[i:i + chunk_size]
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            await asyncio.sleep(0.03)

        # 推送 metadata 和结束信号
        yield f"data: {json.dumps({'type': 'metadata', 'metadata': metadata.model_dump()})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions")
async def list_sessions():
    return get_all_sessions()


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str):
    s = get_session(session_id)
    return s if s else {"error": "Session not found"}


@app.post("/api/sessions/{session_id}/rate")
async def rate(session_id: str, req: RateRequest):
    ok = rate_session(session_id, req.rating)
    return {"success": ok} if ok else {"error": "Session not found"}


@app.get("/api/knowledge")
async def list_knowledge():
    return get_all_knowledge()


@app.get("/api/tickets")
async def list_tickets():
    return get_all_tickets()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── WebSocket 实时通信 ────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    client_id = uuid.uuid4().hex[:8]
    logger.info("ws_client_connected", extra={"extra_fields": {"client_id": client_id}})

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")
            session_id = data.get("sessionId", uuid.uuid4().hex)

            if msg_type == "chat":
                message = data.get("payload", {}).get("message", "")
                await ws.send_json({"type": "typing", "sessionId": session_id, "payload": {"isTyping": True}})

                reply, metadata = await process_message(session_id, client_id, message)

                await ws.send_json({"type": "typing", "sessionId": session_id, "payload": {"isTyping": False}})
                await ws.send_json({
                    "type": "chat",
                    "sessionId": session_id,
                    "payload": {"reply": reply, "metadata": metadata.model_dump()},
                })

            elif msg_type == "rating":
                rating = data.get("payload", {}).get("rating", 5)
                rate_session(session_id, rating)
                await ws.send_json({"type": "status", "sessionId": session_id, "payload": {"rated": True}})

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", extra={"extra_fields": {"client_id": client_id}})


# ── 启动入口 ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
