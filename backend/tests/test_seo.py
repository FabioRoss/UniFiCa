import datetime as dt

from test_api import _add_item, client  # noqa: F401  (fixture)

from app.config import settings

INDEX = ('<!doctype html><html lang="it"><head><meta charset="UTF-8" /><title>Open Unifi</title>\n'
         '<meta name="description" content="x" />\n</head><body><div id="root"></div></body></html>')


def _setup(client, tmp_path, monkeypatch):  # noqa: F811
    from app import main

    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    monkeypatch.setattr(main, "DIST", dist)
    monkeypatch.setattr(settings, "public_url", "https://openunifi.it")


def test_item_page_has_tags_preview_and_content(client, tmp_path, monkeypatch):  # noqa: F811
    _setup(client, tmp_path, monkeypatch)
    item_id = _add_item("Iscrizioni aperte fino al 30 ottobre.\nInfo in segreteria <b>studenti</b>.")
    r = client.get(f"/n/{item_id}?v=1")
    assert r.status_code == 200
    html = r.text
    assert html.count("<title>") == 1 and "<title>Avviso esami · Open Unifi</title>" in html
    assert html.count('name="description"') == 1
    assert 'content="Iscrizioni aperte fino al 30 ottobre. Info in segreteria &lt;b&gt;studenti&lt;/b&gt;."' in html
    assert f'<link rel="canonical" href="https://openunifi.it/n/{item_id}">' in html  # no ?v=
    assert '<meta property="og:type" content="article">' in html
    assert f'content="https://openunifi.it/og/n{item_id}.png?v=' in html
    assert '"@type": "Article"' in html and '"BreadcrumbList"' in html
    # Readable without JavaScript, escaped
    assert "<h1>Avviso esami</h1>" in html and "<p>Info in segreteria &lt;b&gt;studenti&lt;/b&gt;.</p>" in html

    img = client.get(f"/og/n{item_id}.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/og/n999999.png").status_code == 404


def test_status_codes_and_noindex(client, tmp_path, monkeypatch):  # noqa: F811
    _setup(client, tmp_path, monkeypatch)
    for path in ("/", "/esami", "/link", "/info", "/notifiche"):
        r = client.get(path)
        assert r.status_code == 200 and "index, follow" in r.text, path
        assert f'<link rel="canonical" href="https://openunifi.it{path}">' in r.text
    for path, code in (("/n/999999", 404), ("/qualcosa", 404), ("/admin", 200), ("/notifiche?t=segreto", 200)):
        r = client.get(path)
        assert r.status_code == code and '"noindex, nofollow"' in r.text and "canonical" not in r.text, path
    home = client.get("/").text
    assert '"SearchAction"' in home and 'https://openunifi.it/?q={search_term_string}' in home


def test_robots_and_sitemap(client, tmp_path, monkeypatch):  # noqa: F811
    _setup(client, tmp_path, monkeypatch)
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Item, Source

    item_id = _add_item()
    db = SessionLocal()
    exams = db.scalar(select(Source).where(Source.kind == "exams"))
    today = dt.date.today()
    for n, day in ((1, today - dt.timedelta(days=3)), (2, today + dt.timedelta(days=10))):
        db.add(Item(source_id=exams.id, url=f"https://e/{n}", title=f"ESAME {n}", published_on=day,
                    content_text="x", version_count=1))
    db.commit()
    past, future = (db.scalar(select(Item.id).where(Item.url == f"https://e/{n}")) for n in (1, 2))
    db.close()

    robots = client.get("/robots.txt").text
    assert "Disallow: /admin" in robots and "Sitemap: https://openunifi.it/sitemap.xml" in robots
    assert "/api" not in robots  # the app needs the API when Google renders it
    xml = client.get("/sitemap.xml").text
    assert "<loc>https://openunifi.it/</loc>" in xml and f"<loc>https://openunifi.it/n/{item_id}</loc>" in xml
    assert f"/n/{future}<" in xml and f"/n/{past}<" not in xml  # past exam sessions left out


def test_title_case():
    from app.seo import title_case

    assert title_case("MEDICINA LEGALE E MEDICINA DEL LAVORO (C.I.)") == "Medicina Legale e Medicina del Lavoro (C.I.)"
    assert title_case("PATOLOGIA II") == "Patologia II"
