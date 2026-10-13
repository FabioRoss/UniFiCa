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


def test_exam_snapshot_roundtrip(tmp_path, monkeypatch):
    from sqlalchemy import select

    from app import exam_snapshot
    from app.db import SessionLocal, init_engine
    from app.models import Item, Source, Version
    from app.scraper.esse3 import parse_table
    from app.scraper.engine import apply_snapshot
    from app.seed import seed
    from conftest import fixture

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    init_engine(settings.db_path)
    db = SessionLocal()
    seed(db)
    src = db.scalar(select(Source).where(Source.slug == "medicina-appelli"))
    unique = list({s.url: s for s in parse_table(fixture("esse3_appelli.html"))}.values())[:10]
    for snap in unique:
        apply_snapshot(db, src, snap, [], None, baseline=True)
    db.commit()
    data = exam_snapshot.export(db, "medicina-appelli")
    assert len(data["sessions"]) == 10

    # a fresh install that never reached ESSE3
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "other"))
    init_engine(settings.db_path)
    db2 = SessionLocal()
    seed(db2)
    res = exam_snapshot.import_(db2, data)
    assert res == {"sessions": 10, "added": 10, "changed": 0}
    src2 = db2.scalar(select(Source).where(Source.slug == "medicina-appelli"))
    assert src2.baseline_done and src2.last_ok_at is None
    assert exam_snapshot.snapshot_at(db2, src2.id) == data["fetched_at"]
    assert db2.query(Item).count() == 10
    assert all(v.baseline and v.dispatched for v in db2.scalars(select(Version)))  # never notified
    assert exam_snapshot.import_(db2, data)["added"] == 0  # idempotent
