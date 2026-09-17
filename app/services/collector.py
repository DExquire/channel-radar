"""Collection service: fetch -> parse -> idempotent upsert.

Split into three functions so the risky bits are testable without network:

* fetch_channel_html  -> the only I/O (httpx). Mocked/skipped in tests.
* ingest              -> pure DB logic. This is where idempotency lives and is
                         unit-tested (ingesting the same page twice must not
                         create duplicate posts, only new metric snapshots).
* collect_channel     -> orchestration used by the API and scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Channel, ChannelStatus
from app.repositories import channel_repo, post_repo
from app.services.parser import (
    ParsedChannel,
    looks_like_missing_channel,
    parse_channel_page,
)

settings = get_settings()


class ChannelNotAvailable(Exception):
    """Channel does not exist, is private, or has no public web preview."""


@dataclass
class IngestResult:
    new_posts: int
    updated_posts: int
    post_ids_new: list[int]


def fetch_channel_html(username: str, client: httpx.Client | None = None) -> str:
    """Fetch the anonymous web-preview HTML for a channel. Raises on HTTP error."""
    url = f"{settings.tme_base_url}/{username}"
    headers = {"User-Agent": settings.user_agent, "Accept-Language": "en,ru;q=0.8,uk;q=0.6"}
    owns_client = client is None
    client = client or httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True)
    try:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text
    finally:
        if owns_client:
            client.close()


def ingest(session: Session, channel: Channel, parsed: ParsedChannel) -> IngestResult:
    """Persist a parsed page idempotently.

    - Channel metadata is refreshed in place.
    - Each post is matched by its natural key (channel_id, tg_msg_id):
      created if new, left as-is if seen before.
    - A metric snapshot is ALWAYS appended for every post on the page and for
      the channel, preserving the dynamics of views/reactions/subscribers.
    """
    # Refresh channel metadata (keep old value if the page omitted it).
    channel.title = parsed.title or channel.title
    channel.description = parsed.description or channel.description
    channel.photo_url = parsed.photo_url or channel.photo_url
    if parsed.subscribers:
        channel.subscribers = parsed.subscribers
    channel.status = ChannelStatus.active
    channel.error_message = None
    channel.last_collected_at = datetime.now(timezone.utc)

    new_ids: list[int] = []
    updated = 0
    for p in parsed.posts:
        post = post_repo.get_by_natural_key(session, channel.id, p.tg_msg_id)
        if post is None:
            from app.models import Post

            post = Post(
                channel_id=channel.id,
                tg_msg_id=p.tg_msg_id,
                text=p.text,
                link=p.link,
                posted_at=p.posted_at,
                has_media=p.has_media,
            )
            session.add(post)
            session.flush()
            new_ids.append(post.id)
        else:
            # Refresh mutable text (edited posts) but keep identity.
            post.text = p.text or post.text
            updated += 1

        post_repo.add_metric_snapshot(session, post.id, p.views, p.forwards, p.reactions)

    post_count = post_repo.count_for_channel(session, channel.id)
    channel_repo.add_metric_snapshot(session, channel.id, channel.subscribers, post_count)

    return IngestResult(new_posts=len(new_ids), updated_posts=updated, post_ids_new=new_ids)


def collect_channel(session: Session, channel: Channel) -> IngestResult:
    """Full collection cycle for one channel. Marks channel status on failure."""
    try:
        html = fetch_channel_html(channel.username)
    except httpx.HTTPStatusError as exc:
        _mark_error(channel, f"HTTP {exc.response.status_code}")
        raise ChannelNotAvailable(channel.username) from exc
    except httpx.HTTPError as exc:
        _mark_error(channel, f"network error: {exc}")
        raise ChannelNotAvailable(channel.username) from exc

    if looks_like_missing_channel(html):
        _mark_error(channel, "channel not found or private")
        raise ChannelNotAvailable(channel.username)

    parsed = parse_channel_page(html, channel.username)
    result = ingest(session, channel, parsed)
    logger.info(
        "collected @{} : +{} new, {} updated", channel.username, result.new_posts, result.updated_posts
    )
    return result


def _mark_error(channel: Channel, message: str) -> None:
    channel.status = ChannelStatus.error
    channel.error_message = message
    logger.warning("collection failed for @{}: {}", channel.username, message)
