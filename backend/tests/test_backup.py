import datetime as dt
import sqlite3

from app import backup
from app.config import settings


def test_backup_and_retention(tmp_path, monkeypatch):
    from app.db import init_engine

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    init_engine(settings.db_path)
    for i in range(5):
        backup.run(dt.date(2026, 10, 1) + dt.timedelta(days=i), keep=3)
    names = [p.name for p in backup.backups()]
    assert names == ["openunifi-2026-10-03.db", "openunifi-2026-10-04.db", "openunifi-2026-10-05.db"]
    tables = sqlite3.connect(backup.backups()[-1]).execute("select name from sqlite_master").fetchall()
    assert ("sources",) in tables


def test_backup_due(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "backup_hour", 4)
    assert not backup.due(dt.datetime(2026, 10, 13, 3, 59))
    assert backup.due(dt.datetime(2026, 10, 13, 4, 0))
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "openunifi-2026-10-13.db").write_bytes(b"x")
    assert not backup.due(dt.datetime(2026, 10, 13, 12, 0))
