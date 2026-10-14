from pydantic import BaseModel


class MemoryFact(BaseModel):
    fact_id: int
    fact_type: str
    content: str
    confidence: float
