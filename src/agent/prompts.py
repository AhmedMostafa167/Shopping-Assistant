"""The agent's prompts: served from the Langfuse prompt registry, with local text as fallback."""

from dataclasses import dataclass

from langfuse import Langfuse
from langfuse.model import TextPromptClient
from structlog import get_logger

from .Templates import AGENT_SYSTEM_PROMPT, FIRST_TURN_MEMORY_INSTRUCTION

logger = get_logger(__name__)

SYSTEM_PROMPT_NAME = "shopping-agent/system"
FIRST_TURN_MEMORY_PROMPT_NAME = "shopping-agent/first-turn-memory"

# The label that marks the version the application serves by default. Releasing a new
# prompt means moving this label in Langfuse, not changing code.
PRODUCTION_LABEL = "production"
# Candidate versions carry this label while they are evaluated, before promotion.
STAGING_LABEL = "staging"

# Seeded into the registry once (scripts/seed_langfuse_prompts.py) and used as the
# fallback when the registry is not configured or cannot be reached.
LOCAL_PROMPTS = {
    SYSTEM_PROMPT_NAME: AGENT_SYSTEM_PROMPT,
    FIRST_TURN_MEMORY_PROMPT_NAME: FIRST_TURN_MEMORY_INSTRUCTION,
}


@dataclass(frozen=True)
class AgentPrompt:
    text: str
    # Set only when the text came from the registry, so traces can link to the version.
    registered: TextPromptClient | None = None


def load_prompt(
    registry: Langfuse | None, name: str, label: str = PRODUCTION_LABEL
) -> AgentPrompt:
    """Return the version of a prompt carrying the label, or the local text if unavailable."""
    local_text = LOCAL_PROMPTS[name]
    if registry is None:
        return AgentPrompt(text=local_text)

    # Cached in memory by the SDK and refreshed in the background, so calling this on
    # every turn costs nothing after the first fetch.
    prompt = registry.get_prompt(
        name, label=label, type="text", fallback=local_text
    )
    if prompt.is_fallback:
        logger.warning("prompt_registry_unavailable_using_local_text", prompt_name=name, label=label)
        return AgentPrompt(text=local_text)

    return AgentPrompt(text=prompt.compile(), registered=prompt)


def warm_prompt_cache(
    registry: Langfuse | None, label: str = PRODUCTION_LABEL
) -> dict[str, int | None]:
    """Fetch every prompt once at startup so no chat request waits on the first fetch.

    Returns the served version per prompt; None means the local text is in use.
    """
    versions = {}
    for name in LOCAL_PROMPTS:
        prompt = load_prompt(registry, name, label)
        versions[name] = prompt.registered.version if prompt.registered else None
    return versions
