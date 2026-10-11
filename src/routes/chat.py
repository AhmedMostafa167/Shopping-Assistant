from fastapi import APIRouter, Depends, HTTPException, Request, status
from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

from helpers.config import Settings, get_settings
from helpers.logging import get_logger
from models.enums import LogEventEnums, MessageEnums
from .schemas.Chat import ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse


logger = get_logger(__name__)


chat_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
)


async def get_conversation_for_user(request: Request, username: str, conversation_id):
    """Return (profile, conversation), or raise 404 if either is missing or not linked."""
    profile = await request.app.profile_model.get_profile_by_username(username)

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MessageEnums.USER_PROFILE_NOT_FOUND.value,
        )

    conversation = (
        await request.app.conversation_model.get_by_uuid_for_profile(
            conversation_uuid=conversation_id,
            profile_id=profile.profile_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MessageEnums.CONVERSATION_NOT_FOUND.value,
        )

    return profile, conversation


@chat_router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    logger.info(
        LogEventEnums.CHAT_REQUEST_STARTED.value,
        conversation_id=str(body.conversation_id),
        username=body.username,
    )
    profile, conversation = await get_conversation_for_user(
        request, body.username, body.conversation_id
    )

    langfuse = get_client()

    # One trace per chat turn, grouped into one session per conversation.
    with (
        propagate_attributes(
            session_id=str(conversation.conversation_uuid),
            user_id=profile.username,
            tags=["chat"],
        ),
        langfuse.start_as_current_observation(
            as_type="span",
            name="chat-turn",
            input=body.message,
        ) as chat_turn,
    ):
        langfuse_handler = CallbackHandler()
        # LangChain runs sync handlers of an async graph in a worker thread, so the
        # handler's "current observation" never reaches the tool's own code. Inline,
        # spans opened inside a tool (the retrieval steps) nest under that tool.
        langfuse_handler.run_inline = True

        config = {
            "configurable": {
                "thread_id": conversation.thread_id,
                "user_id": profile.username,
            },
            "callbacks": [langfuse_handler],
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

        response = result["messages"][-1].content
        chat_turn.update(output=response)
        trace_id = langfuse.get_current_trace_id()

    logger.info(
        LogEventEnums.CHAT_REQUEST_COMPLETED.value,
        conversation_id=str(conversation.conversation_uuid),
    )

    return ChatResponse(
        conversation_id=conversation.conversation_uuid,
        response=response,
        trace_id=trace_id,
    )


@chat_router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def chat_feedback(
    request: Request,
    body: FeedbackRequest,
    app_settings: Settings = Depends(get_settings),
):
    # Langfuse is the only place feedback is stored, so refuse it when tracing is off
    # instead of accepting a rating that would be dropped.
    if not app_settings.LANGFUSE_TRACING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MessageEnums.FEEDBACK_UNAVAILABLE.value,
        )

    _, conversation = await get_conversation_for_user(
        request, body.username, body.conversation_id
    )

    get_client().create_score(
        trace_id=body.trace_id,
        # One rating per reply: sending again updates it instead of adding a second.
        score_id=f"response_rating-{body.trace_id}",
        name="response_rating",
        value=1 if body.helpful else 0,
        data_type="BOOLEAN",
        comment=body.comment,
    )

    logger.info(
        LogEventEnums.CHAT_FEEDBACK_RECORDED.value,
        conversation_id=str(conversation.conversation_uuid),
        trace_id=body.trace_id,
        helpful=body.helpful,
    )

    return FeedbackResponse(
        message=MessageEnums.FEEDBACK_RECORDED.value,
        trace_id=body.trace_id,
    )

