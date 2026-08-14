"""
Fact extraction and conflict resolution. Both are the actual differentiating logic of this
project — kept as one module inside agent/ rather than split across tool files, so this logic
is testable directly without going through LangGraph's tool-calling machinery.

Conflict detection here is an LLM judgment call over the (typically small) set of existing
same-type facts for one profile — not embedding similarity search. Deliberate v1 simplification:
per-user fact counts are small enough that showing the LLM all of them is cheap, and it avoids
standing up a second vector table just for memory. Revisit only if that stops being true.
"""
import json
import logging
from models.db_schemes import Memory, ExtractionResult
from .Templates import EXTRACTION_PROMPT, CONFLICT_PROMPT

logger = logging.getLogger("uvicorn")


class MemoryController:
    def __init__(self, llm_provider, memory_model, profile_model):
        self.llm_provider = llm_provider
        self.memory_model = memory_model
        self.profile_model = profile_model

    async def extract_facts(self, message: str) -> list:
        raw = self.llm_provider.generate_text(prompt=EXTRACTION_PROMPT.format(message=message))
        if not raw:
            logger.error("Fact extraction returned nothing")
            return []
        try:
            parsed = ExtractionResult.model_validate_json(raw)
        except Exception as e:
            logger.error(f"Failed to parse extraction result: {e} — raw: {raw}")
            return []
        return parsed.facts

    async def resolve_and_write(self, username: str, message: str) -> list[str]:
        profile = await self.profile_model.get_profile_or_create_one(username)
        facts = await self.extract_facts(message)
        actions = []

        for fact in facts:
            existing = await self.memory_model.get_memories_by_profile(profile.profile_id, fact.fact_type)

            if existing:
                existing_str = "\n".join(f"id={m.memory_id}: {m.content}" for m in existing)
                raw = self.llm_provider.generate_text(
                    prompt=CONFLICT_PROMPT.format(
                        fact_type=fact.fact_type, existing_facts=existing_str, new_content=fact.content
                    )
                )
                conflicting_id = -1
                if raw:
                    try:
                        conflicting_id = json.loads(raw).get("conflicting_memory_id", -1)
                    except Exception as e:
                        logger.error(f"Failed to parse conflict check: {e} — raw: {raw}")

                if conflicting_id and conflicting_id != -1:
                    await self.memory_model.update_memory(conflicting_id, fact.content, fact.confidence)
                    actions.append(f"updated memory {conflicting_id}: {fact.content}")
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
        # Returns all stored facts for this profile — at current per-user fact volumes, a full
        # read is cheap enough that relevance-filtering over memory isn't worth the complexity
        # yet, unlike catalog search, which genuinely needs it.
        profile = await self.profile_model.get_profile_by_username(username)
        if profile is None:
            return []
        return await self.memory_model.get_memories_by_profile(profile.profile_id)