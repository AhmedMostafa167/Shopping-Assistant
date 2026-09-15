from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    conversation_id: UUID
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    conversation_id: UUID
    response: str
