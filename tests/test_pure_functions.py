from ingestion.sync import chunks_of
from retrieval.entity_resolver import classify, extract_department
from ingestion.parsers.timetable_parser import read_timetable_csv
from api.auth.security import hash_password, check_password

def test_query_router():
    assert classify('What period do I have now?') == 'personal_timetable'
    assert classify('Show me CSE HOD photo') == 'faculty'
    assert classify('What are the attendance regulations?') == 'documents'
    assert extract_department('Who is the ECE HOD?') == 'ECE'

def test_chunks():
    assert chunks_of('') == []
    result = chunks_of('word ' * 1000)
    assert len(result) > 1
    assert all(len(s) <= 1100 for s in result)

def test_csv():
    rows = read_timetable_csv('examples/timetable.csv')
    assert rows[0]['day_of_week'] == 0
    assert rows[0]['start_time'].hour == 9

def test_password_hash():
    secret = hash_password('a strong test password')
    assert check_password('a strong test password', secret)
    assert not check_password('wrong password', secret)
