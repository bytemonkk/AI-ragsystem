from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, ForeignKey, Date, Time, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base

def now_utc():
    return datetime.now(timezone.utc)

class Department(Base):
    __tablename__ = 'departments'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))

class Faculty(Base):
    __tablename__ = 'faculty'
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    designation: Mapped[str] = mapped_column(String(150), default='')
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'))
    profile_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    is_hod: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    department: Mapped[Department] = relationship()

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(250), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default='student')
    faculty_id: Mapped[int | None] = mapped_column(ForeignKey('faculty.id'))
    department_id: Mapped[int | None] = mapped_column(ForeignKey('departments.id'))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Subject(Base):
    __tablename__ = 'subjects'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(220))

class Section(Base):
    __tablename__ = 'sections'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    label: Mapped[str] = mapped_column(String(150))

class Room(Base):
    __tablename__ = 'rooms'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)

class TimetableEntry(Base):
    __tablename__ = 'timetable_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey('faculty.id'), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id'))
    section_id: Mapped[int] = mapped_column(ForeignKey('sections.id'))
    room_id: Mapped[int | None] = mapped_column(ForeignKey('rooms.id'))
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'))
    academic_year: Mapped[str] = mapped_column(String(20))
    semester: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)  # Monday=0
    start_time: Mapped[object] = mapped_column(Time)
    end_time: Mapped[object] = mapped_column(Time)
    valid_from: Mapped[object] = mapped_column(Date)
    valid_to: Mapped[object] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    faculty: Mapped[Faculty] = relationship()
    subject: Mapped[Subject] = relationship()
    section: Mapped[Section] = relationship()
    room: Mapped[Room | None] = relationship()
    department: Mapped[Department] = relationship()
    __table_args__ = (Index('ix_timetable_faculty_day_valid', 'faculty_id', 'day_of_week', 'valid_from', 'valid_to'),)

class ScheduleException(Base):
    __tablename__ = 'schedule_exceptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int | None] = mapped_column(ForeignKey('faculty.id'))
    entry_id: Mapped[int | None] = mapped_column(ForeignKey('timetable_entries.id'))
    date: Mapped[object] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(30))  # holiday, cancelled
    note: Mapped[str] = mapped_column(Text, default='')

class SourceDocument(Base):
    __tablename__ = 'source_documents'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of canonical URL
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(70), default='general')
    access_level: Mapped[str] = mapped_column(String(20), default='public')
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default='pending')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('source_documents.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index('ix_chunks_document_position', 'document_id', 'chunk_index'),)
