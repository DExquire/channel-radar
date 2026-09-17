"""Application service: orchestrates channels, collection and the AI layer.

This is the layer the web routes call. It keeps two concerns explicit:

* Adding a channel must feel instant (seconds): we validate + run ONE collection
  cycle synchronously so the user immediately sees data, then return. Heavy AI
  work (per-post categorization, digests) is deliberately NOT on this path.
* Background cycles (scheduler / cron endpoint) do the ongoing refresh AND the
  AI categorization of new posts, capped per run to stay within free quotas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models import Channel, ChannelDigest, ChannelStatus
from app.repositories import channel_repo, post_repo
from app.services import collector
from app.services.ai import get_ai_service

# Cap AI categorizations per collection run to protect the free quota.
_MAX_CATEGORIZE_PER_RUN = 20
# Rebuild a cached digest at most this often.
_DIGEST_TTL = timedelta(hours=6)


class ChannelExists(Exception):
    pass


class InvalidUsername(Exception):
    pass


def add_channel(session: Session, raw_username: str) -> Channel:
    """Validate, persist, and run the first collection synchronously (fast)."""
    username = channel_repo.normalize_username(raw_username)
    if not username or not _is_valid_username(username):
        raise InvalidUsername(raw_username)

    existing = channel_repo.get_by_username(session, username)
    if existing:
        raise ChannelExists(username)

    channel = channel_repo.create_pending(session, username)
    # First cycle: if the channel is missing/private this raises and the row is
    # left with status=error, which the UI surfaces. We flush so the row exists.
    try:
        collector.collect_channel(session, channel)
    except collector.ChannelNotAvailable:
        logger.info("first collection failed for @{} (kept as error row)", username)
    return channel


def collect_all_due(session: Session, min_recollect_minutes: int) -> dict:
    """Refresh every channel due for collection, then categorize new posts."""
    due = channel_repo.due_for_collection(session, min_recollect_minutes)
    collected, failed = 0, 0
    for channel in due:
        try:
            collector.collect_channel(session, channel)
            collected += 1
        except collector.ChannelNotAvailable:
            failed += 1
    categorized = _categorize_missing(session)
    return {"due": len(due), "collected": collected, "failed": failed, "categorized": categorized}


def _categorize_missing(session: Session) -> int:
    """Assign AI categories to posts that don't have one yet (quota-capped)."""
    ai = get_ai_service()
    from sqlalchemy import select

    from app.models import Post

    posts = list(
        session.scalars(
            select(Post).where(Post.category.is_(None)).limit(_MAX_CATEGORIZE_PER_RUN)
        )
    )
    for post in posts:
        post.category = ai.categorize(post.text or "")
    return len(posts)


def get_or_build_digest(session: Session, channel: Channel, period_days: int = 7) -> str | None:
    """Return a cached digest, rebuilding when missing or stale. None if AI off."""
    period = f"{period_days}d"
    cached = session.scalar(
        _digest_stmt(channel.id, period)
    )
    now = datetime.now(timezone.utc)
    if cached and cached.created_at and _aware(cached.created_at) > now - _DIGEST_TTL:
        return cached.summary

    ai = get_ai_service()
    if not ai.enabled:
        return cached.summary if cached else None

    since = now - timedelta(days=period_days)
    posts = post_repo.list_for_channel(session, channel.id, since=since, limit=40)
    summary = ai.digest(channel.title or channel.username, [p.text or "" for p in posts], period)
    if not summary:
        return cached.summary if cached else None

    if cached:
        cached.summary = summary
        cached.model = ai._model
    else:
        session.add(
            ChannelDigest(
                channel_id=channel.id, period=period, summary=summary, model=ai._model
            )
        )
    return summary


def _digest_stmt(channel_id: int, period: str):
    from sqlalchemy import select

    return (
        select(ChannelDigest)
        .where(ChannelDigest.channel_id == channel_id, ChannelDigest.period == period)
        .limit(1)
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_valid_username(username: str) -> bool:
    # Telegram usernames: 5-32 chars, letters/digits/underscore. Be lenient on length.
    import re

    return bool(re.fullmatch(r"[a-z0-9_]{3,32}", username))
