from pydantic import BaseModel

class VectorSearchResult(BaseModel):
    product_id: int
    score: float