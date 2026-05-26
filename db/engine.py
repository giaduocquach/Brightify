"""
Database engine and session configuration for Brightify.
PostgreSQL 17 + pgvector via SQLAlchemy 2.0 async-compatible.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise EnvironmentError(
        "DATABASE_URL not set. Example: postgresql://user:pass@localhost:5432/brightify_dw"
    )

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency – yields a DB session then closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
