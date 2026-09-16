"""Long-term profile and memory orchestration for the shopping assistant."""

import json
from models.db_schemes import ExtractionResult, Memory
from helpers.logging import get_logger
from models.enums import LogEventEnums

from .Templates import CONFLICT_PROMPT, EXTRACTION_PROMPT

logger = get_logger(__name__)


class MemoryController:
    def __init__(self, llm_provider, memory_model, profile_model):
        self.llm_provider = llm_provider
        self.memory_model = memory_model
        self.profile_model = profile_model

    async def extract_facts(self, message: str) -> list:
        raw = await self.llm_provider.agenerate_text(
            prompt=EXTRACTION_PROMPT.format(message=message)
        )
        if not raw:
            logger.error(LogEventEnums.MEMORY_EXTRACTION_FAILED.value, reason="empty_response")
            return []

        try:
            parsed = ExtractionResult.model_validate_json(raw)
        except Exception as exc:
            logger.exception(LogEventEnums.MEMORY_EXTRACTION_FAILED.value, error=str(exc))
            return []
        return parsed.facts

    async def resolve_and_write(self, username: str, message: str) -> list[str]:
        profile = await self.profile_model.get_profile_or_create_one(username)
        facts = await self.extract_facts(message)
        actions: list[str] = []

        for fact in facts:
            existing = await self.memory_model.get_memories_by_profile(
                profile.profile_id,
                fact.fact_type,
            )

            if existing:
                existing_str = "\n".join(
                    f"id={memory.memory_id}: {memory.content}"
                    for memory in existing
                )
                raw = await self.llm_provider.agenerate_text(
                    prompt=CONFLICT_PROMPT.format(
                        fact_type=fact.fact_type,
                        existing_facts=existing_str,
                        new_content=fact.content,
                    )
                )

                conflicting_id = -1
                if raw:
                    try:
                        conflicting_id = json.loads(raw).get(
                            "conflicting_memory_id",
                            -1,
                        )
                    except Exception as exc:
                        logger.exception(
                            LogEventEnums.MEMORY_CONFLICT_PARSE_FAILED.value,
                            error=str(exc),
                        )

                if conflicting_id != -1:
                    updated = await self.memory_model.update_memory(
                        conflicting_id,
                        fact.content,
                        fact.confidence,
                        profile_id=profile.profile_id,
                    )
                    if updated:
                        actions.append(
                            f"updated memory {conflicting_id}: {fact.content}"
                        )
                        continue

            await self.memory_model.create_memory(
                Memory(
                    profile_id=profile.profile_id,
                    fact_type=fact.fact_type,
                    content=fact.content,
                    confidence=fact.confidence,
                    source_turn=message,
                )
            )
            actions.append(f"stored new fact: {fact.content}")

        return actions

    async def read_facts(self, username: str) -> list[Memory]:
        profile = await self.profile_model.get_profile_by_username(username)
        if profile is None:
            return []
        return await self.memory_model.get_memories_by_profile(
            profile.profile_id,
            limit=50,
        )
