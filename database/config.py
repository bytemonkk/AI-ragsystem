from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://cbit:cbit_local_only@localhost:5432/cbit'
    qdrant_url: str = 'http://localhost:6333'
    qdrant_collection: str = 'cbit_documents_v2'
    embed_model: str = 'BAAI/bge-m3'
    embed_dim: int = 1024
    jwt_secret: str = ''
    jwt_algorithm: str = 'HS256'
    cors_origins: str = 'http://localhost:8080'
    allowed_crawl_hosts: str = 'www.cbit.ac.in,cbit.ac.in'
    llm_base_url: str = ''
    llm_api_key: str = ''
    llm_model: str = ''
    admin_bootstrap_email: str = ''
    admin_bootstrap_password: str = ''

@lru_cache
def settings() -> Settings:
    return Settings()
