from uuid import UUID

from pydantic import BaseModel, Field

# The whole conversation is re-sent to the model on every call and kept for later turns,
# so one huge message is paid for again on every turn and can exceed the provider's
# per-request token limit, after which the conversation can never be answered again.
MAX_MESSAGE_CHARACTERS = 2000


class ChatRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARACTERS)


class ProductCard(BaseModel):
    product_id: int
    title: str
    price: float | None = None
    recommendation_score: float | None = None
    image: str | None = None


class ChatResponse(BaseModel):
    conversation_id: UUID
    response: str
    trace_id: str | None = None
    # Products the agent's tools returned in this turn, for the client to show as cards.
    products: list[ProductCard] = []


class FeedbackRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    conversation_id: UUID
    # The trace_id returned by POST /api/v1/chat for the reply being rated.
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    helpful: bool
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    message: str
    trace_id: str
