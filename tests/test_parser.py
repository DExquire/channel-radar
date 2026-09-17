"""Parser normalization on saved fixtures — no network."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services.parser import (
    looks_like_missing_channel,
    parse_channel_page,
    parse_count,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.2K", 1200),
        ("3.4M", 3_400_000),
        ("1 234", 1234),
        ("1,234", 1234),
        ("890", 890),
        ("", 0),
        (None, 0),
        ("no digits", 0),
    ],
)
def test_parse_count(raw, expected):
    assert parse_count(raw) == expected


def test_parse_channel_metadata(sample_html):
    ch = parse_channel_page(sample_html, "sample")
    assert ch.username == "sample"
    assert ch.title == "Sample Channel"
    assert "tech and AI" in ch.description
    assert ch.subscribers == 1_200_000  # 1.2M, not the 3.4K photos counter
    assert ch.photo_url == "https://cdn.example/photo.jpg"


def test_parse_posts(sample_html):
    ch = parse_channel_page(sample_html, "sample")
    assert len(ch.posts) == 3

    first = ch.posts[0]
    assert first.tg_msg_id == 101
    assert first.views == 12_500
    assert first.reactions == 400  # 340 + 60
    assert first.link == "https://t.me/sample/101"
    assert isinstance(first.posted_at, datetime)
    assert first.has_media is False

    second = ch.posts[1]
    assert second.tg_msg_id == 102
    assert second.views == 3200
    assert second.has_media is True  # has a photo wrap


def test_missing_channel_detection(sample_html, missing_html):
    assert looks_like_missing_channel(missing_html) is True
    assert looks_like_missing_channel(sample_html) is False
