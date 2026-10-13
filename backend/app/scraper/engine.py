"""Run a source: fetch, parse, compare with what we stored, record versions.

First successful run of a source is the *baseline*: everything found is
stored (so history and search work from day one) but nobody is notified.
After that, a new URL is a "new" version and a changed content hash is a
"modified" version; both are handed to the notification dispatcher.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import Alert, Item, Source, Version, utcnow
from ..text import change_summary, content_hash, soup
from . import fetch
from .parsers import Entry, Snapshot, parse_content, parse_list, selectors

log = logging.getLogger("openunifi.engine")

FAILURES_BEFORE_ALERT = 3
DEFAULT_MAX_ITEMS = 30
ARCHIVE_MAX_ITEMS = 300

_locks: dict[int, asyncio.Lock] = {}


class ScrapeError(Exception):
    pass


@dataclass
class RunResult:
    ok: bool = True
    items: int = 0
    new: int = 0
    modified: int = 0
    error: str = ""
    seconds: float = 0.0
    version_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "version_ids"}


# ── Fetch + parse ────────────────────────────────────────────────────────

def _with_query(url: str, **params: str) -> str:
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q.update(params)
    return urlunparse(p._replace(query=urlencode(q)))


async def _archive_entries(client: httpx.AsyncClient, src: Source, cfg: dict[str, str]) -> list[Entry]:
    """All pages of the archive list (the unifi CMS paginates with ?start=N)."""
    html = await fetch.get_html(client, src.archive_url)
    entries = parse_list(html, src.archive_url, cfg)
    starts = sorted(
        {int(o["value"]) for o in soup(html).select("select[name=start] option") if o.get("value", "").isdigit()}
    )
    for start in starts:
        if start == 0 or len(entries) >= ARCHIVE_MAX_ITEMS:
            continue
        await asyncio.sleep(settings.request_delay_seconds)
        page = await fetch.get_html(client, _with_query(src.archive_url, start=str(start)))
        entries.extend(parse_list(page, src.archive_url, cfg))
    return entries


async def _snapshots(client: httpx.AsyncClient, src: Source, prev_items: dict[str, Item],
                     include_archive: bool) -> list[tuple[Snapshot, bool]]:
    """[(snapshot, from_archive)] for everything the source currently shows."""
    cfg = selectors(src.parser, src.config)
    delay = settings.request_delay_seconds

    if src.parser == "esse3_appelli":
        from . import esse3

        return [(s, False) for s in await esse3.fetch_sessions(client, cfg)]

    if src.parser == "page":
        html = await fetch.get_html(client, src.url)
        snap = parse_content(html, src.url, cfg)
        if not snap.content_text.strip():
            raise ScrapeError("Contenuto vuoto: il selettore non trova più il testo della pagina")
        return [(snap, False)]

    html = await fetch.get_html(client, src.url)
    entries = parse_list(html, src.url, cfg)
    if not entries:
        raise ScrapeError("Nessun elemento trovato: la struttura della pagina potrebbe essere cambiata")
    max_items = int((src.config or {}).get("max_items") or DEFAULT_MAX_ITEMS)
    entries = entries[:max_items]

    todo: list[tuple[Entry, bool]] = [(e, False) for e in entries]
    if include_archive and src.archive_url:
        try:
            current = {e.url for e in entries}
            todo += [(e, True) for e in await _archive_entries(client, src, cfg) if e.url not in current]
        except Exception as e:  # the archive is a bonus; never fail the run for it
            log.warning("archive of %s failed: %s", src.slug, e)

    out: list[tuple[Snapshot, bool]] = []
    detail = (src.config or {}).get("fetch_detail", True) not in (False, "false", "0")
    for entry, archived in todo:
        if archived and entry.url in prev_items:
            continue
        if detail:
            await asyncio.sleep(delay)
            try:
                snap = parse_content(await fetch.get_html(client, entry.url), entry.url, cfg)
            except fetch.FetchError as e:
                if archived:
                    continue
                # One broken article should not hide the rest; keep the old state.
                log.info("detail %s failed: %s", entry.url, e)
                continue
        else:
            snap = Snapshot(url=entry.url, title=entry.title, content_text=entry.summary)
        snap.title = snap.title or entry.title
        snap.summary = entry.summary
        snap.published_on = entry.published_on or snap.published_on
        out.append((snap, archived))
    return out


async def _attachments(client: httpx.AsyncClient, snap: Snapshot, prev: Item | None,
                       download: bool) -> list[dict[str, Any]]:
    prev_by_url = {a["url"]: a for a in (prev.attachments if prev else [])}
    out = []
    for link in snap.attachment_links:
        if not download:
            p = prev_by_url.get(link["url"])
            out.append({**p, **link} if p else {**link, "hash": ""})
            continue
        await asyncio.sleep(settings.request_delay_seconds / 2)
        out.append(await fetch.fetch_attachment(client, link, prev_by_url.get(link["url"])))
    return out


# ── Compare + store ──────────────────────────────────────────────────────

def _version_atts(atts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = ("url", "name", "file", "hash", "size", "type", "text")
    return [{k: a[k] for k in keep if k in a} for a in atts]


def _comparable_prev(prev: list[dict], new: list[dict]) -> list[dict]:
    """Attachments we never downloaded (hash "") take the new hash, so filling
    in a missing hash is not mistaken for a change."""
    new_by_url = {a["url"]: a for a in new}
    out = []
    for a in prev:
        if not a.get("hash") and a["url"] in new_by_url:
            a = {**a, "hash": new_by_url[a["url"]].get("hash", "")}
        out.append(a)
    return out


def _new_version(db: Session, item: Item, kind: str, baseline: bool, summary: str) -> Version:
    item.version_count += 1
    v = Version(
        item=item,
        number=item.version_count,
        kind=kind,
        baseline=baseline,
        title=item.title,
        summary=item.summary,
        content_text=item.content_text,
        attachments=_version_atts(item.attachments),
        change_summary=summary,
        dispatched=baseline,
    )
    if baseline and kind == "new" and item.published_on:
        # Baseline entries sit in the feed at their publication date.
        v.created_at = min(utcnow(), _date_to_dt(item.published_on))
    db.add(v)
    return v


def _date_to_dt(d):  # noqa: ANN001, ANN202
    import datetime as dt

    return dt.datetime(d.year, d.month, d.day, 12, 0)


def apply_snapshot(db: Session, src: Source, snap: Snapshot, atts: list[dict[str, Any]],
                   prev: Item | None, baseline: bool) -> Version | None:
    new_hash = content_hash(snap.title, snap.content_text, atts)
    now = utcnow()
    if prev is None:
        item = Item(
            source=src,
            url=snap.url,
            title=snap.title or src.name,
            summary=snap.summary,
            published_on=snap.published_on,
            content_text=snap.content_text,
            attachments=atts,
            links=snap.links,
            meta=snap.meta,
            content_hash=new_hash,
            version_count=0,
            first_seen_at=now,
            changed_at=now,
            checked_at=now,
        )
        db.add(item)
        summary = {"page": "Nuova pagina monitorata", "exams": "Nuovo appello"}.get(src.kind, "Nuova pubblicazione")
        v = _new_version(db, item, "new", baseline, summary)
        if baseline and v.created_at:
            item.changed_at = v.created_at
        return v

    prev.checked_at = now
    prev.links = snap.links
    if snap.meta:
        prev.meta = snap.meta
    if snap.summary:
        prev.summary = snap.summary
    if snap.published_on and not prev.published_on:
        prev.published_on = snap.published_on
    old_cmp = content_hash(prev.title, prev.content_text, _comparable_prev(prev.attachments, atts))
    if new_hash == prev.content_hash or new_hash == old_cmp:
        # Same content; still refresh stored attachment metadata (etag etc.).
        prev.attachments = atts
        prev.content_hash = new_hash
        return None

    before = {"title": prev.title, "content_text": prev.content_text, "attachments": prev.attachments}
    prev.title = snap.title or prev.title
    prev.content_text = snap.content_text
    prev.attachments = atts
    prev.content_hash = new_hash
    prev.changed_at = now
    after = {"title": prev.title, "content_text": prev.content_text, "attachments": atts}
    return _new_version(db, prev, "modified", baseline, change_summary(before, after))


def _record_failure(db: Session, src: Source, msg: str) -> Alert | None:
    src.consecutive_failures += 1
    src.last_error = msg[:2000]
    if src.consecutive_failures == FAILURES_BEFORE_ALERT:
        alert = Alert(
            level="error",
            source_id=src.id,
            message=f"{src.name}: {FAILURES_BEFORE_ALERT} controlli falliti di fila. Ultimo errore: {msg}",
        )
        db.add(alert)
        return alert
    return None


async def run_source(source_id: int, client: httpx.AsyncClient | None = None,
                     dispatch: bool = True) -> RunResult:
    lock = _locks.setdefault(source_id, asyncio.Lock())
    if lock.locked():
        return RunResult(ok=False, error="Controllo già in corso")
    async with lock:
        own_client = client is None
        client = client or fetch.make_client()
        t0 = time.monotonic()
        res = RunResult()
        alert: Alert | None = None
        db = SessionLocal()
        try:
            src = db.get(Source, source_id)
            if src is None:
                return RunResult(ok=False, error="Fonte inesistente")
            baseline = not src.baseline_done
            prev_items = {
                i.url: i for i in db.scalars(select(Item).where(Item.source_id == src.id))
            }
            try:
                snaps = await _snapshots(client, src, prev_items, include_archive=baseline)
                versions: list[Version] = []
                for snap, archived in snaps:
                    prev = prev_items.get(snap.url)
                    download = src.track_attachments and not archived and src.kind != "exams"
                    atts = await _attachments(client, snap, prev, download)
                    v = apply_snapshot(db, src, snap, atts, prev, baseline)
                    if v is not None:
                        versions.append(v)
                        if prev is None:
                            prev_items[snap.url] = v.item
                src.baseline_done = True
                src.last_ok_at = utcnow()
                src.last_error = None
                if src.consecutive_failures >= FAILURES_BEFORE_ALERT:
                    for a in db.scalars(select(Alert).where(Alert.source_id == src.id, Alert.resolved.is_(False))):
                        a.resolved = True
                src.consecutive_failures = 0
                src.last_item_count = len(snaps)
                res.items = len(snaps)
                res.new = sum(v.kind == "new" and not v.baseline for v in versions)
                res.modified = sum(v.kind == "modified" and not v.baseline for v in versions)
            except Exception as e:  # network, parse, anything: count it and move on
                log.warning("source %s failed: %s", src.slug, e)
                db.rollback()
                src = db.get(Source, source_id)
                alert = _record_failure(db, src, str(e) or e.__class__.__name__)
                res.ok, res.error = False, str(e)
                versions = []
            src.last_run_at = utcnow()
            db.commit()
            res.version_ids = [v.id for v in versions if not v.baseline]
        finally:
            db.close()
            if own_client:
                await client.aclose()
        res.seconds = round(time.monotonic() - t0, 1)

        if dispatch:
            from ..notify import dispatcher

            if res.version_ids:
                await dispatcher.dispatch_versions(res.version_ids)
            if alert is not None:
                await dispatcher.notify_admins(f"⚠️ Open Unifi: {alert.message}")
        return res


async def preview(parser: str, url: str, config: dict[str, Any]) -> dict[str, Any]:
    """Dry run for the admin form: parse without saving or downloading files."""
    cfg = selectors(parser, config)
    async with fetch.make_client() as client:
        if parser == "esse3_appelli":
            from . import esse3

            sessions = await esse3.fetch_sessions(client, cfg)
            return {"kind": "exams", "count": len(sessions), "entries": [
                {"url": s.url, "title": s.title, "summary": s.summary,
                 "published_on": s.published_on.isoformat() if s.published_on else None}
                for s in sessions[:30]]}
        html = await fetch.get_html(client, url, retries=0)
        if parser == "page":
            snap = parse_content(html, url, cfg)
            return {"kind": "page", "title": snap.title, "text": snap.content_text[:4000],
                    "attachments": snap.attachment_links[:50]}
        entries = parse_list(html, url, cfg)
        detail = None
        if entries:
            snap = parse_content(await fetch.get_html(client, entries[0].url, retries=0), entries[0].url, cfg)
            detail = {"title": snap.title, "text": snap.content_text[:3000],
                      "attachments": snap.attachment_links[:30]}
        return {
            "kind": "news",
            "entries": [
                {"url": e.url, "title": e.title, "summary": e.summary,
                 "published_on": e.published_on.isoformat() if e.published_on else None}
                for e in entries[:30]
            ],
            "detail": detail,
        }
