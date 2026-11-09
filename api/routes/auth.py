from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User
from api.auth.security import check_password, create_token, current_user
router = APIRouter(prefix='/auth', tags=['auth'])

class Login(BaseModel):
    email: EmailStr
    password: str

@router.post('/login')
def login(body: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(body.email)))
    if not user or not check_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, 'Invalid credentials')
    return {'access_token': create_token(user), 'token_type': 'bearer', 'role': user.role}

@router.get('/me')
def me(user: User = Depends(current_user)):
    return {'id': user.id, 'email': user.email, 'role': user.role, 'faculty_id': user.faculty_id, 'department_id': user.department_id}
