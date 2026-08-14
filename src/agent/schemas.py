from pydantic import BaseModel, Field
from typing import Optional


class SearchCatalogInput(BaseModel):
    query: str = Field(description="The user's product search intent, in English.")
    category_name: str = Field(description="Category to search within, e.g. 'electronics_cellphones'.")
    top_k: int = Field(default=10, description="Number of products to return.")


class FilterProductsInput(BaseModel):
    category_name: str
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_rating: Optional[float] = None


class ReadMemoryInput(BaseModel):
    query: str = Field(description="What to recall, e.g. 'does the user have preferences relevant to headphones?'")


class WriteMemoryInput(BaseModel):
    message: str = Field(description="The raw user message to extract candidate facts from.")
 