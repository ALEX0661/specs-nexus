from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.chat_nlp import get_chat_response
import traceback

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest):
    try:
        user_message = chat_request.message.strip()
        response_text = get_chat_response(user_message)
        return ChatResponse(response=response_text)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
