from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User
from api.auth.security import optional_user
from retrieval.query_router import answer
router = APIRouter(prefix='/chat', tags=['chat'])
class ChatMessage(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
@router.post('')
def chat(message: ChatMessage, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    return answer(db, message.question, user)
