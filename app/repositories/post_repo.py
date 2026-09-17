"""Data-access for posts and post-level metric snapshots."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Post, PostMetric


def get_by_natural_key(session: Session, channel_id: int, tg_msg_id: int) -> Post | None:
    return session.scalar(
        select(Post).where(Post.channel_id == channel_id, Post.tg_msg_id == tg_msg_id)
    )


def get_by_id(session: Session, post_id: int) -> Post | None:
    return session.get(Post, post_id)


def count_for_channel(session: Session, channel_id: int) -> int:
    return session.scalar(
        select(func.count(Post.id)).where(Post.channel_id == channel_id)
    ) or 0


def list_for_channel(
    session: Session,
    channel_id: int,
    since: datetime | None = None,
    limit: int = 200,
) -> list[Post]:
    stmt = select(Post).where(Post.channel_id == channel_id)
    if since is not None:
        stmt = stmt.where(Post.posted_at >= since)
    stmt = stmt.order_by(Post.posted_at.desc().nullslast()).limit(limit)
    return list(session.scalars(stmt))


def add_metric_snapshot(
    session: Session, post_id: int, views: int, forwards: int, reactions: int
) -> None:
    session.add(
        PostMetric(
            post_id=post_id, views=views, forwards=forwards, reactions=reactions
        )
    )


def latest_metric(session: Session, post_id: int) -> PostMetric | None:
    return session.scalar(
        select(PostMetric)
        .where(PostMetric.post_id == post_id)
        .order_by(PostMetric.collected_at.desc())
        .limit(1)
    )


def metric_series(session: Session, post_id: int) -> list[PostMetric]:
    return list(
        session.scalars(
            select(PostMetric)
            .where(PostMetric.post_id == post_id)
            .order_by(PostMetric.collected_at)
        )
    )
