import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database.config import settings
from database.connection import engine
from api.routes import auth, faculty, timetable, chat

logging.basicConfig(level=logging.INFO)
app = FastAPI(title='CBIT AI Assistant API', version='2.0.0')
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in settings().cors_origins.split(',')],
                   allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])
app.include_router(auth.router, prefix='/api/v1')
app.include_router(faculty.router, prefix='/api/v1')
app.include_router(timetable.router, prefix='/api/v1')
app.include_router(chat.router, prefix='/api/v1')

@app.get('/health/live')
def live(): return {'status': 'ok'}

@app.get('/health/ready')
def ready():
    from fastapi import HTTPException
    from retrieval.hybrid_retriever import qdrant
    try:
        with engine.connect() as conn: conn.execute(text('SELECT 1'))
        qdrant().get_collections()
        return {'status': 'ready'}
    except Exception:
        raise HTTPException(503, 'Dependency not ready')
