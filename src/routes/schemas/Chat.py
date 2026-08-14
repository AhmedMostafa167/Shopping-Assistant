from pydantic import BaseModel


class ChatRequest(BaseModel):
    username: str
    thread_id: str
    message: str
 
 
class ChatResponse(BaseModel):
    response: str