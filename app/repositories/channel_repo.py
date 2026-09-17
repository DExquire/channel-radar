"""Data-access for channels and channel-level metrics.

Repositories own all SQL. Services depend on repositories, never on the ORM
session directly beyond passing it in — this keeps query logic in one place and
makes the service layer easy to reason about.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, ChannelMetric, ChannelStatus


def normalize_username(raw: str) -> str:
    """@Durov, https://t.me/durov, t.me/s/durov -> 'durov' (lowercased)."""
    u = (raw or "").strip()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    u = u.replace("t.me/s/", "").replace("t.me/", "")
    u = u.lstrip("@").strip("/")
    return u.lower()


def get_by_username(session: Session, username: str) -> Channel | None:
    return session.scalar(select(Channel).where(Channel.username == username))


def get_by_id(session: Session, channel_id: int) -> Channel | None:
    return session.get(Channel, channel_id)


def list_all(session: Session) -> list[Channel]:
    return list(session.scalars(select(Channel).order_by(Channel.created_at.desc())))


def create_pending(session: Session, username: str) -> Channel:
    channel = Channel(username=username, status=ChannelStatus.pending)
    session.add(channel)
    session.flush()  # assign id without ending the transaction
    return channel

def add_metric_snapshot(
    session: Session, channel_id: int, subscribers: int | None, post_count: int
) -> None:
    session.add(
        ChannelMetric(
            channel_id=channel_id, subscribers=subscribers, post_count=post_count
        )
    )


def metric_series(
    session: Session, channel_id: int, since: datetime | None = None
) -> list[ChannelMetric]:
    stmt = select(ChannelMetric).where(ChannelMetric.channel_id == channel_id)
    if since is not None:
        stmt = stmt.where(ChannelMetric.collected_at >= since)
    return list(session.scalars(stmt.order_by(ChannelMetric.collected_at)))


def due_for_collection(session: Session, older_than_minutes: int) -> list[Channel]:
    """Channels whose last collection is older than the window (or never)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    stmt = select(Channel).where(
        (Channel.last_collected_at.is_(None)) | (Channel.last_collected_at < cutoff)
    )
    return list(session.scalars(stmt))
