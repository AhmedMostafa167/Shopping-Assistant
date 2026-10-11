from langfuse import Langfuse
from langfuse.span_filter import is_default_export_span

from .config import Settings

# The SDK only registers a client process-wide when it has keys. Without that, every
# traced call would build a throwaway client and log a warning, so a disabled client
# is registered under this placeholder instead.
DISABLED_KEY = "tracing-disabled"

# LangGraph's routing step after each model call: 1 ms, no information of its own.
NOISE_SPAN_NAMES = {"tools_condition"}


def should_export_span(span) -> bool:
    return is_default_export_span(span) and span.name not in NOISE_SPAN_NAMES


def configure_tracing(settings: Settings) -> Langfuse:
    """Create the process-wide Langfuse client. Elsewhere, use langfuse.get_client()."""
    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY or DISABLED_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY or DISABLED_KEY,
        base_url=settings.LANGFUSE_BASE_URL,
        tracing_enabled=settings.LANGFUSE_TRACING_ENABLED,
        environment=settings.LANGFUSE_TRACING_ENVIRONMENT,
        release=settings.APP_VERSION,
        should_export_span=should_export_span,
    )
