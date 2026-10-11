import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from agent import graph as graph_module
from agent.prompts import (
    FIRST_TURN_MEMORY_PROMPT_NAME,
    LOCAL_PROMPTS,
    SYSTEM_PROMPT_NAME,
    load_prompt,
    warm_prompt_cache,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prompt_versions import promote, publish_candidates  # noqa: E402
from seed_langfuse_prompts import seed_prompts  # noqa: E402


class FakeRegistry:
    """Stands in for the Langfuse client: serves prompts, or fails over to the fallback."""

    def __init__(self, texts=None, reachable=True):
        self.texts = texts or {}
        self.reachable = reachable
        self.requests = []
        self.created = []
        self.api = SimpleNamespace(prompts=SimpleNamespace(list=self._list))

    def get_prompt(self, name, *, label, type, fallback):
        self.requests.append((name, label))
        if not self.reachable:
            return SimpleNamespace(is_fallback=True, compile=lambda: fallback)
        return SimpleNamespace(
            is_fallback=False, version=3, name=name, compile=lambda: self.texts[name]
        )

    def _list(self, name):
        return SimpleNamespace(data=[name] if name in self.texts else [])

    def create_prompt(self, **prompt):
        self.created.append(prompt)
        return SimpleNamespace(version=1)


def test_local_text_is_used_when_no_registry_is_configured():
    prompt = load_prompt(None, SYSTEM_PROMPT_NAME)

    assert prompt.text == LOCAL_PROMPTS[SYSTEM_PROMPT_NAME]
    assert prompt.registered is None


def test_the_production_version_is_requested_from_the_registry():
    registry = FakeRegistry({SYSTEM_PROMPT_NAME: "You are a registry prompt."})

    prompt = load_prompt(registry, SYSTEM_PROMPT_NAME)

    assert registry.requests == [(SYSTEM_PROMPT_NAME, "production")]
    assert prompt.text == "You are a registry prompt."
    assert prompt.registered.version == 3


def test_a_candidate_label_can_be_requested_instead_of_production():
    registry = FakeRegistry(dict.fromkeys(LOCAL_PROMPTS, "candidate text"))

    load_prompt(registry, SYSTEM_PROMPT_NAME, "staging")
    warm_prompt_cache(registry, "staging")

    assert {label for _, label in registry.requests} == {"staging"}


def test_an_unreachable_registry_falls_back_to_local_text_without_linking():
    prompt = load_prompt(FakeRegistry(reachable=False), SYSTEM_PROMPT_NAME)

    assert prompt.text == LOCAL_PROMPTS[SYSTEM_PROMPT_NAME]
    assert prompt.registered is None


def test_startup_warm_up_reports_the_served_version_of_every_prompt():
    registry = FakeRegistry(dict.fromkeys(LOCAL_PROMPTS, "text"))

    assert warm_prompt_cache(registry) == dict.fromkeys(LOCAL_PROMPTS, 3)
    assert warm_prompt_cache(None) == dict.fromkeys(LOCAL_PROMPTS, None)


def test_seeding_creates_missing_prompts_as_production_and_skips_existing_ones():
    registry = FakeRegistry({SYSTEM_PROMPT_NAME: "already in Langfuse"})

    outcome = seed_prompts(registry, LOCAL_PROMPTS)

    assert [p["name"] for p in registry.created] == [FIRST_TURN_MEMORY_PROMPT_NAME]
    assert registry.created[0]["labels"] == ["production"]
    assert registry.created[0]["prompt"] == LOCAL_PROMPTS[FIRST_TURN_MEMORY_PROMPT_NAME]
    assert "left untouched" in outcome[SYSTEM_PROMPT_NAME]


class RecordingChatModel:
    """A chat model double that records the messages it was sent."""

    def __init__(self):
        self.calls = []

    def bind_tools(self, tools):
        return self

    def with_config(self, **config):
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content="Hello!")


def run_first_turn(prompt_registry, monkeypatch):
    for factory in (
        "make_search_catalog_tool",
        "make_filter_products_tool",
        "make_read_memory_tool",
        "make_write_memory_tool",
    ):
        monkeypatch.setattr(graph_module, factory, lambda dependency: _noop_tool)
    chat_model = RecordingChatModel()
    graph = graph_module.build_graph(
        SimpleNamespace(chat_model=chat_model),
        None,
        None,
        None,
        checkpointer=None,
        prompt_registry=prompt_registry,
    )
    asyncio.run(graph.ainvoke({"messages": [("user", "hi")]}))
    return [message.content for message in chat_model.calls[0]]


def _noop_tool() -> str:
    """Do nothing."""
    return ""


def test_the_agent_sends_the_registry_prompts_to_the_model(monkeypatch):
    registry = FakeRegistry(
        {
            SYSTEM_PROMPT_NAME: "SYSTEM FROM LANGFUSE",
            FIRST_TURN_MEMORY_PROMPT_NAME: "FIRST TURN FROM LANGFUSE",
        }
    )
    monkeypatch.setattr(
        graph_module, "propagate_attributes", lambda prompt: _NullContext()
    )

    sent = run_first_turn(registry, monkeypatch)

    assert sent == ["SYSTEM FROM LANGFUSE", "FIRST TURN FROM LANGFUSE", "hi"]


def test_the_agent_sends_the_local_prompts_without_a_registry(monkeypatch):
    sent = run_first_turn(None, monkeypatch)

    assert sent == [
        LOCAL_PROMPTS[SYSTEM_PROMPT_NAME],
        LOCAL_PROMPTS[FIRST_TURN_MEMORY_PROMPT_NAME],
        "hi",
    ]


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class VersionedRegistry:
    """A registry double with versions and labels, for the publish and promote steps."""

    def __init__(self, production_texts):
        self.production = {name: (1, text) for name, text in production_texts.items()}
        self.created = []
        self.label_updates = []

    def get_prompt(self, name, *, label, type, cache_ttl_seconds):
        version, text = self.production[name]
        return SimpleNamespace(version=version, prompt=text)

    def create_prompt(self, **prompt):
        self.created.append(prompt)
        return SimpleNamespace(version=2)

    def update_prompt(self, *, name, version, new_labels):
        self.label_updates.append((name, version, new_labels))


def test_publishing_creates_a_staging_version_only_for_changed_prompts():
    registry = VersionedRegistry(
        {SYSTEM_PROMPT_NAME: "old system text", FIRST_TURN_MEMORY_PROMPT_NAME: "same text"}
    )
    local = {SYSTEM_PROMPT_NAME: "new system text", FIRST_TURN_MEMORY_PROMPT_NAME: "same text"}

    publish_candidates(registry, local, "Store only lasting facts")

    assert len(registry.created) == 1
    assert registry.created[0]["name"] == SYSTEM_PROMPT_NAME
    assert registry.created[0]["labels"] == ["staging"]  # production is not moved
    assert registry.created[0]["commit_message"] == "Store only lasting facts"
    assert registry.label_updates == [(FIRST_TURN_MEMORY_PROMPT_NAME, 1, ["production", "staging"])]


def test_promoting_moves_the_production_label_to_the_version():
    registry = VersionedRegistry({SYSTEM_PROMPT_NAME: "text"})

    promote(registry, SYSTEM_PROMPT_NAME, 2)

    assert registry.label_updates == [(SYSTEM_PROMPT_NAME, 2, ["production", "staging"])]

