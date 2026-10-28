"""Database engine. SQLAlchemy Core with explicit, parameterised SQL (NF03)."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": 5,
            "options": "-c search_path=prostoriq,public -c statement_timeout=5000",
            "application_name": "prostoriq-api",
        },
    )
