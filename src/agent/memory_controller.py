"""Database operations for the user's long-term shopping facts."""

from models.db_schemes import Memory


class MemoryController:
    def __init__(self, memory_model, profile_model):
        self.memory_model = memory_model
        self.profile_model = profile_model

    async def read_facts(self, username: str) -> list[Memory]:
        profile = await self.profile_model.get_profile_by_username(username)
        if profile is None:
            return []
        return await self.memory_model.get_memories_by_profile(
            profile.profile_id,
            limit=50,
        )

    async def add_fact(
        self,
        username: str,
        fact_type: str,
        content: str,
        confidence: float,
    ) -> Memory:
        profile = await self.profile_model.get_profile_or_create_one(username)
        return await self.memory_model.create_memory(
            Memory(
                profile_id=profile.profile_id,
                fact_type=fact_type,
                content=content,
                confidence=confidence,
            )
        )

    async def modify_fact(
        self,
        username: str,
        fact_id: int,
        content: str,
        confidence: float,
        fact_type: str,
    ) -> Memory | None:
        profile = await self.profile_model.get_profile_by_username(username)
        if profile is None:
            return None

        fact = await self.memory_model.update_memory(
            fact_id,
            content,
            confidence,
            profile_id=profile.profile_id,
            fact_type=fact_type,
        )
        return fact
