"""
Database engine and session configuration for Brightify.
PostgreSQL 17 + pgvector via SQLAlchemy 2.0.

Provides both sync and async engines:
  - Sync  (psycopg2-binary)  — used by db/seed.py, alembic, health probe fallback
  - Async (asyncpg)          — used by FastAPI endpoint dependencies

The async engine is built lazily; if asyncpg is not installed it falls back
gracefully so the app can still start (with a logged warning).
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise EnvironmentError(
        "DATABASE_URL not set. Example: postgresql://user:pass@localhost:5432/brightify_dw"
    )

# ── Sync engine (psycopg2) — kept for seed.py / alembic / health fallback ──
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Sync FastAPI dependency — yields a DB session then closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Async engine (asyncpg) ─────────────────────────────────────────────────

def _async_url(sync_url: str) -> str:
    """Convert postgresql://... → postgresql+asyncpg://..."""
    for prefix in ("postgresql+psycopg2://", "postgresql://"):
        if sync_url.startswith(prefix):
            return "postgresql+asyncpg://" + sync_url[len(prefix):]
    return sync_url  # already correct or unknown scheme


async_engine = None
AsyncSessionLocal = None

try:
    import asyncpg  # noqa: F401 — presence check only
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    async_engine = create_async_engine(
        _async_url(DATABASE_URL),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
    )
    AsyncSessionLocal = _sm(
        bind=async_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )
except ImportError:
    import logging as _log
    _log.getLogger(__name__).warning(
        "asyncpg not installed — async DB sessions unavailable. "
        "Install with:  pip install asyncpg"
    )


async def get_async_db() -> AsyncGenerator:
    """Async FastAPI dependency — yields an AsyncSession then closes it."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Async DB unavailable — asyncpg is not installed. "
            "Run: pip install asyncpg"
        )
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_async_db() -> bool:
    """Ping the async DB. Returns True on success, False on any error."""
    if async_engine is None:
        return False
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
