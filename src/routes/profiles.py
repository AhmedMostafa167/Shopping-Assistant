from fastapi import APIRouter, Request

from .schemas.Profile import MemoryFact


profile_router = APIRouter(
    prefix="/api/v1/profiles",
    tags=["profiles"],
)


# Like the chat endpoints, this trusts the username: there is no authentication yet.
@profile_router.get("/{username}/memories", response_model=list[MemoryFact])
async def list_memories(request: Request, username: str):
    facts = await request.app.memory_controller.read_facts(username)
    return [
        MemoryFact(
            fact_id=fact.memory_id,
            fact_type=fact.fact_type,
            content=fact.content,
            confidence=fact.confidence,
        )
        for fact in facts
    ]
