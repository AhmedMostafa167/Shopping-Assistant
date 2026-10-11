from langfuse import get_client, observe
from langfuse.langchain import CallbackHandler
from opentelemetry.sdk.trace import TracerProvider

from helpers.config import Settings
from helpers.tracing import configure_tracing, should_export_span


def test_app_code_runs_unchanged_when_tracing_is_off(caplog):
    settings = Settings(
        LANGFUSE_TRACING_ENABLED=False,
        LANGFUSE_PUBLIC_KEY="",
        LANGFUSE_SECRET_KEY="",
    )
    client = configure_tracing(settings)

    @observe(name="add-one")
    def add_one(value):
        return value + 1

    with caplog.at_level("WARNING", logger="langfuse"):
        with get_client().start_as_current_observation(as_type="span", name="chat-turn"):
            assert add_one(1) == 2
        CallbackHandler()
        client.flush()

    assert caplog.records == []


def make_span(name):
    # A span as the Langfuse SDK would create it, with no exporter attached.
    return TracerProvider().get_tracer("langfuse-sdk").start_span(name)


def test_routing_noise_is_not_exported_but_real_steps_are():
    assert should_export_span(make_span("hybrid-search")) is True
    assert should_export_span(make_span("tools_condition")) is False
