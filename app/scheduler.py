"""Optional in-process scheduler (APScheduler).

Enabled only when RUN_SCHEDULER=1 (e.g. on always-on hosts like Fly.io). On
sleeping free hosts (Render) it is left OFF and collection is driven by the
external cron endpoint instead — see docs/adr/0001-hosting.md.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from app.config import get_settings
from app.db import SessionLocal
from app.services import channel_service

settings = get_settings()
_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    session = SessionLocal()
    try:
        result = channel_service.collect_all_due(session, settings.min_recollect_minutes)
        session.commit()
        logger.info("scheduled collection: {}", result)
    except Exception as exc:  # never let a bad run kill the scheduler thread
        session.rollback()
        logger.exception("scheduled collection failed: {}", exc)
    finally:
        session.close()


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_job, "interval", minutes=settings.collect_interval_minutes, id="collect")
    _scheduler.start()
    logger.info("scheduler started ({} min interval)", settings.collect_interval_minutes)


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
