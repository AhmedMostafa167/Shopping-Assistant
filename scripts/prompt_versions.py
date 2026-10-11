"""Publish a candidate prompt version to Langfuse, or promote one to production.

Publish the local text (src/agent/Templates.py) as a new version labelled for evaluation:

    uv run python scripts/prompt_versions.py publish --message "What changed and why"

Promote an evaluated version so the running application serves it:

    uv run python scripts/prompt_versions.py promote --name shopping-agent/system --version 2

A candidate is evaluated under the "staging" label first; production keeps serving the
current version until promote is run.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.prompts import LOCAL_PROMPTS, PRODUCTION_LABEL, STAGING_LABEL  # noqa: E402
from helpers.config import get_settings  # noqa: E402
from helpers.tracing import configure_tracing  # noqa: E402


def publish_candidates(langfuse, prompts: dict[str, str], message: str) -> dict[str, str]:
    """Make the staging label point at the local text of every prompt.

    A prompt whose text changed gets a new version with the commit message. An unchanged
    prompt has its production version labelled staging as well, so that evaluating under
    "staging" resolves every prompt.
    """
    outcome = {}
    for name, text in prompts.items():
        production = langfuse.get_prompt(name, label=PRODUCTION_LABEL, type="text", cache_ttl_seconds=0)
        if production.prompt == text:
            langfuse.update_prompt(
                name=name, version=production.version, new_labels=[PRODUCTION_LABEL, STAGING_LABEL]
            )
            outcome[name] = f"unchanged; version {production.version} is also staging"
            continue
        created = langfuse.create_prompt(
            name=name, type="text", prompt=text, labels=[STAGING_LABEL], commit_message=message
        )
        outcome[name] = f"created version {created.version} as staging"
    return outcome


def promote(langfuse, name: str, version: int) -> None:
    """Move the production label to an evaluated version."""
    langfuse.update_prompt(name=name, version=version, new_labels=[PRODUCTION_LABEL, STAGING_LABEL])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish", help="Publish local prompt text as a staging candidate")
    publish.add_argument("--message", required=True, help="What changed and why (stored with the version)")
    promotion = commands.add_parser("promote", help="Make a version the production one")
    promotion.add_argument("--name", required=True)
    promotion.add_argument("--version", required=True, type=int)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.langfuse_configured:
        sys.exit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env")
    langfuse = configure_tracing(settings)

    if args.command == "publish":
        for name, result in publish_candidates(langfuse, LOCAL_PROMPTS, args.message).items():
            print(f"{name}: {result}")
    else:
        promote(langfuse, args.name, args.version)
        print(f"{args.name}: version {args.version} is now production")
    langfuse.flush()


if __name__ == "__main__":
    main()
