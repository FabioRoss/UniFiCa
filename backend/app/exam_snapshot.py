"""Copy exam sessions between installations as a JSON snapshot.

For when the server cannot read ESSE3 itself (its IP gets a Cloudflare
challenge): sessions fetched elsewhere are exported to a file and imported
here. An import never notifies anyone, and the Appelli page shows the date
the snapshot was taken until a real check succeeds.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings_store
from .models import Alert, Item, Source, utcnow
from .scraper.engine import apply_snapshot
from .scraper.parsers import Snapshot

FORMAT = 1
# Source.config flag: this source is fed by snapshots, the scheduler skips it
SNAPSHOT_ONLY = "snapshot_only"


def snapshot_key(source_id: int) -> str:
    return f"exam_snapshot:{source_id}"


def export(db: Session, slug: str) -> dict[str, Any]:
    src = db.scalar(select(Source).where(Source.slug == slug))
    if src is None:
        raise SystemExit(f"Fonte '{slug}' inesistente")
    items = list(db.scalars(select(Item).where(Item.source_id == src.id).order_by(Item.published_on)))
    if not items:
        raise SystemExit(f"Nessun appello salvato per '{slug}'")
    fetched = max(i.checked_at for i in items)
    return {
        "format": FORMAT,
        "source": slug,
        "fetched_at": fetched.isoformat(timespec="seconds") + "Z",
        "sessions": [
            {"url": i.url, "title": i.title, "summary": i.summary,
             "published_on": i.published_on.isoformat() if i.published_on else None,
             "content_text": i.content_text, "meta": i.meta or {}}
            for i in items
        ],
    }


async def fetch(slug: str = "medicina-appelli") -> dict[str, Any]:
    """Read ESSE3 directly (no database) into the export format. Used by the
    scheduled GitHub Action when the server itself cannot reach ESSE3."""
    from .scraper import esse3, fetch as http
    from .seed import EXAM_SOURCES

    cfg = EXAM_SOURCES[slug]
    async with http.make_client() as client:
        sessions = await esse3.fetch_sessions(client, cfg)
    if not sessions:
        raise SystemExit("ESSE3 ha risposto senza appelli: snapshot non scritto")
    return {
        "format": FORMAT,
        "source": slug,
        "fetched_at": utcnow().isoformat(timespec="seconds") + "Z",
        "sessions": [
            {"url": s.url, "title": s.title, "summary": s.summary,
             "published_on": s.published_on.isoformat() if s.published_on else None,
             "content_text": s.content_text, "meta": s.meta}
            for s in sessions
        ],
    }


def _parse_utc(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def import_(db: Session, data: dict[str, Any], slug: str | None = None,
            sync: bool = False) -> dict[str, Any]:
    """Load a snapshot.

    sync=False (one-off import): everything is stored as already seen, nobody
    is notified. sync=True (the daily feed from the GitHub Action): behaves
    like a real check of the board. Differences from what is stored are
    notified, the source counts as checked at the snapshot's time, and the
    server stops trying to reach ESSE3 itself for this source.
    """
    if data.get("format") != FORMAT or not isinstance(data.get("sessions"), list):
        raise SystemExit("File non valido: atteso un export di 'python -m app.cli export-exams'")
    slug = slug or data["source"]
    src = db.scalar(select(Source).where(Source.slug == slug))
    if src is None or src.kind != "exams":
        raise SystemExit(f"Fonte appelli '{slug}' inesistente su questo server")
    result: dict[str, Any] = {"sessions": len(data["sessions"]), "added": 0, "changed": 0,
                              "skipped": False, "version_ids": []}
    stored = snapshot_at(db, src.id)
    if sync and stored and _parse_utc(data["fetched_at"]) <= _parse_utc(stored):
        result["skipped"] = True  # already have this snapshot (or a newer one)
        return result

    baseline = not (sync and src.baseline_done)
    prev = {i.url: i for i in db.scalars(select(Item).where(Item.source_id == src.id))}
    versions = []
    for s in data["sessions"]:
        snap = Snapshot(
            url=s["url"], title=s["title"], content_text=s["content_text"], summary=s.get("summary", ""),
            published_on=dt.date.fromisoformat(s["published_on"]) if s.get("published_on") else None,
            meta=s.get("meta") or {},
        )
        v = apply_snapshot(db, src, snap, [], prev.get(snap.url), baseline=baseline)
        if v is not None:
            versions.append(v)
            if v.kind == "new":
                result["added"] += 1
                prev[snap.url] = v.item
            else:
                result["changed"] += 1
    # From now on later snapshots (or a real ESSE3 check) compare against
    # this data and notify only what changed.
    src.baseline_done = True
    if sync:
        src.last_ok_at = _parse_utc(data["fetched_at"])
        src.last_run_at = utcnow()
        src.last_item_count = len(data["sessions"])
        src.last_error = None
        src.consecutive_failures = 0
        for a in db.scalars(select(Alert).where(Alert.source_id == src.id, Alert.resolved.is_(False))):
            a.resolved = True
        src.config = {**(src.config or {}), SNAPSHOT_ONLY: True}
    db.commit()
    settings_store.put(db, snapshot_key(src.id), data["fetched_at"])
    result["version_ids"] = [v.id for v in versions if not v.baseline]
    return result


def set_direct(db: Session, slug: str) -> None:
    """Go back to reading ESSE3 from the server itself."""
    src = db.scalar(select(Source).where(Source.slug == slug))
    if src is None:
        raise SystemExit(f"Fonte '{slug}' inesistente")
    src.config = {k: v for k, v in (src.config or {}).items() if k != SNAPSHOT_ONLY}
    db.commit()


def snapshot_at(db: Session, source_id: int) -> str | None:
    return settings_store.get(db, snapshot_key(source_id))

