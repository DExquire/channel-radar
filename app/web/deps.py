"""FastAPI dependencies."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from app.db import SessionLocal


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
