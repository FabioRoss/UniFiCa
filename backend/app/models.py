"""Database tables.

Times are stored as naive UTC (SQLite has no timezone type); `utcnow()` is
the single source for them and the API serialises them with a trailing Z.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Source(Base):
    """A monitored page: a news list (one item per article) or a single page."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # Group shown to users, e.g. "Medicina e Chirurgia"
    category: Mapped[str] = mapped_column(String(120), default="")
    # "news" = list of articles, "page" = one page watched for changes,
    # "exams" = ESSE3 exam sessions
    kind: Mapped[str] = mapped_column(String(20), default="news")
    # "unifi_news" | "css_list" | "page" | "esse3_appelli"
    parser: Mapped[str] = mapped_column(String(40), default="unifi_news")
    url: Mapped[str] = mapped_column(String(1000))
    # Optional older-news list, read once to backfill history
    archive_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # CSS selectors overriding the parser preset (see scraper/parsers.py)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    track_attachments: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    baseline_done: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_ok_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_item_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    items: Mapped[list[Item]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Item(Base):
    """One article (or the watched page itself) with its current content."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_id", "url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    published_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, default="")
    # [{url, name, hash, etag, last_modified, size, text}]
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Other links inside the content [{text, url}], shown but not tracked
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Structured fields for exam sessions (date, time, teachers, ...)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    version_count: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    checked_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    source: Mapped[Source] = relationship(back_populates="items")
    versions: Mapped[list[Version]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Version.number"
    )


class Version(Base):
    """A snapshot taken when an item first appeared or changed. These are the
    feed entries and what notifications are about."""

    __tablename__ = "versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # "new" | "modified"
    # Recorded on a source's first run: shown in history, never notified
    baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    change_summary: Mapped[str] = mapped_column(String(500), default="")
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False)
    push_sent: Mapped[int] = mapped_column(Integer, default=0)
    telegram_sent: Mapped[int] = mapped_column(Integer, default=0)

    item: Mapped[Item] = relationship(back_populates="versions")


class Subscriber(Base):
    """An anonymous device (Web Push) or Telegram chat, with its filters."""

    __tablename__ = "subscribers"
    __table_args__ = (UniqueConstraint("channel", "endpoint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))  # "push" | "telegram"
    # Push endpoint URL, or the Telegram chat id
    endpoint: Mapped[str] = mapped_column(String(1000))
    keys: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Random secret the owner uses to read and change its preferences
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(20), default="")
    prefs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    last_active_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    last_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Pending(Base):
    """A notification held back by quiet hours or digest mode."""

    __tablename__ = "pending"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id", ondelete="CASCADE"), nullable=True)
    announcement_id: Mapped[int | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Announcement(Base):
    """A message written by the admin and broadcast to subscribers."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    push_sent: Mapped[int] = mapped_column(Integer, default=0)
    telegram_sent: Mapped[int] = mapped_column(Integer, default=0)


class LinkGroup(Base):
    __tablename__ = "link_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(40), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    links: Mapped[list[Link]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="Link.position"
    )


class Link(Base):
    """A useful link or a contact (office, professor, secretariat)."""

    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("link_groups.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="link")  # "link" | "contact"
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str] = mapped_column(String(300), default="")
    phone: Mapped[str] = mapped_column(String(100), default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    hours: Mapped[str] = mapped_column(String(300), default="")
    tags: Mapped[str] = mapped_column(String(300), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped[LinkGroup] = relationship(back_populates="links")


class Alert(Base):
    """Something the admin should look at (a broken scraper, mostly)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    level: Mapped[str] = mapped_column(String(20), default="warning")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
