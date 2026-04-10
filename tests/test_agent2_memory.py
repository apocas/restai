"""Tests for agent2 session memory (in-memory backend)."""
import asyncio
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import patch

from restai.agent2.memory import (
    LOCAL_SESSION_CAP,
    get_session,
    save_session,
)
from restai.agent2.types import (
    AgentSession,
    Message,
    TextBlock,
    ToolUseBlock,
)


def _make_brain():
    """Create a minimal mock brain with no Redis configured."""
    brain = SimpleNamespace(_agent2_sessions=OrderedDict(), _agent2_redis=None, _agent2_redis_url=None)
    return brain


@patch("restai.agent2.memory.config.build_redis_url", return_value=None)
def test_get_session_returns_empty_for_unknown_chat_id(_mock):
    brain = _make_brain()
    session = asyncio.run(get_session(brain, "nonexistent-id"))
    assert isinstance(session, AgentSession)
    assert session.messages == []


@patch("restai.agent2.memory.config.build_redis_url", return_value=None)
def test_save_and_get_session_round_trip(_mock):
    brain = _make_brain()

    msg = Message(role="user", content=[TextBlock(text="hello")])
    session = AgentSession(messages=[msg])

    asyncio.run(save_session(brain, "chat-1", session))
    loaded = asyncio.run(get_session(brain, "chat-1"))

    assert len(loaded.messages) == 1
    assert loaded.messages[0].role == "user"
    assert len(loaded.messages[0].content) == 1
    assert isinstance(loaded.messages[0].content[0], TextBlock)
    assert loaded.messages[0].content[0].text == "hello"


@patch("restai.agent2.memory.config.build_redis_url", return_value=None)
def test_lru_eviction(_mock):
    brain = _make_brain()

    # Save LOCAL_SESSION_CAP + 1 sessions
    async def fill():
        for i in range(LOCAL_SESSION_CAP + 1):
            msg = Message(role="user", content=[TextBlock(text=f"msg-{i}")])
            session = AgentSession(messages=[msg])
            await save_session(brain, f"chat-{i}", session)

    asyncio.run(fill())

    # The oldest session (chat-0) should have been evicted
    oldest = asyncio.run(get_session(brain, "chat-0"))
    assert oldest.messages == [], "Oldest session should have been evicted"

    # The newest session should still be present
    newest = asyncio.run(get_session(brain, f"chat-{LOCAL_SESSION_CAP}"))
    assert len(newest.messages) == 1
    assert newest.messages[0].content[0].text == f"msg-{LOCAL_SESSION_CAP}"


@patch("restai.agent2.memory.config.build_redis_url", return_value=None)
def test_message_serialization_round_trip(_mock):
    """TextBlock and ToolUseBlock survive save/load through JSON serialization."""
    brain = _make_brain()

    messages = [
        Message(role="user", content=[TextBlock(text="What is 2+2?")]),
        Message(
            role="assistant",
            content=[
                TextBlock(text="Let me calculate that."),
                ToolUseBlock(id="call_1", name="calculator", input={"expr": "2+2"}),
            ],
        ),
    ]
    session = AgentSession(messages=messages)

    async def roundtrip():
        await save_session(brain, "chat-ser", session)
        return await get_session(brain, "chat-ser")

    loaded = asyncio.run(roundtrip())
    assert len(loaded.messages) == 2

    m0 = loaded.messages[0]
    assert m0.role == "user"
    assert isinstance(m0.content[0], TextBlock)
    assert m0.content[0].text == "What is 2+2?"

    m1 = loaded.messages[1]
    assert m1.role == "assistant"
    assert len(m1.content) == 2
    assert isinstance(m1.content[0], TextBlock)
    assert isinstance(m1.content[1], ToolUseBlock)
    assert m1.content[1].name == "calculator"
    assert m1.content[1].input == {"expr": "2+2"}
