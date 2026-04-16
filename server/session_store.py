"""
会话持久化存储 — PostgreSQL + 内存降级

需求 3: 会话数据持久化到 PostgreSQL，失败时回退内存存储。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from server.models import (
    Message, MessageMetadata, Session, SessionContext,
    SessionStatus, Sentiment, IntentCategory,
)

logger = logging.getLogger("session_store")


def _serialize_message(msg: Message) -> dict[str, Any]:
    """Serialize a Message to a JSON-compatible dict."""
    return msg.model_dump(mode="json")


def _deserialize_message(data: dict[str, Any]) -> Message:
    """Deserialize a dict back into a Message."""
    return Message.model_validate(data)


def _serialize_context(ctx: SessionContext) -> dict[str, Any]:
    """Serialize SessionContext to a JSON-compatible dict."""
    return ctx.model_dump(mode="json")


def _deserialize_context(data: dict[str, Any]) -> SessionContext:
    """Deserialize a dict back into a SessionContext."""
    return SessionContext.model_validate(data)


class SessionStore:
    """
    Async session store backed by PostgreSQL (asyncpg).

    Falls back to an in-memory dict when the database is unavailable or
    a write operation fails (Requirement 3.4).
    """

    def __init__(self, db_url: str = ""):
        self._db_url = db_url
        self._pool: Any = None  # asyncpg.Pool | None
        self._fallback: dict[str, Session] = {}

    # ── Connection management ─────────────────────────

    async def init(self) -> None:
        """Create the asyncpg connection pool. Safe to call when db_url is empty."""
        if not self._db_url:
            logger.info("session_store_no_db", extra={"extra_fields": {
                "message": "No DB URL configured — using in-memory fallback only",
            }})
            return
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self._db_url, min_size=2, max_size=10,
            )
            logger.info("session_store_connected")
        except Exception as exc:
            logger.error("session_store_connect_failed", exc_info=exc)
            self._pool = None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def _db_available(self) -> bool:
        return self._pool is not None

    # ── Public API ────────────────────────────────────

    async def save(self, session: Session) -> bool:
        """
        Persist a full session to PostgreSQL (Requirement 3.1).
        Falls back to in-memory on failure (Requirement 3.4).
        Returns True on success.
        """
        if not self._db_available:
            self._fallback[session.id] = session
            return True

        try:
            messages_json = json.dumps(
                [_serialize_message(m) for m in session.messages],
                ensure_ascii=False,
            )
            context_json = json.dumps(
                _serialize_context(session.context),
                ensure_ascii=False,
            )
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO sessions (id, user_id, tenant_id, messages, context,
                                          status, satisfaction, created_at, updated_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7,
                            to_timestamp($8), to_timestamp($9))
                    ON CONFLICT (id) DO UPDATE SET
                        messages   = EXCLUDED.messages,
                        context    = EXCLUDED.context,
                        status     = EXCLUDED.status,
                        satisfaction = EXCLUDED.satisfaction,
                        updated_at = EXCLUDED.updated_at
                    """,
                    session.id,
                    session.user_id,
                    getattr(session, "tenant_id", "default"),
                    messages_json,
                    context_json,
                    session.status.value,
                    session.satisfaction,
                    session.created_at,
                    session.updated_at,
                )
            return True
        except Exception as exc:
            logger.error("session_save_failed", exc_info=exc, extra={"extra_fields": {
                "session_id": session.id,
            }})
            # Fallback to memory (Requirement 3.4)
            self._fallback[session.id] = session
            return False

    async def load(self, session_id: str) -> Optional[Session]:
        """
        Load a session by ID (Requirement 3.3).
        Checks DB first, then in-memory fallback.
        """
        if self._db_available:
            try:
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM sessions WHERE id = $1", session_id,
                    )
                if row is not None:
                    return self._row_to_session(row)
            except Exception as exc:
                logger.error("session_load_failed", exc_info=exc, extra={"extra_fields": {
                    "session_id": session_id,
                }})

        return self._fallback.get(session_id)

    async def list_by_user(
        self, user_id: str, tenant_id: str = "default",
    ) -> list[Session]:
        """
        Return all sessions for a given user (Requirement 3.5).
        Merges DB results with any in-memory fallback entries.
        """
        sessions: dict[str, Session] = {}

        if self._db_available:
            try:
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM sessions
                        WHERE user_id = $1 AND tenant_id = $2
                        ORDER BY updated_at DESC
                        """,
                        user_id, tenant_id,
                    )
                for row in rows:
                    s = self._row_to_session(row)
                    sessions[s.id] = s
            except Exception as exc:
                logger.error("session_list_failed", exc_info=exc, extra={"extra_fields": {
                    "user_id": user_id,
                }})

        # Merge fallback entries for the same user/tenant
        for s in self._fallback.values():
            if s.user_id == user_id and getattr(s, "tenant_id", "default") == tenant_id:
                sessions.setdefault(s.id, s)

        return list(sessions.values())

    async def upsert_messages(
        self, session_id: str, user_msg: Message, bot_msg: Message,
    ) -> bool:
        """
        Append a user + assistant message pair to an existing session
        (Requirement 3.2). Falls back to in-memory on failure.
        """
        if not self._db_available:
            s = self._fallback.get(session_id)
            if s:
                s.messages.append(user_msg)
                s.messages.append(bot_msg)
                s.updated_at = time.time()
            return s is not None

        try:
            messages_to_add = json.dumps(
                [_serialize_message(user_msg), _serialize_message(bot_msg)],
                ensure_ascii=False,
            )
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE sessions
                    SET messages   = messages || $2::jsonb,
                        updated_at = to_timestamp($3)
                    WHERE id = $1
                    """,
                    session_id,
                    messages_to_add,
                    time.time(),
                )
            return result.endswith("1")  # "UPDATE 1"
        except Exception as exc:
            logger.error("session_upsert_failed", exc_info=exc, extra={"extra_fields": {
                "session_id": session_id,
            }})
            # Fallback
            s = self._fallback.get(session_id)
            if s:
                s.messages.append(user_msg)
                s.messages.append(bot_msg)
                s.updated_at = time.time()
            return False

    async def get_all(self) -> list[Session]:
        """Return all sessions (for admin listing)."""
        sessions: dict[str, Session] = {}

        if self._db_available:
            try:
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 200",
                    )
                for row in rows:
                    s = self._row_to_session(row)
                    sessions[s.id] = s
            except Exception as exc:
                logger.error("session_get_all_failed", exc_info=exc)

        for s in self._fallback.values():
            sessions.setdefault(s.id, s)

        return list(sessions.values())

    async def rate(self, session_id: str, rating: int) -> bool:
        """Set satisfaction rating on a session."""
        rating = max(1, min(5, rating))

        if self._db_available:
            try:
                async with self._pool.acquire() as conn:
                    result = await conn.execute(
                        """
                        UPDATE sessions SET satisfaction = $2, updated_at = to_timestamp($3)
                        WHERE id = $1
                        """,
                        session_id, rating, time.time(),
                    )
                if result.endswith("1"):
                    return True
            except Exception as exc:
                logger.error("session_rate_failed", exc_info=exc)

        s = self._fallback.get(session_id)
        if s:
            s.satisfaction = rating
            return True
        return False

    # ── Internal helpers ──────────────────────────────

    def _row_to_session(self, row: Any) -> Session:
        """Convert an asyncpg Record to a Session model."""
        messages_raw = row["messages"]
        if isinstance(messages_raw, str):
            messages_raw = json.loads(messages_raw)

        context_raw = row["context"]
        if isinstance(context_raw, str):
            context_raw = json.loads(context_raw)

        messages = [_deserialize_message(m) for m in messages_raw]
        context = _deserialize_context(context_raw)

        created_at = row["created_at"]
        updated_at = row["updated_at"]

        return Session(
            id=row["id"],
            user_id=row["user_id"],
            messages=messages,
            context=context,
            status=SessionStatus(row["status"]),
            satisfaction=row["satisfaction"],
            created_at=created_at.timestamp() if hasattr(created_at, "timestamp") else float(created_at),
            updated_at=updated_at.timestamp() if hasattr(updated_at, "timestamp") else float(updated_at),
        )
