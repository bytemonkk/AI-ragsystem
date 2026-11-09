from sqlalchemy import select, func
from sqlalchemy.orm import Session
from database.models import Faculty, Department

def faculty_dict(f: Faculty) -> dict:
    return {'id': f.id, 'external_id': f.external_id, 'name': f.name, 'designation': f.designation, 'department': f.department.code, 'is_hod': f.is_hod, 'image_url': f.image_url, 'profile_url': f.profile_url}

def find_faculty(db: Session, query: str, department: str | None = None, hod_only: bool = False, limit: int = 10) -> list[Faculty]:
    stmt = select(Faculty).join(Department).where(Faculty.is_active.is_(True))
    if department: stmt = stmt.where(func.lower(Department.code) == department.lower())
    if hod_only: stmt = stmt.where(Faculty.is_hod.is_(True))
    if query: stmt = stmt.where(Faculty.name.ilike('%' + query.replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
    return list(db.scalars(stmt.order_by(Faculty.name).limit(limit)).all())
