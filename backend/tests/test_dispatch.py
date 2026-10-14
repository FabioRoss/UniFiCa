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


def test_telegram_links_are_inline_buttons(monkeypatch):
    from app.config import settings
    from app.notify import telegram
    from app.notify.dispatcher import telegram_digest, telegram_text

    monkeypatch.setattr(settings, "public_url", "https://openunifi.it")
    m = {"kind": "modified", "source": "ADE", "item_title": "Attività <elettive>", "change": "Testo modificato",
         "url": "/n/107?v=2", "original": "https://www.medicina.unifi.it/vp-118.html"}
    text, kb = telegram_text(m)
    assert "<a " not in text and "&lt;elettive&gt;" in text
    assert kb == [[{"text": "✏️ Vedi le modifiche", "url": "https://openunifi.it/n/107?v=2"},
                   {"text": "🌐 Sito ufficiale", "url": "https://www.medicina.unifi.it/vp-118.html"}]]

    ann = {"kind": "announcement", "item_title": "Avviso", "summary": "", "original": None, "url": "/"}
    assert telegram_text(ann)[1] is None  # no link, no keyboard

    few = [{**m, "kind": "new", "item_title": f"Appello {i}", "url": f"/n/{i}"} for i in range(1, 4)]
    text, kb = telegram_digest(few)
    assert "1. 🆕 Appello 1 <i>(ADE)</i>" in text and "<a " not in text
    assert kb[0] == [{"text": "1. Appello 1", "url": "https://openunifi.it/n/1"}]
    assert kb[-1] == [{"text": "🗞 Tutte le novità", "url": "https://openunifi.it/"}]

    many = [{**m, "item_title": f"Appello {i}", "url": f"/n/{i}"} for i in range(1, 46)]
    text, kb = telegram_digest(many)
    assert [b["text"] for b in kb[0]] == ["1", "2", "3", "4", "5"] and len(kb) == 9  # 8 rows of numbers + "tutte"
    assert sum(len(r) for r in kb) <= 100  # Telegram's limit

    # Telegram refuses non-public hosts: drop the button rather than lose the message
    monkeypatch.setattr(settings, "public_url", "http://localhost:8000")
    assert telegram.url_button("x", "/n/1") is None
    assert telegram_text(m)[1] == [[{"text": "🌐 Sito ufficiale", "url": "https://www.medicina.unifi.it/vp-118.html"}]]
