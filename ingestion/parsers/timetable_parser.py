"""Read human-verified CSV output of PDF timetable extraction."""
import csv
from datetime import datetime, date, time

def read_timetable_csv(path: str) -> list[dict]:
    with open(path, encoding='utf-8-sig', newline='') as fp: rows = list(csv.DictReader(fp))
    required = {'faculty_external_id', 'subject_code', 'subject_name', 'section_code', 'section_label', 'room_code',
                'department_code', 'academic_year', 'semester', 'day_of_week', 'start_time', 'end_time', 'valid_from', 'valid_to', 'source_url'}
    if not rows or not required.issubset(rows[0]): raise ValueError(f'Timetable CSV requires columns: {sorted(required)}')
    for row in rows:
        for field in ('valid_from', 'valid_to'): row[field] = date.fromisoformat(row[field])
        for field in ('start_time', 'end_time'): row[field] = time.fromisoformat(row[field])
        for field in ('semester', 'day_of_week'): row[field] = int(row[field])
        if row['day_of_week'] not in range(7) or row['start_time'] >= row['end_time'] or row['valid_from'] > row['valid_to']:
            raise ValueError(f'Invalid timetable row: {row}')
    return rows
