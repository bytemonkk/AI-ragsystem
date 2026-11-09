from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import Faculty
from services.faculty_service import find_faculty, faculty_dict
router = APIRouter(prefix='/faculty', tags=['faculty'])

@router.get('/search')
def find(q: str = Query(default='', max_length=150), department: str | None = None, db: Session = Depends(get_db)):
    return [faculty_dict(f) for f in find_faculty(db, q, department=department)]

@router.get('/{faculty_id}')
def detail(faculty_id: int, db: Session = Depends(get_db)):
    f = db.get(Faculty, faculty_id)
    if not f or not f.is_active: raise HTTPException(404, 'Faculty not found')
    return faculty_dict(f)
