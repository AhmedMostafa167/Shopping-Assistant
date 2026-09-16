from fastapi import APIRouter, HTTPException, Request, status

from helpers.logging import get_logger
from models.enums import LogEventEnums, MessageEnums
from .schemas.Chat import ChatRequest, ChatResponse


logger = get_logger(__name__)


chat_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
)


@chat_router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    logger.info(
        LogEventEnums.CHAT_REQUEST_STARTED.value,
        conversation_id=str(body.conversation_id),
        username=body.username,
    )
    profile = await request.app.profile_model.get_profile_by_username(
        body.username
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MessageEnums.USER_PROFILE_NOT_FOUND.value,
        )

    conversation = (
        await request.app.conversation_model.get_by_uuid_for_profile(
            conversation_uuid=body.conversation_id,
            profile_id=profile.profile_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MessageEnums.CONVERSATION_NOT_FOUND.value,
        )

    config = {
        "configurable": {
            "thread_id": conversation.thread_id,
            "user_id": profile.username,
        }
    }

    try:
        result = await request.app.graph.ainvoke(
            {
                "messages": [
                    ("user", body.message),
                ],
            },
            config=config,
        )
    except Exception:
        logger.exception(
            LogEventEnums.AGENT_EXECUTION_FAILED.value,
            conversation_id=str(conversation.conversation_uuid),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=MessageEnums.AGENT_EXECUTION_FAILED.value,
        )

    logger.info(
        LogEventEnums.CHAT_REQUEST_COMPLETED.value,
        conversation_id=str(conversation.conversation_uuid),
    )

    return ChatResponse(
        conversation_id=conversation.conversation_uuid,
        response=result["messages"][-1].content,
    )
