from datetime import datetime, date
from zoneinfo import ZoneInfo
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, joinedload
from database.models import TimetableEntry, ScheduleException

LOCAL_TZ = ZoneInfo('Asia/Kolkata')

def entry_dict(e: TimetableEntry) -> dict:
    return {'id': e.id, 'faculty': e.faculty.name, 'subject': e.subject.name,
            'subject_code': e.subject.code, 'branch': e.department.code,
            'section': e.section.label, 'room': e.room.code if e.room else None,
            'start_time': e.start_time.isoformat(timespec='minutes'),
            'end_time': e.end_time.isoformat(timespec='minutes'), 'academic_year': e.academic_year,
            'semester': e.semester, 'source_url': e.source_url,
            'status': 'scheduled'}

def schedule(db: Session, faculty_id: int, at: datetime | None = None, current_only: bool = False) -> dict:
    now = at.astimezone(LOCAL_TZ) if at else datetime.now(LOCAL_TZ)
    day, clock = now.date(), now.time().replace(tzinfo=None)
    stmt = (select(TimetableEntry).options(joinedload(TimetableEntry.faculty), joinedload(TimetableEntry.subject),
             joinedload(TimetableEntry.department), joinedload(TimetableEntry.room), joinedload(TimetableEntry.section))
            .where(TimetableEntry.faculty_id == faculty_id, TimetableEntry.day_of_week == now.weekday(),
                   TimetableEntry.valid_from <= day, TimetableEntry.valid_to >= day,
                   TimetableEntry.is_active.is_(True)))
    if current_only: stmt = stmt.where(TimetableEntry.start_time <= clock, TimetableEntry.end_time > clock)
    entries = list(db.scalars(stmt.order_by(TimetableEntry.start_time)).all())
    exceptions = list(db.scalars(select(ScheduleException).where(ScheduleException.date == day,
        or_(ScheduleException.faculty_id == faculty_id, ScheduleException.faculty_id.is_(None)))).all())
    filtered = []
    for entry in entries:
        relevant = [e for e in exceptions if e.entry_id is None or e.entry_id == entry.id]
        if relevant:
            for e in relevant:
                if e.kind in ('holiday', 'cancelled'):
                    # Global holidays are suppressed, cancelled periods reported explicitly.
                    if e.kind == 'holiday': break
                    record = entry_dict(entry)
                    record['status'] = 'cancelled'
                    record['note'] = e.note
                    filtered.append(record)
            continue
        filtered.append(entry_dict(entry))
    return {'date': day.isoformat(), 'time': now.strftime('%H:%M'), 'timezone': 'Asia/Kolkata',
            'entries': filtered, 'note': 'Published schedule; unrecorded substitutions or cancellations may apply.'}
