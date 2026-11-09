from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from database.config import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    with SessionLocal() as session:
        yield session
