from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from .schemas.Chat import ChatRequest, ChatResponse


chat_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["api_v1"],
)


@chat_router.post("/", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    config = {
        "configurable": {
            "thread_id": body.thread_id,
            "user_id": body.username,
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
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "message": f"Agent execution failed: {exc}",
            },
        )

    return ChatResponse(
        response=result["messages"][-1].content
    )
