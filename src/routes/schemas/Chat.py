from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    conversation_id: UUID
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    conversation_id: UUID
    response: str
    trace_id: str | None = None


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
