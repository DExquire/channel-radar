"""Idempotency of ingestion — the core data-integrity guarantee.

Ingesting the same parsed page twice must NOT create duplicate posts, but must
append a new metric snapshot each time (that's how dynamics are preserved).
"""
from __future__ import annotations

from app.models import Channel, ChannelStatus, Post, PostMetric
from app.repositories import channel_repo, post_repo
from app.services import collector
from app.services.parser import parse_channel_page


def _make_channel(session):
    ch = channel_repo.create_pending(session, "sample")
    session.flush()
    return ch


def test_ingest_is_idempotent(db_session, sample_html):
    ch = _make_channel(db_session)
    parsed = parse_channel_page(sample_html, "sample")

    r1 = collector.ingest(db_session, ch, parsed)
    db_session.flush()
    assert r1.new_posts == 3
    assert post_repo.count_for_channel(db_session, ch.id) == 3

    # Second ingest of the identical page: no new posts.
    r2 = collector.ingest(db_session, ch, parsed)
    db_session.flush()
    assert r2.new_posts == 0
    assert r2.updated_posts == 3
    assert post_repo.count_for_channel(db_session, ch.id) == 3


def test_metric_snapshots_accumulate(db_session, sample_html):
    ch = _make_channel(db_session)
    parsed = parse_channel_page(sample_html, "sample")

    collector.ingest(db_session, ch, parsed)
    collector.ingest(db_session, ch, parsed)
    db_session.flush()

    post = post_repo.get_by_natural_key(db_session, ch.id, 101)
    series = post_repo.metric_series(db_session, post.id)
    # Two ingests -> two snapshots for the same post (dynamics preserved).
    assert len(series) == 2
    assert all(s.views == 12_500 for s in series)


def test_new_post_added_on_second_page(db_session, sample_html):
    ch = _make_channel(db_session)
    parsed = parse_channel_page(sample_html, "sample")
    collector.ingest(db_session, ch, parsed)
    db_session.flush()

    # Simulate a later page with one extra post.
    parsed.posts.append(
        type(parsed.posts[0])(
            tg_msg_id=104, text="new", link="https://t.me/sample/104", posted_at=None, views=10
        )
    )
    r = collector.ingest(db_session, ch, parsed)
    db_session.flush()
    assert r.new_posts == 1
    assert post_repo.count_for_channel(db_session, ch.id) == 4


def test_ingest_sets_channel_active(db_session, sample_html):
    ch = _make_channel(db_session)
    assert ch.status == ChannelStatus.pending
    collector.ingest(db_session, ch, parse_channel_page(sample_html, "sample"))
    assert ch.status == ChannelStatus.active
    assert ch.subscribers == 1_200_000
