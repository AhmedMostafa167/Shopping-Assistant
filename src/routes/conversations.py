from fastapi import APIRouter, HTTPException, Request, status

from helpers.logging import get_logger
from models.enums import LogEventEnums
from .schemas.Conversation import (
    ConversationResponse,
    CreateConversationRequest,
)

logger = get_logger(__name__)


conversation_router = APIRouter(
    prefix="/api/v1/conversations",
)


@conversation_router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED,)
async def create_conversation(request: Request, body: CreateConversationRequest,):
    
    profile = await request.app.profile_model.get_profile_or_create_one(body.username)

    # ConversationModel generates and persists the LangGraph thread_id.
    conversation = await request.app.conversation_model.create_conversation(
        profile_id=profile.profile_id,
        title=body.title,
    )

    logger.info(
        LogEventEnums.CONVERSATION_CREATED.value,
        conversation_id=str(conversation.conversation_uuid),
        profile_id=profile.profile_id,
    )

    return ConversationResponse(
        conversation_id=conversation.conversation_uuid,
        title=conversation.title,
    )
