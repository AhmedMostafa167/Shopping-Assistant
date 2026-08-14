from .BaseDataModel import BaseDataModel
from .db_schemes import Memory
from sqlalchemy.future import select


class MemoryModel(BaseDataModel):
    def __init__(self, db_client: object):
        super().__init__(db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        memory = cls(db_client)
        return memory

    async def create_memory(self, memory: Memory) -> Memory:
        async with self.db_client() as session:
            async with session.begin():
                session.add(memory)
            await session.refresh(memory)
            return memory

    async def get_memories_by_profile(self, profile_id: int, fact_type: str = None) -> list[Memory]:
        async with self.db_client() as session:
            query = select(Memory).where(Memory.profile_id == profile_id)
            if fact_type is not None:
                query = query.where(Memory.fact_type == fact_type)
            result = await session.execute(query)
            return result.scalars().all()

    async def update_memory(self, memory_id: int, content: str, confidence: float) -> Memory | None:
        async with self.db_client() as session:
            query = select(Memory).where(Memory.memory_id == memory_id)
            result = await session.execute(query)
            memory = result.scalar_one_or_none()

            if memory is None:
                return None

            memory.content = content
            memory.confidence = confidence
            async with session.begin():
                session.add(memory)
            await session.refresh(memory)
            return memory