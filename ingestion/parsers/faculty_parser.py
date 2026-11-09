"""Read reviewed faculty records; avoid guessing from arbitrary HTML tables."""
import csv

def read_faculty_csv(path: str) -> list[dict]:
    with open(path, encoding='utf-8-sig', newline='') as fp:
        rows = list(csv.DictReader(fp))
    needed = {'external_id', 'name', 'department_code', 'department_name', 'designation', 'is_hod', 'image_url', 'profile_url'}
    if not rows or not needed.issubset(rows[0]): raise ValueError(f'Faculty CSV requires columns: {sorted(needed)}')
    return rows
