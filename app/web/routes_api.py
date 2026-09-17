"""JSON API: add a channel, and the external cron collection trigger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import channel_service
from app.web.deps import get_db

router = APIRouter(prefix="/api", tags=["api"])
settings = get_settings()


class AddChannelRequest(BaseModel):
    username: str


class AddChannelResponse(BaseModel):
    id: int
    username: str
    status: str
    title: str | None = None
    subscribers: int | None = None
    post_count: int
    error_message: str | None = None


@router.post("/channels", response_model=AddChannelResponse, status_code=status.HTTP_201_CREATED)
def add_channel(payload: AddChannelRequest, db: Session = Depends(get_db)):
    """Add a channel and run the first collection synchronously (seconds).

    Returns 201 with the channel state. If the channel is missing/private the
    row is created with status='error' and the message explains why — the UI
    shows that instead of failing.
    """
    from app.repositories import post_repo

    try:
        channel = channel_service.add_channel(db, payload.username)
    except channel_service.InvalidUsername:
        raise HTTPException(status_code=422, detail="Invalid channel username")
    except channel_service.ChannelExists as exc:
        raise HTTPException(status_code=409, detail=f"Channel @{exc} already added")

    return AddChannelResponse(
        id=channel.id,
        username=channel.username,
        status=channel.status.value,
        title=channel.title,
        subscribers=channel.subscribers,
        post_count=post_repo.count_for_channel(db, channel.id),
        error_message=channel.error_message,
    )


@router.post("/cron/collect")
def cron_collect(
    db: Session = Depends(get_db),
    x_cron_secret: str | None = Header(default=None),
):
    """External-trigger endpoint for background collection.

    A scheduled GitHub Action / cron-job.org hits this on a schedule; it both
    wakes the (sleeping) web service and drives the incremental refresh. Guarded
    by a shared secret when CRON_SECRET is set.
    """
    if settings.cron_secret and x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Bad cron secret")
    result = channel_service.collect_all_due(db, settings.min_recollect_minutes)
    return {"ok": True, **result}


@router.get("/healthz")
def healthz():
    return {"ok": True, "ai_enabled": settings.ai_enabled}


@router.get("/ai-debug")
def ai_debug():
    """TEMPORARY diagnostic — remove after verifying the AI layer."""
    from app.services.ai import get_ai_service

    return get_ai_service().probe()
