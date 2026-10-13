import asyncio
import datetime as dt

from app.models import Pending, Source, Subscriber
from app.notify import dispatcher, webpush
from app.scraper.engine import apply_snapshot
from app.scraper.parsers import Snapshot


def _setup(db, n_versions):
    src = Source(slug="s", name="Fonte", kind="news", parser="unifi_news", url="https://x/")
    db.add(src)
    db.commit()
    ids = []
    for i in range(n_versions):
        v = apply_snapshot(db, src, Snapshot(url=f"https://x/{i}", title=f"Avviso {i}", content_text="testo"),
                           [], None, baseline=False)
        db.commit()
        ids.append(v.id)
    return src, ids


def _sub(db, token, prefs):
    s = Subscriber(channel="push", endpoint=f"https://push/{token}", keys={"p256dh": "k", "auth": "a"},
                   token=token * 8, prefs=prefs)
    db.add(s)
    db.commit()
    return s


def test_dispatch_groups_and_queues(db, monkeypatch):
    sent = []

    async def fake_send(endpoint, keys, payload, vapid, urgency="normal"):
        sent.append((endpoint, payload))
        return webpush.OK

    monkeypatch.setattr(webpush, "send", fake_send)
    src, ids = _setup(db, 5)
    _sub(db, "a", {})                                         # everything, instant
    _sub(db, "b", {"sources": [], "keywords": ["avviso 3"]})   # one keyword match
    _sub(db, "c", {"quiet": {"start": "00:00", "end": "23:59"}})  # quiet almost all day
    asyncio.run(dispatcher.dispatch_versions(ids))

    by_ep = {}
    for ep, p in sent:
        by_ep.setdefault(ep, []).append(p)
    if dt.datetime.now(dispatcher.P.tz()).strftime("%H:%M") < "23:59":
        assert "https://push/c" not in by_ep
        assert db.query(Pending).count() == 5
    assert len(by_ep["https://push/a"]) == 1 and by_ep["https://push/a"][0]["tag"] == "digest"
    assert [p["body"] for p in by_ep["https://push/b"]] == ["Avviso 3"]


def test_gone_subscription_is_deleted(db, monkeypatch):
    async def gone(*a, **k):
        return webpush.GONE

    monkeypatch.setattr(webpush, "send", gone)
    _, ids = _setup(db, 1)
    _sub(db, "z", {})
    asyncio.run(dispatcher.dispatch_versions(ids))
    db.expire_all()
    assert db.query(Subscriber).count() == 0
