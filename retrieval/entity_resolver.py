
"""Rule-based query intent classification for CBIT RAG.

Routes:
- personal_timetable: authenticated user's classes
- faculty: faculty profiles, HoDs and photographs
- documents: circulars, exams, meetings, policies and
  general institutional questions
"""

import re


def classify(question: str) -> str:
    q = question.lower().strip()

    # 1. Personal timetable queries have highest priority.
    personal = re.search(
        r"\b(my|i|me)\b", q
    )

    timetable = re.search(
        r"\b(class|classes|period|periods|"
        r"timetable|time table|room)\b", q
    )

    if personal and timetable and not re.search(
        r"\b(meeting|parent.teacher|circular|"
        r"notification|exam|examination)\b", q
    ):
        return "personal_timetable"

    # 2. Questions about institutional documents.
    document_terms = (
        r"\b(meeting|circular|notification|notice|"
        r"exam|examination|academic calendar|"
        r"fee|fees|attendance|regulation|"
        r"policy|syllabus|admission|"
        r"scholarship|remedial|"
        r"parent.teacher)\b"
    )

    if re.search(document_terms, q):
        return "documents"

    # 3. Explicit faculty identity and profile queries.
    faculty_terms = (
        r"\b(hod|head of department|"
        r"faculty|professor|teacher|"
        r"lecturer|photo|picture|image)\b"
    )

    if re.search(faculty_terms, q):
        return "faculty"

    # 4. General questions use hybrid document retrieval.
    return "documents"


def extract_department(question: str) -> str | None:
    match = re.search(
        r"\b(cse|it|ece|eee|mech|civil|"
        r"aiml|aids|mba|mca)\b",
        question,
        re.IGNORECASE,
    )

    return match.group(1).upper() if match else None
