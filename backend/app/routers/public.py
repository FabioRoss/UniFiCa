"""Public API: feed, items with diffs, sources, links, announcements, RSS."""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import rss, settings_store
from ..config import settings
from ..db import get_db
from ..models import Announcement, Item, LinkGroup, Source, Version, utcnow
from ..notify import prefs as P
from ..notify import telegram
from ..text import attachment_changes, line_diff

router = APIRouter()


def iso(t: dt.datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") + "Z" if t else None


def source_out(s: Source) -> dict[str, Any]:
    return {"id": s.id, "slug": s.slug, "name": s.name, "category": s.category, "kind": s.kind,
            "url": s.url, "last_ok_at": iso(s.last_ok_at), "interval_minutes": s.interval_minutes}


def att_out(a: dict[str, Any]) -> dict[str, Any]:
    return {"url": a["url"], "name": a.get("name") or a.get("file") or a["url"],
            "file": a.get("file", ""), "size": a.get("size"), "type": a.get("type", "")}


@router.get("/api/config")
def config(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "site_name": settings.site_name,
        "base_url": settings.base_url,
        "vapid_public_key": settings_store.vapid_keys(db)["public"],
        "telegram_bot": telegram.bot_username(),
        "telegram_enabled": telegram.enabled(),
        "site": settings_store.site(db),
    }


@router.get("/api/sources")
def sources(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.position, Source.id))
    return [source_out(s) for s in rows]


def _search_filter(q: str):  # noqa: ANN202
    conds = []
    for word in q.split()[:6]:
        like = f"%{word}%"
        conds.append(or_(Item.title.ilike(like), Item.summary.ilike(like), Item.content_text.ilike(like)))
    return conds


@router.get("/api/feed")
def feed(
    db: Session = Depends(get_db),
    source: int | None = None,
    category: str | None = None,
    kind: str | None = Query(None, pattern="^(new|modified)$"),
    q: str | None = Query(None, max_length=100),
    before: int | None = None,
    limit: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    stmt = (
        select(Version, Item, Source)
        .join(Item, Version.item_id == Item.id)
        .join(Source, Item.source_id == Source.id)
        .where(Item.hidden.is_(False))
        # The feed is for news and watched pages (shown from the start, dated
        # by the site's own "last updated" date). Exam sessions, new or
        # changed, only appear on their own page (/esami); subscribers are
        # still notified about them.
        .where(Source.kind != "exams")
    )
    if source:
        stmt = stmt.where(Source.id == source)
    if category:
        stmt = stmt.where(Source.category == category)
    if kind:
        stmt = stmt.where(Version.kind == kind)
    if q and q.strip():
        stmt = stmt.where(*_search_filter(q.strip()))
    if before:
        ref = db.get(Version, before)
        if ref is not None:
            stmt = stmt.where(
                or_(Version.created_at < ref.created_at,
                    (Version.created_at == ref.created_at) & (Version.id < ref.id))
            )
    rows = db.execute(stmt.order_by(Version.created_at.desc(), Version.id.desc()).limit(limit + 1)).all()
    out = []
    for v, item, src in rows[:limit]:
        out.append({
            "id": v.id,
            "number": v.number,
            "kind": v.kind,
            "baseline": v.baseline,
            "created_at": iso(v.created_at),
            "change_summary": v.change_summary,
            "item": {
                "id": item.id, "title": v.title or item.title, "summary": item.summary,
                "url": item.url, "published_on": item.published_on.isoformat() if item.published_on else None,
                "attachments": len(v.attachments or []),
                "source": {"id": src.id, "name": src.name, "category": src.category, "kind": src.kind},
            },
        })
    return {"entries": out, "next": out[-1]["id"] if len(rows) > limit else None}


@router.get("/api/items/{item_id}")
def item_detail(item_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.get(Item, item_id)
    if item is None or item.hidden:
        raise HTTPException(404, "Contenuto non trovato")
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "url": item.url,
        "published_on": item.published_on.isoformat() if item.published_on else None,
        "content_text": item.content_text,
        # Sanitised rendering with tables and inline links (richtext.py); older items have none
        "html": (item.meta or {}).get("html") or None,
        "attachments": [att_out(a) for a in item.attachments],
        "links": item.links,
        "first_seen_at": iso(item.first_seen_at),
        "changed_at": iso(item.changed_at),
        "checked_at": iso(item.checked_at),
        "source": source_out(item.source),
        "versions": [
            {"number": v.number, "kind": v.kind, "baseline": v.baseline, "created_at": iso(v.created_at),
             "change_summary": v.change_summary}
            for v in reversed(item.versions)
        ],
    }


@router.get("/api/items/{item_id}/versions/{number}/diff")
def version_diff(item_id: int, number: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.get(Item, item_id)
    if item is None or item.hidden:
        raise HTTPException(404, "Contenuto non trovato")
    by_num = {v.number: v for v in item.versions}
    cur = by_num.get(number)
    if cur is None:
        raise HTTPException(404, "Versione non trovata")
    prev = by_num.get(number - 1)
    out: dict[str, Any] = {
        "number": number, "kind": cur.kind, "created_at": iso(cur.created_at),
        "change_summary": cur.change_summary, "title": cur.title, "previous": None,
    }
    if prev is None:
        out["text"] = [{"op": "eq", "text": x} for x in cur.content_text.splitlines()]
        out["attachments"] = {"added": [att_out(a) for a in cur.attachments], "removed": [], "changed": []}
        return out
    ch = attachment_changes(prev.attachments, cur.attachments)
    old_att = {a["url"]: a for a in prev.attachments}
    changed = []
    for a in ch["changed"]:
        row = att_out(a)
        o = old_att.get(a["url"], {})
        if o.get("text") or a.get("text"):
            row["diff"] = line_diff(o.get("text", ""), a.get("text", ""))
        changed.append(row)
    out.update(
        previous={"number": prev.number, "created_at": iso(prev.created_at)},
        title_change={"old": prev.title, "new": cur.title} if prev.title != cur.title else None,
        text=line_diff(prev.content_text, cur.content_text),
        attachments={"added": [att_out(a) for a in ch["added"]],
                     "removed": [att_out(a) for a in ch["removed"]], "changed": changed},
    )
    return out


@router.get("/api/exams")
def exams(
    db: Session = Depends(get_db),
    source: int | None = None,
    q: str | None = Query(None, max_length=100),
    days: int = Query(200, ge=1, le=400),
) -> dict[str, Any]:
    """Upcoming exam sessions (from today), soonest first."""
    today = dt.datetime.now(P.tz()).date()
    stmt = (
        select(Item, Source).join(Source, Item.source_id == Source.id)
        .where(Source.kind == "exams", Item.hidden.is_(False), Item.published_on >= today,
               Item.published_on <= today + dt.timedelta(days=days))
    )
    if source:
        stmt = stmt.where(Source.id == source)
    if q and q.strip():
        stmt = stmt.where(*_search_filter(q.strip()))
    rows = db.execute(stmt.order_by(Item.published_on, Item.title).limit(1500)).all()
    # "Nuovo" badge: sessions published in the last 3 days (not the baseline import)
    recent = set(db.scalars(select(Version.item_id).where(
        Version.kind == "new", Version.baseline.is_(False),
        Version.created_at >= utcnow() - dt.timedelta(days=3))))
    from ..exam_snapshot import snapshot_at

    return {
        # snapshot_at: when imported data was fetched elsewhere (the page shows
        # it as the data's date until a real check succeeds)
        "sources": [{**source_out(s), "snapshot_at": snapshot_at(db, s.id)} for s in db.scalars(
            select(Source).where(Source.kind == "exams", Source.enabled.is_(True)))],
        "exams": [
            {"id": i.id, "title": i.title, "url": i.url, "date": i.published_on.isoformat(),
             "changed": i.version_count > 1, "recent": i.id in recent, "source_id": s.id, **(i.meta or {})}
            for i, s in rows
        ],
    }


@router.get("/api/announcements")
def announcements(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    since = utcnow() - dt.timedelta(days=30)
    rows = db.scalars(
        select(Announcement).where(or_(Announcement.pinned.is_(True), Announcement.created_at >= since))
        .order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).limit(10)
    )
    return [{"id": a.id, "title": a.title, "body": a.body, "url": a.url, "pinned": a.pinned,
             "created_at": iso(a.created_at)} for a in rows]


def link_out(l) -> dict[str, Any]:  # noqa: ANN001, E741
    return {"id": l.id, "kind": l.kind, "title": l.title, "url": l.url, "description": l.description,
            "email": l.email, "phone": l.phone, "location": l.location, "hours": l.hours, "tags": l.tags,
            "position": l.position, "group_id": l.group_id}


@router.get("/api/links")
def links(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    groups = db.scalars(select(LinkGroup).order_by(LinkGroup.position, LinkGroup.id))
    return [{"id": g.id, "name": g.name, "description": g.description, "icon": g.icon,
             "links": [link_out(l) for l in g.links]} for g in groups]


# ── RSS ──────────────────────────────────────────────────────────────────

def _rss_entries(db: Session, source_id: int | None) -> list[dict[str, Any]]:
    stmt = (
        select(Version, Item, Source).join(Item, Version.item_id == Item.id)
        .join(Source, Item.source_id == Source.id).where(Item.hidden.is_(False))
    )
    if source_id:
        stmt = stmt.where(Source.id == source_id)
    else:
        stmt = stmt.where(Source.kind != "exams")  # like the home feed; exams have their own feed
    rows = db.execute(stmt.order_by(Version.created_at.desc()).limit(50)).all()
    out = []
    for v, item, src in rows:
        prefix = "" if v.kind == "new" else "[Modificato] "
        desc = v.change_summary if v.kind == "modified" else (item.summary or v.content_text[:500])
        out.append({
            "title": prefix + (v.title or item.title),
            "link": f"{settings.base_url}/n/{item.id}?v={v.number}",
            "guid": f"openunifi-v{v.id}",
            "description": desc,
            "date": v.created_at,
            "category": src.name,
        })
    return out


@router.get("/rss.xml", include_in_schema=False)
def rss_all(db: Session = Depends(get_db)) -> Response:
    xml = rss.build(f"{settings.site_name}: tutti gli aggiornamenti", "/",
                    "Novità e modifiche dai siti dell'Università di Firenze", _rss_entries(db, None))
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/rss/{slug}.xml", include_in_schema=False)
def rss_source(slug: str, db: Session = Depends(get_db)) -> Response:
    src = db.scalar(select(Source).where(Source.slug == slug))
    if src is None:
        raise HTTPException(404)
    xml = rss.build(f"{settings.site_name}: {src.name}", "/", f"Aggiornamenti da {src.url}",
                    _rss_entries(db, src.id))
    return Response(xml, media_type="application/rss+xml; charset=utf-8")
