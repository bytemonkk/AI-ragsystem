"""Upsert reviewed faculty and timetable CSVs.
Usage: python -m scripts.import_structured faculty examples/faculty.csv
       python -m scripts.import_structured timetable examples/timetable.csv
"""
import argparse
from sqlalchemy import select
from database.connection import SessionLocal
from database.models import Department, Faculty, Subject, Section, Room, TimetableEntry
from ingestion.parsers.faculty_parser import read_faculty_csv
from ingestion.parsers.timetable_parser import read_timetable_csv

def get_or_create(db, cls, field, value, **defaults):
    record = db.scalar(select(cls).where(getattr(cls, field) == value))
    if not record:
        record = cls(**{field: value, **defaults})
        db.add(record)
        db.flush()
    return record

def import_faculty(path):
    rows = read_faculty_csv(path)
    with SessionLocal.begin() as db:
        for row in rows:
            dep = get_or_create(db, Department, 'code', row['department_code'], name=row['department_name'])
            obj = get_or_create(db, Faculty, 'external_id', row['external_id'], name=row['name'], department_id=dep.id)
            obj.name, obj.designation, obj.department_id = row['name'], row['designation'], dep.id
            obj.is_hod = row['is_hod'].strip().lower() in ('1', 'yes', 'true')
            obj.image_url = row['image_url'] or None
            obj.profile_url = row['profile_url'] or None
    print(f'Upserted {len(rows)} faculty records')

def import_timetable(path):
    rows = read_timetable_csv(path)
    with SessionLocal.begin() as db:
        # This importer replaces matching timetable slots. Review conflicts before importing.
        for row in rows:
            fac = db.scalar(select(Faculty).where(Faculty.external_id == row['faculty_external_id']))
            if fac is None: raise ValueError('Unknown faculty external ID: ' + row['faculty_external_id'])
            dep = db.scalar(select(Department).where(Department.code == row['department_code']))
            if dep is None: raise ValueError('Unknown department: ' + row['department_code'])
            sub = get_or_create(db, Subject, 'code', row['subject_code'], name=row['subject_name'])
            sec = get_or_create(db, Section, 'code', row['section_code'], label=row['section_label'])
            room = get_or_create(db, Room, 'code', row['room_code']) if row['room_code'] else None
            criteria = [TimetableEntry.faculty_id == fac.id, TimetableEntry.day_of_week == row['day_of_week'],
                        TimetableEntry.start_time == row['start_time'], TimetableEntry.academic_year == row['academic_year'],
                        TimetableEntry.semester == row['semester'], TimetableEntry.section_id == sec.id]
            existing = db.scalar(select(TimetableEntry).where(*criteria))
            if existing: entry = existing
            else:
                entry = TimetableEntry(faculty_id=fac.id, day_of_week=row['day_of_week'], start_time=row['start_time'],
                                     academic_year=row['academic_year'], semester=row['semester'], section_id=sec.id)
                db.add(entry)
            entry.subject_id, entry.department_id = sub.id, dep.id
            entry.room_id, entry.end_time = room.id if room else None, row['end_time']
            entry.valid_from, entry.valid_to = row['valid_from'], row['valid_to']
            entry.source_url = row['source_url']
    print(f'Upserted {len(rows)} timetable rows')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('kind', choices=['faculty', 'timetable'])
    p.add_argument('file')
    args = p.parse_args()
    (import_faculty if args.kind == 'faculty' else import_timetable)(args.file)
