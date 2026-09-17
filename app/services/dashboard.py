"""Read-side view assembly for the dashboard.

Turns ORM rows into plain dicts the templates render. Keeping this here means
templates stay dumb and routes stay thin, and the (testable) analytics helpers
are applied in one place.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Channel
from app.repositories import channel_repo, post_repo
from app.services import analytics

_HEALTH_STALE_DAYS = 3.0


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def channel_health(channel: Channel, last_post_at: datetime | None) -> str:
    """Traffic-light health for a source."""
    if channel.status.value == "error":
        return "down"
    if channel.status.value == "pending":
        return "pending"
    days = analytics.days_since(_aware(last_post_at), datetime.now(timezone.utc))
    if days is not None and days > _HEALTH_STALE_DAYS:
        return "stale"
    return "ok"


def overview(session: Session) -> list[dict]:
    rows = []
    for ch in channel_repo.list_all(session):
        posts = post_repo.list_for_channel(session, ch.id, limit=1)
        last_post_at = posts[0].posted_at if posts else None
        rows.append(
            {
                "id": ch.id,
                "username": ch.username,
                "title": ch.title or ch.username,
                "subscribers": ch.subscribers,
                "post_count": post_repo.count_for_channel(session, ch.id),
                "last_collected_at": _aware(ch.last_collected_at),
                "status": ch.status.value,
                "error_message": ch.error_message,
                "health": channel_health(ch, last_post_at),
            }
        )
    return rows


def channel_detail(session: Session, channel: Channel, period_days: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    posts = post_repo.list_for_channel(session, channel.id, since=since, limit=300)

    # Baseline of latest views per post for anomaly detection.
    view_values: list[int] = []
    post_rows = []
    for p in posts:
        latest = post_repo.latest_metric(session, p.id)
        views = latest.views if latest else 0
        reactions = latest.reactions if latest else 0
        view_values.append(views)
        post_rows.append(
            {
                "id": p.id,
                "tg_msg_id": p.tg_msg_id,
                "text": p.text or "",
                "preview": (p.text or "").strip().replace("\n", " ")[:160],
                "link": p.link,
                "posted_at": _aware(p.posted_at),
                "views": views,
                "reactions": reactions,
                "category": p.category,
                "has_media": p.has_media,
            }
        )

    # Anomaly flags computed against the period baseline.
    for row in post_rows:
        a = analytics.detect_anomaly(row["views"], view_values)
        row["is_anomaly"] = a.is_anomaly
        row["z_score"] = a.z_score

    # Subscriber trend series for the chart.
    series = channel_repo.metric_series(session, channel.id, since=since)
    trend = [
        {"t": _aware(m.collected_at).isoformat(), "subscribers": m.subscribers, "posts": m.post_count}
        for m in series
    ]

    return {
        "channel": {
            "id": channel.id,
            "username": channel.username,
            "title": channel.title or channel.username,
            "description": channel.description,
            "subscribers": channel.subscribers,
            "status": channel.status.value,
            "error_message": channel.error_message,
            "last_collected_at": _aware(channel.last_collected_at),
        },
        "posts": post_rows,
        "trend": trend,
        "avg_views": analytics.average_views(view_values),
        "period_days": period_days,
    }


def post_detail(session: Session, post_id: int) -> dict | None:
    post = post_repo.get_by_id(session, post_id)
    if post is None:
        return None
    metrics = post_repo.metric_series(session, post.id)
    channel = channel_repo.get_by_id(session, post.channel_id)
    return {
        "post": {
            "id": post.id,
            "tg_msg_id": post.tg_msg_id,
            "text": post.text or "",
            "link": post.link,
            "posted_at": _aware(post.posted_at),
            "category": post.category,
            "has_media": post.has_media,
        },
        "channel": {"id": channel.id, "username": channel.username, "title": channel.title or channel.username},
        "metric_history": [
            {
                "t": _aware(m.collected_at).isoformat(),
                "views": m.views,
                "reactions": m.reactions,
                "forwards": m.forwards,
            }
            for m in metrics
        ],
    }
