from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    # Temporary identity until authentication is added.
    username: str = Field(min_length=1, max_length=255)

    title: str | None = Field(
        default=None,
        max_length=255,
    )


class ConversationResponse(BaseModel):
    conversation_id: UUID
    title: str | None = None


class ConversationListItem(BaseModel):
    conversation_id: UUID
    title: str | None = None
