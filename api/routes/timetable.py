from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User
from api.auth.security import current_user
from services.timetable_service import schedule
router = APIRouter(prefix='/timetable', tags=['timetable'])

@router.get('/me')
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.faculty_id: raise HTTPException(403, 'Faculty account required')
    return schedule(db, user.faculty_id)

@router.get('/me/current-class')
def current(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.faculty_id: raise HTTPException(403, 'Faculty account required')
    return schedule(db, user.faculty_id, current_only=True)
