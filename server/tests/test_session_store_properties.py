"""
Property-based tests for SessionStore in server/session_store.py.

Property 3: Session round trip — save then load produces equivalent session
Property 4: User query completeness — list_by_user returns all and only that user's sessions

Validates: Requirements 3.3, 3.5
"""

from __future__ import annotations

import asyncio
import sys

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from server.models import (
    Message,
    MessageMetadata,
    Session,
    SessionContext,
    SessionStatus,
    Sentiment,
    IntentCategory,
)
from server.session_store import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously for Hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_store() -> SessionStore:
    """Create an in-memory-only SessionStore (no DB URL)."""
    store = SessionStore(db_url="")
    _run(store.init())
    return store


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_sentiments = st.sampled_from(list(Sentiment))
_intents = st.sampled_from(list(IntentCategory))
_statuses = st.sampled_from(list(SessionStatus))
_roles = st.sampled_from(["user", "assistant", "system"])

_user_ids = st.text(
    min_size=1, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
)
_session_ids = st.text(
    min_size=8, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
)

_message_metadata = st.builds(
    MessageMetadata,
    sentiment=st.one_of(st.none(), _sentiments),
    intent=st.one_of(st.none(), _intents),
    confidence=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    language=st.one_of(st.none(), st.just("zh"), st.just("en")),
    tools_used=st.lists(st.text(min_size=1, max_size=20), max_size=3),
    knowledge_refs=st.lists(st.text(min_size=1, max_size=30), max_size=3),
    response_time_ms=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
)

_messages = st.builds(
    Message,
    id=st.text(min_size=4, max_size=12, alphabet="abcdef0123456789"),
    role=_roles,
    content=st.text(min_size=0, max_size=200),
    timestamp=st.floats(min_value=1_000_000_000.0, max_value=2_000_000_000.0, allow_nan=False),
    metadata=st.one_of(st.none(), _message_metadata),
)

_session_contexts = st.builds(
    SessionContext,
    user_name=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    language=st.sampled_from(["zh", "en", "ja"]),
    sentiment_trend=st.lists(_sentiments, max_size=5),
    current_intent=st.one_of(st.none(), _intents),
    extracted_entities=st.dictionaries(
        keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
        values=st.text(min_size=0, max_size=20),
        max_size=3,
    ),
    escalation_reason=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    ticket_id=st.one_of(st.none(), st.text(min_size=1, max_size=16)),
)

_sessions = st.builds(
    Session,
    id=_session_ids,
    user_id=_user_ids,
    messages=st.lists(_messages, min_size=0, max_size=5),
    context=_session_contexts,
    created_at=st.floats(min_value=1_000_000_000.0, max_value=2_000_000_000.0, allow_nan=False),
    updated_at=st.floats(min_value=1_000_000_000.0, max_value=2_000_000_000.0, allow_nan=False),
    status=_statuses,
    satisfaction=st.one_of(st.none(), st.integers(min_value=1, max_value=5)),
)


# ---------------------------------------------------------------------------
# Property 3: Session round trip — save then load produces equivalent session
# Feature: enterprise-agent-optimization, Property 3: 会话持久化 Round Trip
# ---------------------------------------------------------------------------

@given(session=_sessions)
@settings(max_examples=50)
def test_save_then_load_returns_equivalent_session(session: Session) -> None:
    """
    For any valid Session, saving it then loading by session_id must produce
    a Session with equivalent messages, context, status, and satisfaction.
    """
    store = _make_store()
    _run(store.save(session))
    loaded = _run(store.load(session.id))

    assert loaded is not None, f"Session {session.id} not found after save"
    assert loaded.id == session.id
    assert loaded.user_id == session.user_id
    assert loaded.status == session.status
    assert loaded.satisfaction == session.satisfaction

    # Messages: compare count and content
    assert len(loaded.messages) == len(session.messages)
    for orig, restored in zip(session.messages, loaded.messages):
        assert restored.id == orig.id
        assert restored.role == orig.role
        assert restored.content == orig.content

    # Context: compare key fields
    assert loaded.context.language == session.context.language
    assert loaded.context.user_name == session.context.user_name
    assert loaded.context.current_intent == session.context.current_intent
    assert loaded.context.extracted_entities == session.context.extracted_entities


@given(session=_sessions)
@settings(max_examples=25)
def test_save_overwrites_previous_session(session: Session) -> None:
    """
    Saving a session twice (with updated fields) must reflect the latest state
    on subsequent load.
    """
    store = _make_store()
    _run(store.save(session))

    # Mutate and re-save
    session.status = SessionStatus.RESOLVED
    session.satisfaction = 5
    _run(store.save(session))

    loaded = _run(store.load(session.id))
    assert loaded is not None
    assert loaded.status == SessionStatus.RESOLVED
    assert loaded.satisfaction == 5


@given(session_id=_session_ids)
@settings(max_examples=25)
def test_load_nonexistent_session_returns_none(session_id: str) -> None:
    """Loading a session_id that was never saved must return None."""
    store = _make_store()
    loaded = _run(store.load(session_id))
    assert loaded is None


@given(
    session=_sessions,
    user_msg=_messages,
    bot_msg=_messages,
)
@settings(max_examples=25)
def test_upsert_messages_appends_to_session(
    session: Session, user_msg: Message, bot_msg: Message,
) -> None:
    """
    After saving a session and upserting a message pair, loading the session
    must contain the original messages plus the two new ones.
    """
    store = _make_store()
    original_count = len(session.messages)
    _run(store.save(session))

    _run(store.upsert_messages(session.id, user_msg, bot_msg))

    loaded = _run(store.load(session.id))
    assert loaded is not None
    assert len(loaded.messages) == original_count + 2
    assert loaded.messages[-2].id == user_msg.id
    assert loaded.messages[-1].id == bot_msg.id


# ---------------------------------------------------------------------------
# Property 4: User query completeness — list_by_user returns all and only
#              that user's sessions
# Feature: enterprise-agent-optimization, Property 4: 按用户查询会话完整性
# ---------------------------------------------------------------------------

@given(
    target_user=_user_ids,
    target_sessions=st.lists(_sessions, min_size=1, max_size=8),
    other_user=_user_ids,
    other_sessions=st.lists(_sessions, min_size=0, max_size=5),
)
@settings(max_examples=50)
def test_list_by_user_returns_only_target_users_sessions(
    target_user: str,
    target_sessions: list[Session],
    other_user: str,
    other_sessions: list[Session],
) -> None:
    """
    For any set of sessions belonging to multiple users, querying by a specific
    user_id must return all and only sessions belonging to that user.
    """
    assume(target_user != other_user)

    store = _make_store()

    # Assign unique IDs and correct user_ids, use default tenant
    all_target_ids = set()
    for i, s in enumerate(target_sessions):
        s.id = f"target_{i}_{s.id[:8]}"
        s.user_id = target_user
        all_target_ids.add(s.id)
        _run(store.save(s))

    all_other_ids = set()
    for i, s in enumerate(other_sessions):
        s.id = f"other_{i}_{s.id[:8]}"
        s.user_id = other_user
        all_other_ids.add(s.id)
        _run(store.save(s))

    # Query for target user
    results = _run(store.list_by_user(target_user, tenant_id="default"))
    result_ids = {s.id for s in results}

    # All target sessions must be present
    assert all_target_ids.issubset(result_ids), (
        f"Missing sessions: {all_target_ids - result_ids}"
    )

    # No other user's sessions should appear
    assert result_ids.isdisjoint(all_other_ids), (
        f"Leaked sessions from other user: {result_ids & all_other_ids}"
    )


@given(
    user_id=_user_ids,
    sessions=st.lists(_sessions, min_size=0, max_size=10),
)
@settings(max_examples=50)
def test_list_by_user_count_matches_saved(
    user_id: str, sessions: list[Session],
) -> None:
    """
    The number of sessions returned by list_by_user must equal the number
    of distinct sessions saved for that user.
    """
    store = _make_store()

    saved_ids = set()
    for i, s in enumerate(sessions):
        s.id = f"sess_{i}_{s.id[:8]}"
        s.user_id = user_id
        saved_ids.add(s.id)
        _run(store.save(s))

    results = _run(store.list_by_user(user_id, tenant_id="default"))
    assert len(results) == len(saved_ids)


@given(user_id=_user_ids)
@settings(max_examples=25)
def test_list_by_user_empty_when_no_sessions(user_id: str) -> None:
    """Querying a user with no saved sessions must return an empty list."""
    store = _make_store()
    results = _run(store.list_by_user(user_id, tenant_id="default"))
    assert results == []


@given(
    users=st.lists(
        _user_ids, min_size=2, max_size=5, unique=True,
    ),
    sessions_per_user=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=25)
def test_list_by_user_isolates_across_multiple_users(
    users: list[str], sessions_per_user: int,
) -> None:
    """
    With N users each having M sessions, querying any single user must
    return exactly M sessions, all belonging to that user.
    """
    store = _make_store()

    user_session_ids: dict[str, set[str]] = {}
    counter = 0
    for uid in users:
        user_session_ids[uid] = set()
        for j in range(sessions_per_user):
            sid = f"multi_{counter}"
            counter += 1
            s = Session(id=sid, user_id=uid)
            _run(store.save(s))
            user_session_ids[uid].add(sid)

    for uid in users:
        results = _run(store.list_by_user(uid, tenant_id="default"))
        result_ids = {s.id for s in results}
        assert result_ids == user_session_ids[uid], (
            f"User {uid}: expected {user_session_ids[uid]}, got {result_ids}"
        )
        # Every returned session must belong to the queried user
        for s in results:
            assert s.user_id == uid
