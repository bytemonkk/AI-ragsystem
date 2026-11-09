from logging.config import fileConfig
from alembic import context
from database.connection import Base
from database import models  # noqa
from database.config import settings
config = context.config
config.set_main_option('sqlalchemy.url', settings().database_url)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    from sqlalchemy import create_engine
    engine = create_engine(settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
    engine.dispose()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
