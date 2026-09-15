from sqlalchemy import select

from .BaseDataModel import BaseDataModel
from .db_schemes import Memory


class MemoryModel(BaseDataModel):
    def __init__(self, db_client: object):
        super().__init__(db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def create_memory(self, memory: Memory) -> Memory:
        async with self.db_client() as session:
            async with session.begin():
                session.add(memory)
            await session.refresh(memory)
            return memory

    async def get_memories_by_profile(
        self,
        profile_id: int,
        fact_type: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        # limit = max(1, min(limit, 100))
        query = (
            select(Memory)
            .where(Memory.profile_id == profile_id)
            .order_by(Memory.confidence.desc(), Memory.memory_id.desc())
            .limit(limit)
        )
        if fact_type is not None:
            query = query.where(Memory.fact_type == fact_type)

        async with self.db_client() as session:
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_memory(
        self,
        memory_id: int,
        content: str,
        confidence: float,
        *,
        profile_id: int,
    ) -> Memory | None:
        query = select(Memory).where(
            Memory.memory_id == memory_id,
            Memory.profile_id == profile_id,
        )

        async with self.db_client() as session:
            result = await session.execute(query)
            memory = result.scalar_one_or_none()
            if memory is None:
                return None

            memory.content = content
            memory.confidence = confidence
            await session.commit()
            await session.refresh(memory)
            return memory
