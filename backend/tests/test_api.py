import pytest
from fastapi.testclient import TestClient

from app.config import settings

H = {"x-openunifi": "1"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "admin_user", "Fabio.Test@Example.com")
    monkeypatch.setattr(settings, "admin_password", "segreta")
    monkeypatch.setattr(settings, "frontend_dist", str(tmp_path / "dist"))
    from app import security
    from app.main import app

    security._failures.clear()
    security._all_failures.clear()
    with TestClient(app) as c:
        yield c


def _add_item(text="Prima versione"):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Item, Source
    from app.scraper.engine import apply_snapshot
    from app.scraper.parsers import Snapshot

    db = SessionLocal()
    src = db.scalar(select(Source).where(Source.slug == "medicina-news"))
    prev = db.scalar(select(Item).where(Item.url == "https://x/a"))
    v = apply_snapshot(db, src, Snapshot(url="https://x/a", title="Avviso esami", content_text=text),
                       [], prev, baseline=False)
    db.commit()
    item_id = v.item.id
    db.close()
    return item_id


def test_public_endpoints(client):
    cfg = client.get("/api/config").json()
    assert len(cfg["vapid_public_key"]) > 80
    assert any(s["slug"] == "medicina-news" for s in client.get("/api/sources").json())
    assert len(client.get("/api/links").json()) >= 3

    item_id = _add_item()
    _add_item("Seconda versione con una riga in più\nnuova riga")
    feed = client.get("/api/feed").json()["entries"]
    assert [e["kind"] for e in feed] == ["modified", "new"]
    assert client.get("/api/feed", params={"q": "esami"}).json()["entries"]
    assert not client.get("/api/feed", params={"q": "inesistente"}).json()["entries"]

    detail = client.get(f"/api/items/{item_id}").json()
    assert len(detail["versions"]) == 2
    diff = client.get(f"/api/items/{item_id}/versions/2/diff").json()
    assert any(r["op"] in ("add", "change") for r in diff["text"])

    rss = client.get("/rss.xml")
    assert rss.status_code == 200 and "Avviso esami" in rss.text
    assert client.get("/rss/medicina-news.xml").status_code == 200
    assert client.get("/api/exams").json()["exams"] == []


def test_watched_pages_are_in_the_feed(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Source
    from app.scraper.engine import apply_snapshot
    from app.scraper.parsers import Snapshot

    db = SessionLocal()
    src = db.scalar(select(Source).where(Source.slug == "medicina-orario-lezioni"))
    apply_snapshot(db, src, Snapshot(url=src.url, title="Orario delle lezioni", content_text="x"), [], None,
                   baseline=True)
    db.commit()
    entries = client.get("/api/feed", params={"source": src.id}).json()["entries"]
    assert [e["item"]["title"] for e in entries] == ["Orario delle lezioni"]
    db.close()


def test_push_subscription_lifecycle(client):
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "k", "auth": "a"}}
    r = client.post("/api/subscription/push", json={"subscription": sub, "platform": "ios"}).json()
    token = r["token"]
    assert r["prefs"]["sources"] is None
    r = client.put(f"/api/subscription/{token}", json={"prefs": {"sources": [1], "keywords": ["tirocinio"]}}).json()
    assert r["prefs"]["sources"] == [1] and r["prefs"]["keywords"] == ["tirocinio"]
    # same endpoint again keeps the same token
    assert client.post("/api/subscription/push", json={"subscription": sub}).json()["token"] == token
    assert client.delete(f"/api/subscription/{token}").json()["ok"]
    assert client.get(f"/api/subscription/{token}").status_code == 404


def test_admin(client):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.post("/api/admin/login", json={"username": "fabio.test@example.com", "password": "no"}, headers=H).status_code == 401
    assert client.post("/api/admin/login", json={"username": "fabio.test@example.com", "password": "segreta"}).status_code == 403
    assert client.post("/api/admin/login", json={"username": "fabio.test@example.com", "password": "segreta"}, headers=H).status_code == 200

    stats = client.get("/api/admin/stats").json()
    assert stats["subscribers"]["total"] == 0 and len(stats["sources"]) >= 2

    g = client.post("/api/admin/link-groups", json={"name": "Prova"}, headers=H).json()
    link = client.post("/api/admin/links", json={"group_id": g["id"], "title": "Mensa", "url": "https://dsu.it"},
                       headers=H).json()
    assert client.post("/api/admin/links", json={"group_id": g["id"], "title": "X", "url": "javascript:alert(1)"},
                       headers=H).status_code == 422
    assert client.delete(f"/api/admin/links/{link['id']}").status_code == 403  # missing header
    assert client.delete(f"/api/admin/links/{link['id']}", headers=H).json()["ok"]

    s = client.post("/api/admin/sources", headers=H, json={
        "name": "Nuova fonte", "kind": "page", "parser": "page", "url": "https://www.unifi.it/x"}).json()
    assert s["slug"] == "nuova-fonte" and not s["baseline_done"]
    assert client.post("/api/admin/sources", headers=H, json={
        "name": "Sbagliata", "kind": "page", "parser": "unifi_news", "url": "https://a.it"}).status_code == 422

    site = client.put("/api/admin/settings", headers=H, json={"intro": "Ciao"}).json()
    assert site["intro"] == "Ciao"
    assert client.get("/api/config").json()["site"]["intro"] == "Ciao"


def test_password_hash():
    from app.security import hash_password, verify_password

    h = hash_password("abc")
    assert "$" not in h and verify_password("abc", h) and not verify_password("abd", h)


def _login(client, password="segreta", xff=None, user="fabio.test@example.com"):
    headers = dict(H)
    if xff:
        headers["X-Forwarded-For"] = xff
    return client.post("/api/admin/login", json={"username": user, "password": password}, headers=headers)


def test_every_admin_route_requires_login(client):
    from fastapi.routing import APIRoute

    from app.main import app

    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/admin"):
            continue
        if route.path in ("/api/admin/login", "/api/admin/logout"):
            continue
        path = route.path.replace("{", "").replace("}", "")  # params become literal text
        path = "/".join("1" if seg.endswith("_id") else seg for seg in path.split("/"))
        for method in route.methods:
            r = client.request(method, path, headers=H, json={})
            assert r.status_code == 401, (method, route.path, r.status_code)
            checked += 1
    assert checked > 25


def test_spoofed_forwarded_for_does_not_bypass_throttle(client):
    # Caddy appends the real peer last; the client controls the first entries
    for i in range(8):
        assert _login(client, "sbagliata", xff=f"10.0.0.{i}, 203.0.113.7").status_code == 401
    assert _login(client, "segreta", xff="10.9.9.9, 203.0.113.7").status_code == 429
    assert _login(client, "segreta", xff="198.51.100.1").status_code == 200  # other people unaffected


def test_password_change_logs_out_sessions(client, monkeypatch):
    assert _login(client).status_code == 200
    assert client.get("/api/admin/me").status_code == 200
    monkeypatch.setattr(settings, "admin_password", "una-nuova-password")
    assert client.get("/api/admin/me").status_code == 401


def test_placeholder_password_keeps_panel_locked(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "CHANGE_ME")
    assert _login(client, "CHANGE_ME").status_code == 503
    monkeypatch.setattr(settings, "admin_password", "")
    assert _login(client, "").status_code == 503


def test_forged_cookie_rejected(client):
    client.cookies.set("openunifi_admin", "eyJ1IjoiYWRtaW4ifQ.forged.signature", path="/api")
    assert client.get("/api/admin/stats").status_code == 401


def test_login_needs_the_right_user_too(client):
    r = _login(client, user="admin")  # right password, wrong user
    assert r.status_code == 401 and r.json()["detail"] == "Credenziali non valide"
    assert _login(client, user="  FABIO.TEST@example.COM ").status_code == 200  # emails are case-insensitive


def test_guessable_user_keeps_panel_locked(client, monkeypatch):
    for user in ("", "admin", "Root"):
        monkeypatch.setattr(settings, "admin_user", user)
        assert _login(client, user=user).status_code == 503


def test_user_change_logs_out_sessions(client, monkeypatch):
    assert _login(client).status_code == 200
    monkeypatch.setattr(settings, "admin_user", "altra@example.com")
    assert client.get("/api/admin/me").status_code == 401


def test_direct_esse3_checks_can_be_switched_off(client, monkeypatch):
    # The daily snapshot keeps feeding the source; the server never calls ESSE3 itself
    import asyncio

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Alert, Source
    from app.scraper import engine

    assert _login(client).status_code == 200
    db = SessionLocal()
    src = db.scalar(select(Source).where(Source.slug == "medicina-appelli"))
    src.last_error, src.consecutive_failures = "HTTP 403", 4
    db.add(Alert(source_id=src.id, message="403"))
    db.commit()
    body = client.get("/api/admin/sources").json()
    row = next(s for s in body if s["slug"] == "medicina-appelli")
    row["config"]["snapshot_only"] = True
    payload = {k: row[k] for k in ("name", "slug", "category", "kind", "parser", "url", "archive_url", "config",
                                    "interval_minutes", "enabled", "track_attachments", "position")}
    out = client.put(f"/api/admin/sources/{row['id']}", json=payload, headers=H).json()
    assert out["config"]["snapshot_only"] is True and out["enabled"]
    assert out["last_error"] is None and out["consecutive_failures"] == 0  # the old 403 is gone

    async def boom(*a, **k):
        raise AssertionError("ESSE3 must not be contacted")

    monkeypatch.setattr(engine, "_snapshots", boom)
    res = asyncio.run(engine.run_source(row["id"]))  # "check now" and `cli run`
    assert not res.ok and "disattivato" in res.error
    db.expire_all()
    assert db.get(Source, row["id"]).consecutive_failures == 0
    assert not db.scalars(select(Alert).where(Alert.resolved.is_(False))).all()
    db.close()
