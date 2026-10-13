"""Background loop, everything automatic (no cron needed):
- run due sources one at a time (polite to the unifi servers),
- flush held notifications (quiet hours, digests) every minute,
- take the daily database backup."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import backup
from .config import settings
from .db import SessionLocal
from .models import Source, utcnow
from .notify import dispatcher
from .scraper import engine

log = logging.getLogger("openunifi.scheduler")

TICK_SECONDS = 30


def due_sources() -> list[int]:
    now = utcnow()
    db = SessionLocal()
    try:
        out = []
        for s in db.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.position, Source.id)):
            if (s.config or {}).get("snapshot_only"):
                continue  # fed by the daily snapshot import (see exam_snapshot.py)
            interval = dt.timedelta(minutes=max(1, s.interval_minutes))
            # Back off after repeated failures (max 2h) so a broken site is not hammered
            if s.consecutive_failures:
                interval = min(interval * (2 ** min(s.consecutive_failures, 4)), dt.timedelta(hours=2))
            if s.last_run_at is None or now - s.last_run_at >= interval:
                out.append(s.id)
        return out
    finally:
        db.close()


async def run_forever() -> None:
    last_flush = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            for sid in due_sources():
                res = await engine.run_source(sid)
                log.info("source %s: %s", sid, res.as_dict())
            if loop.time() - last_flush >= 55:
                last_flush = loop.time()
                await dispatcher.flush_pending()
                if settings.backup_keep > 0 and backup.due(dt.datetime.now(ZoneInfo(settings.timezone))):
                    await asyncio.to_thread(backup.run)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)
