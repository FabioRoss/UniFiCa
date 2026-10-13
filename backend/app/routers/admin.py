"""Admin API: login, dashboard stats, sources, items, links, announcements,
alerts, subscribers and site settings."""
from __future__ import annotations

import asyncio
import datetime as dt
import re
import secrets
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store
from ..config import settings
from ..db import get_db
from ..models import (
    Alert, Announcement, Item, Link, LinkGroup, Pending, Source, Subscriber, Version, utcnow,
)
from ..notify import dispatcher, telegram
from ..notify import prefs as P
from ..scraper import engine
from ..scraper.parsers import PARSERS, PRESETS
from ..security import (
    COOKIE, SESSION_DAYS, admin_locked, client_ip, make_session, record_failure, require_admin, throttled,
    user_matches, verify_password,
)
from .public import att_out, iso, link_out

router = APIRouter(prefix="/api/admin")
auth = [Depends(require_admin)]


# ── Session ──────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    if request.headers.get("x-openunifi") != "1":
        raise HTTPException(403, "Richiesta non valida")
    if admin_locked():
        raise HTTPException(503, "Pannello bloccato: imposta OPENUNIFI_ADMIN_USER (non 'admin') e "
                                 "OPENUNIFI_ADMIN_PASSWORD nel file .env")
    ip = client_ip(request)
    if throttled(ip):
        raise HTTPException(429, "Troppi tentativi, riprova tra qualche minuto")
    # Evaluate both, so response time does not reveal whether the user exists
    user_ok = user_matches(body.username)
    pass_ok = verify_password(body.password, settings.admin_password)
    ok = user_ok and pass_ok
    if not ok:
        record_failure(ip)
        raise HTTPException(401, "Credenziali non valide")
    response.set_cookie(
        COOKIE, make_session(db), max_age=SESSION_DAYS * 86400, httponly=True, samesite="strict",
        secure=settings.base_url.startswith("https"), path="/api",
    )
    return {"user": settings.admin_user}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE, path="/api")
    return {"ok": True}


@router.get("/me", dependencies=auth)
def me() -> dict[str, Any]:
    return {"user": settings.admin_user, "configured": bool(settings.admin_password)}


# ── Dashboard ────────────────────────────────────────────────────────────

@router.get("/stats", dependencies=auth)
def stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    now = utcnow()
    subs = list(db.scalars(select(Subscriber).where(Subscriber.active.is_(True))))
    sources = list(db.scalars(select(Source).order_by(Source.position, Source.id)))

    followers: Counter[int] = Counter()
    keywords: Counter[str] = Counter()
    modes = Counter()
    for s in subs:
        p = P.merged(s.prefs)
        if p["sources"] is None:
            for src in sources:
                followers[src.id] += 1
        else:
            followers.update(p["sources"])
        keywords.update(k.lower() for k in p["keywords"])
        modes["digest" if p["digest"] else "quiet" if p["quiet"] else "instant"] += 1

    def versions_since(days: int) -> int:
        return db.scalar(select(func.count()).select_from(Version).where(
            Version.baseline.is_(False), Version.created_at >= now - dt.timedelta(days=days))) or 0

    def sent_since(days: int) -> int:
        since = now - dt.timedelta(days=days)
        v = db.scalar(select(func.coalesce(func.sum(Version.push_sent + Version.telegram_sent), 0))
                      .where(Version.created_at >= since)) or 0
        a = db.scalar(select(func.coalesce(func.sum(Announcement.push_sent + Announcement.telegram_sent), 0))
                      .where(Announcement.created_at >= since)) or 0
        return int(v) + int(a)

    # Updates per day for the last 30 days (Europe/Rome dates)
    tz = P.tz()
    per_day: Counter[str] = Counter()
    for (created,) in db.execute(select(Version.created_at).where(
            Version.baseline.is_(False), Version.created_at >= now - dt.timedelta(days=30))):
        per_day[created.replace(tzinfo=dt.timezone.utc).astimezone(tz).date().isoformat()] += 1
    today = dt.datetime.now(tz).date()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]

    return {
        "subscribers": {
            "total": len(subs),
            "push": sum(s.channel == "push" for s in subs),
            "telegram": sum(s.channel == "telegram" for s in subs),
            "new_7d": sum(s.created_at >= now - dt.timedelta(days=7) for s in subs),
            "platforms": dict(Counter(s.platform or "other" for s in subs)),
            "modes": dict(modes),
            "admins": sum(s.is_admin for s in subs),
            "inactive": db.scalar(select(func.count()).select_from(Subscriber)
                                  .where(Subscriber.active.is_(False))) or 0,
        },
        "updates": {"day": versions_since(1), "week": versions_since(7), "month": versions_since(30)},
        "updates_per_day": [{"date": d, "count": per_day.get(d, 0)} for d in days],
        "notifications": {"week": sent_since(7), "month": sent_since(30)},
        "pending": db.scalar(select(func.count()).select_from(Pending)) or 0,
        "items": db.scalar(select(func.count()).select_from(Item)) or 0,
        "top_keywords": keywords.most_common(15),
        "sources": [
            {"id": s.id, "name": s.name, "enabled": s.enabled, "followers": followers.get(s.id, 0),
             "ok": s.consecutive_failures == 0, "last_run_at": iso(s.last_run_at),
             "last_ok_at": iso(s.last_ok_at), "error": s.last_error}
            for s in sources
        ],
        "alerts": db.scalar(select(func.count()).select_from(Alert).where(Alert.resolved.is_(False))) or 0,
        "telegram": {"enabled": telegram.enabled(), "bot": telegram.bot_username(),
                     "channel": settings.telegram_channel},
        "backup": _backup_info(),
    }


def _backup_info() -> dict[str, Any]:
    from .. import backup

    files = backup.backups()
    last = files[-1] if files else None
    return {"count": len(files), "last": last.name if last else None,
            "last_at": iso(dt.datetime.fromtimestamp(last.stat().st_mtime, dt.timezone.utc).replace(tzinfo=None))
            if last else None}


# ── Sources ──────────────────────────────────────────────────────────────

class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=80)
    category: str = Field("", max_length=120)
    kind: str = Field("news", pattern="^(news|page|exams)$")
    parser: str = "unifi_news"
    url: str = Field(pattern=r"^https?://", max_length=1000)
    archive_url: str | None = Field(None, max_length=1000)
    config: dict[str, Any] = {}
    interval_minutes: int = Field(15, ge=5, le=10080)
    enabled: bool = True
    track_attachments: bool = True
    position: int = 0


def _slugify(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:70] or "fonte"


def source_admin_out(s: Source) -> dict[str, Any]:
    return {
        "id": s.id, "slug": s.slug, "name": s.name, "category": s.category, "kind": s.kind,
        "parser": s.parser, "url": s.url, "archive_url": s.archive_url, "config": s.config or {},
        "interval_minutes": s.interval_minutes, "enabled": s.enabled,
        "track_attachments": s.track_attachments, "position": s.position,
        "baseline_done": s.baseline_done, "last_run_at": iso(s.last_run_at), "last_ok_at": iso(s.last_ok_at),
        "last_error": s.last_error, "consecutive_failures": s.consecutive_failures,
        "last_item_count": s.last_item_count,
        "items": len(s.items),
    }


def _apply_source(s: Source, body: SourceIn) -> None:
    if body.parser not in PARSERS:
        raise HTTPException(422, "Parser sconosciuto")
    expected = {"page": "page", "exams": "esse3_appelli"}.get(body.kind)
    if expected and body.parser != expected:
        raise HTTPException(422, f"Questo tipo di fonte usa il parser '{expected}'")
    if body.kind == "news" and body.parser in ("page", "esse3_appelli"):
        raise HTTPException(422, "Per le notizie usa 'unifi_news' o 'css_list'")
    for k in ("name", "category", "kind", "parser", "url", "interval_minutes", "enabled",
              "track_attachments", "position"):
        setattr(s, k, getattr(body, k))
    s.archive_url = body.archive_url or None
    s.config = {k: v for k, v in body.config.items() if v not in ("", None)}


@router.get("/parsers", dependencies=auth)
def parsers() -> dict[str, Any]:
    return PRESETS


@router.get("/sources", dependencies=auth)
def list_sources(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [source_admin_out(s) for s in db.scalars(select(Source).order_by(Source.position, Source.id))]


@router.post("/sources", dependencies=auth)
def create_source(body: SourceIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    slug = _slugify(body.slug or body.name)
    base, n = slug, 2
    while db.scalar(select(Source.id).where(Source.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    s = Source(slug=slug)
    _apply_source(s, body)
    db.add(s)
    db.commit()
    return source_admin_out(s)


@router.put("/sources/{source_id}", dependencies=auth)
def update_source(source_id: int, body: SourceIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.get(Source, source_id)
    if s is None:
        raise HTTPException(404)
    url_changed = s.url != body.url or s.parser != body.parser
    _apply_source(s, body)
    if url_changed:
        # A new target page: take a fresh baseline instead of notifying everything as new.
        s.baseline_done = False
    db.commit()
    return source_admin_out(s)


@router.delete("/sources/{source_id}", dependencies=auth)
def delete_source(source_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    s = db.get(Source, source_id)
    if s is None:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/sources/{source_id}/run", dependencies=auth)
async def run_source(source_id: int) -> dict[str, Any]:
    res = await engine.run_source(source_id)
    return res.as_dict()


class PreviewIn(BaseModel):
    parser: str
    url: str = Field(pattern=r"^https?://")
    config: dict[str, Any] = {}


@router.post("/sources/preview", dependencies=auth)
async def preview(body: PreviewIn) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(engine.preview(body.parser, body.url, body.config), 90)
    except Exception as e:
        raise HTTPException(422, f"Anteprima non riuscita: {e}") from e


@router.get("/esse3/options", dependencies=auth)
async def esse3_options(fac_id: str | None = None) -> dict[str, Any]:
    """Schools and courses as ESSE3 lists them, to fill fac_id / cds_ids."""
    from ..scraper import esse3, fetch

    try:
        async with fetch.make_client() as client:
            return await asyncio.wait_for(esse3.options(client, fac_id), 60)
    except Exception as e:
        raise HTTPException(502, f"ESSE3 non raggiungibile: {e}") from e


# ── Items ────────────────────────────────────────────────────────────────

@router.get("/items", dependencies=auth)
def list_items(source: int | None = None, q: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Item).order_by(Item.changed_at.desc()).limit(200)
    if source:
        stmt = stmt.where(Item.source_id == source)
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    return [{"id": i.id, "title": i.title, "url": i.url, "source": i.source.name, "hidden": i.hidden,
             "versions": i.version_count, "changed_at": iso(i.changed_at),
             "attachments": [att_out(a) for a in i.attachments]} for i in db.scalars(stmt)]


class ItemPatch(BaseModel):
    hidden: bool


@router.put("/items/{item_id}", dependencies=auth)
def patch_item(item_id: int, body: ItemPatch, db: Session = Depends(get_db)) -> dict[str, bool]:
    i = db.get(Item, item_id)
    if i is None:
        raise HTTPException(404)
    i.hidden = body.hidden
    db.commit()
    return {"ok": True}


# ── Links ────────────────────────────────────────────────────────────────

class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    icon: str = Field("", max_length=40)


class LinkIn(BaseModel):
    group_id: int
    kind: str = Field("link", pattern="^(link|contact)$")
    title: str = Field(min_length=1, max_length=300)
    url: str = Field("", max_length=1000)
    description: str = Field("", max_length=2000)
    email: str = Field("", max_length=300)
    phone: str = Field("", max_length=100)
    location: str = Field("", max_length=300)
    hours: str = Field("", max_length=300)
    tags: str = Field("", max_length=300)


class OrderIn(BaseModel):
    ids: list[int]


def _check_url(url: str) -> None:
    if url and not re.match(r"^(https?://|mailto:|tel:|/)", url):
        raise HTTPException(422, "Il link deve iniziare con https://")


@router.post("/link-groups", dependencies=auth)
def create_group(body: GroupIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    pos = (db.scalar(select(func.max(LinkGroup.position))) or 0) + 1
    g = LinkGroup(position=pos, **body.model_dump())
    db.add(g)
    db.commit()
    return {"id": g.id}


@router.put("/link-groups/{group_id}", dependencies=auth)
def update_group(group_id: int, body: GroupIn, db: Session = Depends(get_db)) -> dict[str, bool]:
    g = db.get(LinkGroup, group_id)
    if g is None:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/link-groups/{group_id}", dependencies=auth)
def delete_group(group_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    g = db.get(LinkGroup, group_id)
    if g is None:
        raise HTTPException(404)
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.post("/link-groups/order", dependencies=auth)
def order_groups(body: OrderIn, db: Session = Depends(get_db)) -> dict[str, bool]:
    for pos, gid in enumerate(body.ids):
        g = db.get(LinkGroup, gid)
        if g is not None:
            g.position = pos
    db.commit()
    return {"ok": True}


@router.post("/links", dependencies=auth)
def create_link(body: LinkIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_url(body.url)
    if db.get(LinkGroup, body.group_id) is None:
        raise HTTPException(422, "Gruppo inesistente")
    pos = (db.scalar(select(func.max(Link.position)).where(Link.group_id == body.group_id)) or 0) + 1
    link = Link(position=pos, **body.model_dump())
    db.add(link)
    db.commit()
    return link_out(link)


@router.put("/links/{link_id}", dependencies=auth)
def update_link(link_id: int, body: LinkIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_url(body.url)
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(404)
    if body.group_id != link.group_id:
        link.position = (db.scalar(select(func.max(Link.position)).where(Link.group_id == body.group_id)) or 0) + 1
    for k, v in body.model_dump().items():
        setattr(link, k, v)
    db.commit()
    return link_out(link)


@router.delete("/links/{link_id}", dependencies=auth)
def delete_link(link_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(404)
    db.delete(link)
    db.commit()
    return {"ok": True}


@router.post("/links/order", dependencies=auth)
def order_links(body: OrderIn, db: Session = Depends(get_db)) -> dict[str, bool]:
    for pos, lid in enumerate(body.ids):
        link = db.get(Link, lid)
        if link is not None:
            link.position = pos
    db.commit()
    return {"ok": True}


# ── Announcements ────────────────────────────────────────────────────────

class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field("", max_length=3000)
    url: str = Field("", max_length=1000)
    pinned: bool = False
    send: bool = True


def ann_out(a: Announcement) -> dict[str, Any]:
    return {"id": a.id, "title": a.title, "body": a.body, "url": a.url, "pinned": a.pinned,
            "created_at": iso(a.created_at), "push_sent": a.push_sent, "telegram_sent": a.telegram_sent}


@router.get("/announcements", dependencies=auth)
def list_announcements(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [ann_out(a) for a in db.scalars(select(Announcement).order_by(Announcement.created_at.desc()))]


@router.post("/announcements", dependencies=auth)
async def create_announcement(body: AnnouncementIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_url(body.url)
    a = Announcement(title=body.title, body=body.body, url=body.url, pinned=body.pinned)
    db.add(a)
    db.commit()
    result = await dispatcher.broadcast(a.id) if body.send else {}
    db.refresh(a)
    return {**ann_out(a), "result": result}


@router.put("/announcements/{ann_id}", dependencies=auth)
def update_announcement(ann_id: int, body: AnnouncementIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_url(body.url)
    a = db.get(Announcement, ann_id)
    if a is None:
        raise HTTPException(404)
    a.title, a.body, a.url, a.pinned = body.title, body.body, body.url, body.pinned
    db.commit()
    return ann_out(a)


@router.delete("/announcements/{ann_id}", dependencies=auth)
def delete_announcement(ann_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    a = db.get(Announcement, ann_id)
    if a is None:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── Alerts ───────────────────────────────────────────────────────────────

@router.get("/alerts", dependencies=auth)
def list_alerts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Alert).order_by(Alert.resolved, Alert.created_at.desc()).limit(100))
    return [{"id": a.id, "created_at": iso(a.created_at), "level": a.level, "source_id": a.source_id,
             "message": a.message, "resolved": a.resolved} for a in rows]


@router.post("/alerts/{alert_id}/resolve", dependencies=auth)
def resolve_alert(alert_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404)
    a.resolved = True
    db.commit()
    return {"ok": True}


# ── Subscribers ──────────────────────────────────────────────────────────

@router.get("/subscribers", dependencies=auth)
def list_subscribers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    names = {s.id: s.name for s in db.scalars(select(Source))}
    out = []
    for s in db.scalars(select(Subscriber).order_by(Subscriber.created_at.desc()).limit(500)):
        p = P.merged(s.prefs)
        out.append({
            "id": s.id, "channel": s.channel, "platform": s.platform, "active": s.active,
            "is_admin": s.is_admin, "created_at": iso(s.created_at), "last_active_at": iso(s.last_active_at),
            "last_sent_at": iso(s.last_sent_at), "failures": s.failures,
            "sources": "tutte" if p["sources"] is None else ", ".join(names.get(i, "?") for i in p["sources"]),
            "keywords": p["keywords"], "mode": "digest" if p["digest"] else "quiet" if p["quiet"] else "instant",
        })
    return out


class SubscriberPatch(BaseModel):
    is_admin: bool


@router.put("/subscribers/{sub_id}", dependencies=auth)
def patch_subscriber(sub_id: int, body: SubscriberPatch, db: Session = Depends(get_db)) -> dict[str, bool]:
    s = db.get(Subscriber, sub_id)
    if s is None:
        raise HTTPException(404)
    s.is_admin = body.is_admin
    db.commit()
    return {"ok": True}


@router.delete("/subscribers/{sub_id}", dependencies=auth)
def delete_subscriber(sub_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    s = db.get(Subscriber, sub_id)
    if s is None:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return {"ok": True}


class DeviceIn(BaseModel):
    token: str


@router.post("/admin-device", dependencies=auth)
def admin_device(body: DeviceIn, db: Session = Depends(get_db)) -> dict[str, bool]:
    """Mark this browser's push subscription as an admin-alert recipient."""
    s = db.scalar(select(Subscriber).where(Subscriber.token == body.token))
    if s is None:
        raise HTTPException(404, "Attiva prima le notifiche su questo dispositivo")
    s.is_admin = True
    db.commit()
    return {"ok": True}


@router.post("/telegram-code", dependencies=auth)
def telegram_code(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not telegram.enabled():
        raise HTTPException(422, "Bot Telegram non configurato")
    code = secrets.token_hex(4)
    expires = utcnow() + dt.timedelta(minutes=15)
    settings_store.put(db, "admin_link_code", {"code": code, "expires": expires.isoformat()})
    bot = telegram.bot_username()
    return {"code": code, "expires_at": iso(expires),
            "link": f"https://t.me/{bot}?start=admin_{code}" if bot else None}


@router.post("/test-admin-alert", dependencies=auth)
async def test_admin_alert() -> dict[str, bool]:
    await dispatcher.notify_admins("🔔 Test: gli avvisi di amministrazione arrivano qui.")
    return {"ok": True}


# ── Site settings ────────────────────────────────────────────────────────

class SiteIn(BaseModel):
    intro: str = Field("", max_length=1000)
    disclaimer: str = Field("", max_length=2000)
    contact_email: str = Field("", max_length=200)
    telegram_channel_url: str = Field("", max_length=300)


@router.get("/settings", dependencies=auth)
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_store.site(db)


@router.put("/settings", dependencies=auth)
def put_settings(body: SiteIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_url(body.telegram_channel_url)
    settings_store.put(db, "site", body.model_dump())
    return settings_store.site(db)
