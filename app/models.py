"""ORM models.

Design notes (see docs/adr/0002-metrics-dynamics-storage.md):

* Natural keys enforce idempotency at the DB level:
    - Channel.username is UNIQUE.
    - Post is UNIQUE per (channel_id, tg_msg_id) — the Telegram message id is the
      natural key, so re-collecting the same page never duplicates a post.
* Metrics change over time (views, reactions, subscribers grow). Instead of
  overwriting the latest value we APPEND a snapshot row on every collection:
    - PostMetric  -> per-post time series (views/forwards/reactions).
    - ChannelMetric -> per-channel time series (subscribers/post_count).
  This is what lets the dashboard draw trends rather than only "current value".
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ChannelStatus(str, enum.Enum):
    pending = "pending"      # added, first collection not finished yet
    active = "active"        # collected at least once, source healthy
    error = "error"          # last collection failed (not found / private / network)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)

    subscribers: Mapped[int | None] = mapped_column(Integer)  # latest cached value
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus), default=ChannelStatus.pending, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    posts: Mapped[list["Post"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["ChannelMetric"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("channel_id", "tg_msg_id", name="uq_post_channel_msg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tg_msg_id: Mapped[int] = mapped_column(Integer, nullable=False)  # natural key part

    text: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    has_media: Mapped[bool] = mapped_column(Boolean, default=False)

    # AI-derived category (nullable — dashboard degrades gracefully without it).
    category: Mapped[str | None] = mapped_column(String(64), index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channel: Mapped["Channel"] = relationship(back_populates="posts")
    metrics: Mapped[list["PostMetric"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class PostMetric(Base):
    """Append-only snapshot of a post's metrics at a point in time."""

    __tablename__ = "post_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    views: Mapped[int] = mapped_column(Integer, default=0)
    forwards: Mapped[int] = mapped_column(Integer, default=0)
    reactions: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    post: Mapped["Post"] = relationship(back_populates="metrics")


class ChannelMetric(Base):
    """Append-only snapshot of channel-level metrics at a point in time."""

    __tablename__ = "channel_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscribers: Mapped[int | None] = mapped_column(Integer)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    channel: Mapped["Channel"] = relationship(back_populates="metrics")


class ChannelDigest(Base):
    """Cached AI digest for a channel/period so we don't re-call the LLM per view."""

    __tablename__ = "channel_digests"
    __table_args__ = (
        UniqueConstraint("channel_id", "period", name="uq_digest_channel_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "7d"
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
