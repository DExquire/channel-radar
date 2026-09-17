"""Pure parser for the anonymous Telegram web preview (t.me/s/<channel>).

This module is intentionally free of I/O: it turns raw HTML into normalized
dataclasses. That makes it fully unit-testable on saved fixtures with no network
(see tests/test_parser.py) — the parsing rules are the riskiest part of the
project, so they are isolated here.

We use the anonymous web preview (no Bot API, no API_ID/API_HASH) exactly as the
task requires. The preview exposes: channel title/description/subscribers/photo,
and per post: message id, text, publish time, view count, and — when present —
reactions and forwards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

_COUNT_RE = re.compile(r"([\d.,]+)\s*([KMkmКМ]?)")
_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "к": 1_000, "м": 1_000_000}


def parse_count(raw: str | None) -> int:
    """'1.2K' -> 1200, '3.4M' -> 3400000, '1 234' -> 1234, '' -> 0."""
    if not raw:
        return 0
    # Telegram uses spaces (incl. non-breaking) as thousand separators: drop them
    # so "3 200" -> 3200, while "1.2K" keeps its suffix.
    raw = raw.replace("\xa0", "").replace(" ", "").strip()
    m = _COUNT_RE.search(raw)
    if not m:
        return 0
    number, suffix = m.group(1), m.group(2).lower()
    number = number.replace(",", "").replace(" ", "")
    try:
        value = float(number)
    except ValueError:
        return 0
    return int(value * _MULTIPLIERS.get(suffix, 1))


@dataclass
class ParsedPost:
    tg_msg_id: int
    text: str
    link: str
    posted_at: datetime | None
    views: int = 0
    forwards: int = 0
    reactions: int = 0
    has_media: bool = False


@dataclass
class ParsedChannel:
    username: str
    title: str | None = None
    description: str | None = None
    subscribers: int = 0
    photo_url: str | None = None
    posts: list[ParsedPost] = field(default_factory=list)


def _text_or_none(node) -> str | None:
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def _parse_subscribers(soup: BeautifulSoup) -> int:
    """The header shows several counters; pick the 'subscribers' one."""
    for counter in soup.select(".tgme_channel_info_counter"):
        kind = _text_or_none(counter.select_one(".counter_type")) or ""
        if "subscriber" in kind.lower() or "подписчик" in kind.lower():
            return parse_count(_text_or_none(counter.select_one(".counter_value")))
    # Fallback: first counter value on the page.
    first = soup.select_one(".tgme_channel_info_counter .counter_value")
    return parse_count(_text_or_none(first))


def _msg_id_from_data_post(data_post: str) -> int | None:
    # data-post="durov/123" -> 123
    if not data_post or "/" not in data_post:
        return None
    tail = data_post.rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _parse_datetime(wrap) -> datetime | None:
    time_node = wrap.select_one("time[datetime]")
    if not time_node:
        return None
    raw = time_node.get("datetime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_reactions(wrap) -> int:
    total = 0
    for reaction in wrap.select(".tgme_widget_message_reaction"):
        # reaction node text is like "👍 42"
        total += parse_count(reaction.get_text(" ", strip=True))
    return total


def parse_channel_page(html: str, username: str) -> ParsedChannel:
    """Parse a full t.me/s/<channel> page into a ParsedChannel."""
    soup = BeautifulSoup(html, "lxml")

    channel = ParsedChannel(
        username=username,
        title=_text_or_none(soup.select_one(".tgme_channel_info_header_title")),
        description=_text_or_none(soup.select_one(".tgme_channel_info_description")),
        subscribers=_parse_subscribers(soup),
    )

    photo = soup.select_one(".tgme_page_photo_image img, .tgme_channel_info_header_photo img")
    if photo and photo.get("src"):
        channel.photo_url = photo["src"]

    for wrap in soup.select(".tgme_widget_message_wrap"):
        msg = wrap.select_one(".tgme_widget_message")
        if not msg:
            continue
        tg_msg_id = _msg_id_from_data_post(msg.get("data-post", ""))
        if tg_msg_id is None:
            continue

        text = _text_or_none(wrap.select_one(".tgme_widget_message_text")) or ""
        has_media = bool(
            wrap.select_one(
                ".tgme_widget_message_photo_wrap, .tgme_widget_message_video, "
                ".tgme_widget_message_document, .tgme_widget_message_voice, "
                ".tgme_widget_message_sticker"
            )
        )
        link = (msg.get("data-post") and f"https://t.me/{msg['data-post']}") or (
            f"https://t.me/{username}/{tg_msg_id}"
        )

        channel.posts.append(
            ParsedPost(
                tg_msg_id=tg_msg_id,
                text=text,
                link=link,
                posted_at=_parse_datetime(wrap),
                views=parse_count(_text_or_none(wrap.select_one(".tgme_widget_message_views"))),
                forwards=parse_count(
                    _text_or_none(wrap.select_one(".tgme_widget_message_forwards"))
                ),
                reactions=_parse_reactions(wrap),
                has_media=has_media,
            )
        )

    return channel


def looks_like_missing_channel(html: str) -> bool:
    """A non-existent / private channel's t.me/s page has neither message posts
    nor the channel-info header. A real channel always has at least the header
    (even with zero visible posts)."""
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one(".tgme_widget_message_wrap"):
        return False
    has_header = soup.select_one(".tgme_channel_info_header_title")
    return has_header is None
