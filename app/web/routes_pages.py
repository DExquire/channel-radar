"""HTML dashboard routes (server-rendered Jinja2)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.repositories import channel_repo
from app.services import channel_service, dashboard
from app.web.deps import get_db

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

_ALLOWED_PERIODS = {1, 7, 30, 90}


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "index.html", {"request": request, "channels": dashboard.overview(db)}
    )


@router.get("/channels/{channel_id}", response_class=HTMLResponse)
def channel_page(
    channel_id: int, request: Request, period: int = 7, db: Session = Depends(get_db)
):
    period = period if period in _ALLOWED_PERIODS else 7
    channel = channel_repo.get_by_id(db, channel_id)
    if channel is None:
        return templates.TemplateResponse(
            "not_found.html", {"request": request, "what": "Channel"}, status_code=404
        )
    detail = dashboard.channel_detail(db, channel, period)
    digest = channel_service.get_or_build_digest(db, channel, period_days=period)
    return templates.TemplateResponse(
        "channel.html",
        {
            "request": request,
            "d": detail,
            "digest": digest,
            "period": period,
            "periods": sorted(_ALLOWED_PERIODS),
        },
    )


@router.get("/posts/{post_id}", response_class=HTMLResponse)
def post_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    detail = dashboard.post_detail(db, post_id)
    if detail is None:
        return templates.TemplateResponse(
            "not_found.html", {"request": request, "what": "Post"}, status_code=404
        )
    return templates.TemplateResponse("post.html", {"request": request, "d": detail})
