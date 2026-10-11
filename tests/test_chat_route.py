import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from langfuse.langchain import CallbackHandler

from helpers.config import Settings
from helpers.tracing import configure_tracing
from routes import chat as chat_module
from routes.chat import chat, chat_feedback
from routes.schemas.Chat import ChatRequest, FeedbackRequest


@pytest.fixture(autouse=True)
def tracing_off():
    configure_tracing(
        Settings(
            LANGFUSE_TRACING_ENABLED=False,
            LANGFUSE_PUBLIC_KEY="",
            LANGFUSE_SECRET_KEY="",
        )
    )


class FakeGraph:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def ainvoke(self, state, config):
        self.calls.append((state, config))
        if self.error:
            raise self.error
        return {"messages": [SimpleNamespace(content="Here are two phones.")]}


def make_request(graph, conversation_uuid, known_user=True, known_conversation=True):
    profile = SimpleNamespace(profile_id=7, username="ahmed")
    conversation = SimpleNamespace(
        conversation_uuid=conversation_uuid, thread_id="thread-1"
    )

    async def get_profile_by_username(username):
        return profile if known_user else None

    async def get_by_uuid_for_profile(conversation_uuid, profile_id):
        return conversation if known_conversation else None

    app = SimpleNamespace(
        graph=graph,
        profile_model=SimpleNamespace(get_profile_by_username=get_profile_by_username),
        conversation_model=SimpleNamespace(
            get_by_uuid_for_profile=get_by_uuid_for_profile
        ),
    )
    return SimpleNamespace(app=app)


def test_chat_returns_the_agent_reply_and_hands_langfuse_to_the_graph():
    graph = FakeGraph()
    conversation_uuid = uuid4()
    body = ChatRequest(
        username="ahmed", conversation_id=conversation_uuid, message="a cheap phone"
    )

    response = asyncio.run(chat(make_request(graph, conversation_uuid), body))

    assert response.response == "Here are two phones."
    assert response.conversation_id == conversation_uuid
    assert response.trace_id is None  # tracing is off in tests

    state, config = graph.calls[0]
    assert state == {"messages": [("user", "a cheap phone")]}
    assert config["configurable"] == {"thread_id": "thread-1", "user_id": "ahmed"}
    assert len(config["callbacks"]) == 1
    assert isinstance(config["callbacks"][0], CallbackHandler)
    # Without this, retrieval steps traced inside a tool lose their parent.
    assert config["callbacks"][0].run_inline is True


def test_chat_still_returns_500_when_the_agent_fails():
    graph = FakeGraph(error=RuntimeError("model unavailable"))
    conversation_uuid = uuid4()
    body = ChatRequest(
        username="ahmed", conversation_id=conversation_uuid, message="a cheap phone"
    )

    with pytest.raises(HTTPException) as raised:
        asyncio.run(chat(make_request(graph, conversation_uuid), body))

    assert raised.value.status_code == 500


TRACE_ID = "8c6730e0bc7ed25b5a669367fbf4478e"
TRACING_ON = SimpleNamespace(LANGFUSE_TRACING_ENABLED=True)
TRACING_OFF = SimpleNamespace(LANGFUSE_TRACING_ENABLED=False)


class FakeLangfuse:
    def __init__(self):
        self.scores = []

    def create_score(self, **score):
        self.scores.append(score)


@pytest.fixture
def fake_langfuse(monkeypatch):
    client = FakeLangfuse()
    monkeypatch.setattr(chat_module, "get_client", lambda: client)
    return client


def feedback_body(conversation_uuid, **overrides):
    fields = {
        "username": "ahmed",
        "conversation_id": conversation_uuid,
        "trace_id": TRACE_ID,
        "helpful": False,
        "comment": "It ignored my budget.",
    }
    return FeedbackRequest(**{**fields, **overrides})


def test_feedback_is_recorded_as_one_updatable_score_on_the_trace(fake_langfuse):
    conversation_uuid = uuid4()
    request = make_request(FakeGraph(), conversation_uuid)

    response = asyncio.run(
        chat_feedback(request, feedback_body(conversation_uuid), TRACING_ON)
    )

    assert response.trace_id == TRACE_ID
    assert fake_langfuse.scores == [
        {
            "trace_id": TRACE_ID,
            "score_id": f"response_rating-{TRACE_ID}",
            "name": "response_rating",
            "value": 0,
            "data_type": "BOOLEAN",
            "comment": "It ignored my budget.",
        }
    ]


def test_helpful_feedback_is_scored_as_one(fake_langfuse):
    conversation_uuid = uuid4()
    request = make_request(FakeGraph(), conversation_uuid)
    body = feedback_body(conversation_uuid, helpful=True, comment=None)

    asyncio.run(chat_feedback(request, body, TRACING_ON))

    assert fake_langfuse.scores[0]["value"] == 1
    assert fake_langfuse.scores[0]["comment"] is None


def test_feedback_is_refused_when_tracing_is_off(fake_langfuse):
    conversation_uuid = uuid4()
    request = make_request(FakeGraph(), conversation_uuid)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            chat_feedback(request, feedback_body(conversation_uuid), TRACING_OFF)
        )

    assert raised.value.status_code == 503
    assert fake_langfuse.scores == []


@pytest.mark.parametrize(
    "missing", [{"known_user": False}, {"known_conversation": False}]
)
def test_feedback_for_an_unknown_user_or_conversation_is_not_recorded(
    fake_langfuse, missing
):
    conversation_uuid = uuid4()
    request = make_request(FakeGraph(), conversation_uuid, **missing)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            chat_feedback(request, feedback_body(conversation_uuid), TRACING_ON)
        )

    assert raised.value.status_code == 404
    assert fake_langfuse.scores == []


@pytest.mark.parametrize("trace_id", ["", "not-a-trace-id", TRACE_ID.upper(), TRACE_ID + "0"])
def test_feedback_rejects_a_malformed_trace_id(trace_id):
    with pytest.raises(ValidationError):
        feedback_body(uuid4(), trace_id=trace_id)

