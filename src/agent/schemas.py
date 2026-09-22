from typing import Literal

from pydantic import BaseModel, Field


class SearchCatalogInput(BaseModel):
    query: str = Field(description="The user's product search intent, in English.")
    category_name: str = Field(
        description="Category to search within, e.g. 'electronics_cellphones'."
    )
    top_k: int = Field(default=5, description="Number of products to return.")


class FilterProductsInput(BaseModel):
    category_name: str
    min_price: float | None = None
    max_price: float | None = None
    min_rating: float | None = None


class ReadMemoryInput(BaseModel):
    """No user arguments are needed; the current user comes from RunnableConfig."""


class WriteMemoryInput(BaseModel):
    operation: Literal["add", "modify"] = Field(
        description="Whether to add a new fact or modify an existing fact."
    )
    fact: str = Field(
        min_length=1,
        description="A concise, standalone fact about the user."
    )
    fact_type: Literal["preference", "constraint", "history"] = Field(
        description="The category of the user fact."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that the fact was explicitly stated or strongly supported."
    )
    fact_id: int | None = Field(
        default=None,
        description="The existing fact ID; required when operation is modify."
    )
