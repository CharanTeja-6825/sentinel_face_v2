"""Test fixtures.

Tests run against a SEPARATE database (`sentinelface_test`), migrated with the
real Alembic chain so the migration path is exercised rather than duplicated.
Dev data in `sentinelface` is never touched. See DECISIONS.md D8.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_DB = "sentinelface_test"

# Must be set before app.config is imported anywhere.
_base = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://sentinel:sentinel@db:5432/sentinelface"
)
os.environ["DATABASE_URL"] = _base.rsplit("/", 1)[0] + "/" + TEST_DB

ASSETS = Path(__file__).parent / "assets"


def _ensure_test_database() -> None:
    import psycopg

    admin = _base.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    from alembic import command
    from alembic.config import Config

    _ensure_test_database()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def db(migrated_db):
    """A clean database per test."""
    from sqlalchemy import text

    from app.database import SessionLocal, engine

    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE observations, tracks, unmatched_faces, "
                "attendance_decisions, attendance_sessions, timetable_blocks, "
                "face_templates, enrolment_sessions, section_students, "
                "sections, students RESTART IDENTITY CASCADE"
            )
        )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """FastAPI test client sharing the clean test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def engine_loaded():
    """The real InsightFace model. Slow, so session-scoped."""
    from app.services.face_engine import load_engine

    return load_engine()


def require_asset(name: str) -> Path:
    """Skip a test when the operator has not supplied real footage yet.

    §13 asks for a committed short clip and enrolment images. Until those exist
    the affected tests SKIP with a clear reason — they never pass vacuously,
    and they never fabricate an accuracy number (§15).
    """
    path = ASSETS / name
    if not path.exists():
        pytest.skip(
            f"Missing test asset {path}. Drop real footage there to enable this "
            "test — see backend/tests/assets/README.md"
        )
    return path
