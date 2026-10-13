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
from .models import Item, Source
from .scraper.engine import apply_snapshot
from .scraper.parsers import Snapshot

FORMAT = 1


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


def import_(db: Session, data: dict[str, Any], slug: str | None = None) -> dict[str, int]:
    if data.get("format") != FORMAT or not isinstance(data.get("sessions"), list):
        raise SystemExit("File non valido: atteso un export di 'python -m app.cli export-exams'")
    slug = slug or data["source"]
    src = db.scalar(select(Source).where(Source.slug == slug))
    if src is None or src.kind != "exams":
        raise SystemExit(f"Fonte appelli '{slug}' inesistente su questo server")
    prev = {i.url: i for i in db.scalars(select(Item).where(Item.source_id == src.id))}
    added = changed = 0
    for s in data["sessions"]:
        snap = Snapshot(
            url=s["url"], title=s["title"], content_text=s["content_text"], summary=s.get("summary", ""),
            published_on=dt.date.fromisoformat(s["published_on"]) if s.get("published_on") else None,
            meta=s.get("meta") or {},
        )
        # baseline=True: imported data is never notified and stays out of the feed
        v = apply_snapshot(db, src, snap, [], prev.get(snap.url), baseline=True)
        if v is not None:
            if v.kind == "new":
                added += 1
                prev[snap.url] = v.item
            else:
                changed += 1
    # From now on a real ESSE3 check compares against this data and notifies
    # what changed since the snapshot (new sessions, moved dates).
    src.baseline_done = True
    db.commit()
    settings_store.put(db, snapshot_key(src.id), data["fetched_at"])
    return {"sessions": len(data["sessions"]), "added": added, "changed": changed}


def snapshot_at(db: Session, source_id: int) -> str | None:
    return settings_store.get(db, snapshot_key(source_id))

