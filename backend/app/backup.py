"""Daily database backups, taken by the scheduler (no cron needed).

Uses SQLite's online backup API, so it is consistent even while the app is
writing. Files land in <data_dir>/backups, which docker-compose mounts from
./backups on the host; the newest `keep` are kept.
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from pathlib import Path

from .config import settings

log = logging.getLogger("openunifi.backup")

PREFIX = "openunifi-"


def backup_dir() -> Path:
    return Path(settings.data_dir) / "backups"


def backups() -> list[Path]:
    d = backup_dir()
    return sorted(d.glob(f"{PREFIX}*.db")) if d.exists() else []


def run(day: dt.date | None = None, keep: int | None = None) -> Path:
    day = day or dt.date.today()
    keep = settings.backup_keep if keep is None else keep
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{PREFIX}{day.isoformat()}.db"
    tmp = target.with_suffix(".tmp")
    src = sqlite3.connect(settings.db_path)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    tmp.replace(target)  # never leave a half-written file under the final name
    for old in backups()[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
    log.info("backup written: %s", target.name)
    return target


def due(now_local: dt.datetime) -> bool:
    """Today's backup is missing and it is past the backup hour."""
    if now_local.hour < settings.backup_hour:
        return False
    return not (backup_dir() / f"{PREFIX}{now_local.date().isoformat()}.db").exists()
