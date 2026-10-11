import pytest
from pydantic import ValidationError

from helpers.config import Settings


def test_tracing_enabled_without_keys_fails_at_startup():
    with pytest.raises(ValidationError, match="LANGFUSE_TRACING_ENABLED"):
        Settings(
            LANGFUSE_TRACING_ENABLED=True,
            LANGFUSE_PUBLIC_KEY="",
            LANGFUSE_SECRET_KEY="",
        )


def test_tracing_enabled_with_keys_is_accepted():
    settings = Settings(
        LANGFUSE_TRACING_ENABLED=True,
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    assert settings.LANGFUSE_TRACING_ENABLED is True


def test_tracing_is_off_by_default_and_needs_no_keys():
    settings = Settings(
        LANGFUSE_TRACING_ENABLED=False,
        LANGFUSE_PUBLIC_KEY="",
        LANGFUSE_SECRET_KEY="",
    )
    assert settings.LANGFUSE_TRACING_ENABLED is False
