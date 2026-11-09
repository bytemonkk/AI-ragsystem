"""Temporary testing-only account provisioner, never exposed as a public endpoint.
python -m scripts.create_faculty_user EMAIL FACULTY_EXTERNAL_ID
Password is read from CBIT_USER_PASSWORD environment variable.
"""
import os
import sys
from sqlalchemy import select
from database.connection import SessionLocal
from database.models import User, Faculty
from api.auth.security import hash_password

def main():
    if len(sys.argv) != 3: raise ValueError('Provide email and faculty external ID')
    password = os.environ.get('CBIT_USER_PASSWORD', '')
    if len(password) < 12: raise ValueError('Set CBIT_USER_PASSWORD to a strong password (12+ characters)')
    with SessionLocal.begin() as db:
        faculty = db.scalar(select(Faculty).where(Faculty.external_id == sys.argv[2]))
        if not faculty: raise ValueError('Faculty not found')
        user = db.scalar(select(User).where(User.email == sys.argv[1]))
        if not user: user = User(email=sys.argv[1], password_hash='')
        user.password_hash = hash_password(password)
        user.role = 'faculty'
        user.faculty_id = faculty.id
        user.department_id = faculty.department_id
        db.add(user)
    print('Faculty test account provisioned')
if __name__ == '__main__': main()
