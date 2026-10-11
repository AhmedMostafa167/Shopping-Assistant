"""Create the agent's prompts in Langfuse from the local text, labelled production.

Run once per Langfuse project:  uv run python scripts/seed_langfuse_prompts.py

Prompts that already exist are left untouched: after seeding, Langfuse is the source of
truth and new versions are created there.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.prompts import LOCAL_PROMPTS, PRODUCTION_LABEL  # noqa: E402
from helpers.config import get_settings  # noqa: E402
from helpers.tracing import configure_tracing  # noqa: E402


def seed_prompts(langfuse, prompts: dict[str, str]) -> dict[str, str]:
    """Create each missing prompt as version 1. Returns what happened per prompt."""
    outcome = {}
    for name, text in prompts.items():
        if langfuse.api.prompts.list(name=name).data:
            outcome[name] = "already exists, left untouched"
            continue
        created = langfuse.create_prompt(
            name=name,
            type="text",
            prompt=text,
            labels=[PRODUCTION_LABEL],
            commit_message="Seeded from src/agent/Templates.py",
        )
        outcome[name] = f"created version {created.version}"
    return outcome


def main() -> None:
    settings = get_settings()
    if not settings.langfuse_configured:
        sys.exit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env")

    langfuse = configure_tracing(settings)
    for name, result in seed_prompts(langfuse, LOCAL_PROMPTS).items():
        print(f"{name}: {result}")
    langfuse.flush()


if __name__ == "__main__":
    main()
