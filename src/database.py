"""
SQLAlchemy engine, session factory, and declarative Base.

Reads DATABASE_URL from settings, creates:
- `engine`         — SQLAlchemy sync engine
- `SessionLocal`   — scoped session factory
- `Base`           — declarative base class for all models
- `get_db()`       — FastAPI dependency that yields a session per request

All model files in src/models/ inherit from `Base` defined here.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from src.config.settings import settings

# ── 1. Engine ─────────────────────────────────────────
# One connection pool to PostgreSQL. Created once at startup.
# Think of it as the highway — built once, every car (session) uses it.
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,  # prints SQL queries when True
)

# ── 2. Session Factory ────────────────────────────────
# Creates sessions. Two important settings:
#   autocommit=False → YOU control when to commit (transaction safety)
#   autoflush=False  → SQLAlchemy doesn't send queries until you ask
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ── 3. Base ───────────────────────────────────────────
# Every model inherits from this. When Alembic runs, it asks Base:
# "who are your children?" and generates CREATE TABLE for each one.
Base = declarative_base()


# ── 4. get_db() — FastAPI dependency ──────────────────
# Uses yield (Concept 1):
#   - Creates a session BEFORE the request runs
#   - Gives it to the route/controller (yield = pause)
#   - Closes it AFTER the request finishes (finally = always runs)
#
# IMPORTANT: This does NOT commit. Controllers decide when to commit.
# This is how one request can insert an RFQ + 5 stages in one transaction.
def get_db():
    session = SessionLocal()
    try:
        yield session       # pause — request uses this session
    finally:
        session.close()     # always runs, even if request crashed