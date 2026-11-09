import re
from sqlalchemy.orm import Session
from database.models import User, Faculty
from retrieval.entity_resolver import classify, extract_department
from services.faculty_service import find_faculty, faculty_dict
from services.timetable_service import schedule
from retrieval.hybrid_retriever import search
from generator.generator import generate_answer

def answer(db: Session, question: str, user: User | None = None) -> dict:
    intent = classify(question)
    if intent == 'personal_timetable':
        if user is None: return {'intent': intent, 'answer': 'Please log in to view your personal timetable.', 'data': None, 'sources': []}
        if user.faculty_id is None: return {'intent': intent, 'answer': 'No faculty record is linked to your account.', 'data': None, 'sources': []}
        info = schedule(db, user.faculty_id, current_only=bool(re.search(r'\b(now|current|right now)\b', question, re.I)))
        return {'intent': intent, 'answer': 'Here is your published schedule. Check the status and source for changes.' if info['entries'] else 'No scheduled period was found for that time.', 'data': info,
                'sources': list({e['source_url'] for e in info['entries']})}
    if intent == 'faculty':
        dep = extract_department(question)
        if not dep and user and user.department_id:
            from database.models import Department
            d = db.get(Department, user.department_id)
            dep = d.code if d else None
        hod = bool(re.search(r'\b(hod|head of department)\b', question, re.I))
        if hod and not dep: return {'intent': intent, 'answer': 'Which department’s HoD do you mean?', 'data': [], 'sources': []}
        q = re.sub(r'(?i)\b(show|me|the|faculty|photo|picture|image|of|who|is|our|my|hod|head|department|professor|dr|cse|it|ece|eee|aiml|aids)\b', ' ', question).strip(' ?.,')
        people = find_faculty(db, '' if hod else q, department=dep, hod_only=hod)
        items = [faculty_dict(p) for p in people]
        return {'intent': intent, 'answer': 'Matching faculty records:' if items else 'No verified faculty record found. Please specify a name or department.',
                'data': items, 'sources': [p.profile_url for p in people if p.profile_url]}
    department = extract_department(question)
    documents = search(db, question, department=department)
    return {'intent': intent, 'answer': generate_answer(question, documents), 'data': None,
            'sources': list(dict.fromkeys(d['source_url'] for d in documents)), 'evidence': documents}
