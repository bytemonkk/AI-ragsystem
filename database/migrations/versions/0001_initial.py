"""Initial structured schema.

Revision ID: 0001
Revises:
"""
from alembic import op
from database.connection import Base
from database import models  # noqa: F401
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute("CREATE INDEX IF NOT EXISTS ix_chunk_search ON document_chunks USING GIN (to_tsvector('english', text))")

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
