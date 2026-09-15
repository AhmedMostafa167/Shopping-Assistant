import logging

from fastapi import APIRouter, HTTPException, Request, status

from .schemas.Chat import ChatRequest, ChatResponse


logger = logging.getLogger(__name__)


chat_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
)


@chat_router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    profile = await request.app.profile_model.get_profile_by_username(
        body.username
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
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
            detail="Conversation not found",
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
        logger.exception(f"Agent execution failed for conversation {conversation.conversation_uuid}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent execution failed",
        )

    return ChatResponse(
        conversation_id=conversation.conversation_uuid,
        response=result["messages"][-1].content,
    )
