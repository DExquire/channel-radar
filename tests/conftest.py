"""Shared test fixtures. Tests never touch the network or a real LLM."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Force an isolated in-memory-ish SQLite DB and no AI key before app imports.
os.environ["DATABASE_URL"] = "sqlite:///./test_channel_radar.db"
os.environ["GEMINI_API_KEY"] = ""

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_html() -> str:
    return (FIXTURES / "channel_sample.html").read_text(encoding="utf-8")


@pytest.fixture
def missing_html() -> str:
    return (FIXTURES / "missing_channel.html").read_text(encoding="utf-8")


@pytest.fixture
def db_session():
    """A fresh, isolated SQLite session with tables created and dropped per test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
