import datetime as dt

from conftest import fixture

from app.scraper.esse3 import parse_table
from app.scraper.parsers import parse_content, parse_date, parse_list, selectors

BASE = "https://www.medicina.unifi.it/"


def test_news_list():
    entries = parse_list(fixture("news.html"), BASE + "news.html", selectors("unifi_news", {}))
    assert len(entries) == 6
    first = entries[0]
    assert first.url == BASE + "art-1324-tpv-vi-a-a-2026-2027.html"
    assert first.title == "TPV VI a.a.2026/2027"
    assert first.published_on == dt.date(2026, 10, 9)
    assert "TIROMED" in first.summary


def test_news_archive_has_more_items():
    entries = parse_list(fixture("news_archive.html"), BASE, selectors("unifi_news", {}))
    assert len(entries) >= 40
    assert all(e.url.startswith(BASE) for e in entries)


def test_article_content():
    snap = parse_content(fixture("article_esami.html"), BASE + "art-1322-iscrizione-esami.html",
                         selectors("unifi_news", {}))
    assert snap.title == "Iscrizione esami"
    assert "appelli anticipati di novembre" in snap.content_text
    assert "Condividi" not in snap.content_text  # share box removed
    assert not snap.content_text.startswith("Iscrizione esami")  # h1 removed
    assert snap.published_on == dt.date(2026, 10, 8)


def test_article_links():
    snap = parse_content(fixture("article_tpv.html"), BASE + "x.html", selectors("unifi_news", {}))
    assert {"url": BASE + "vp-307-vi-anno.html", "text": "Consulta la pagina dedicata (URL)"} in snap.links
    assert not any("twitter" in l["url"] for l in snap.links)


def test_page_monitor_attachments():
    snap = parse_content(fixture("page_lauree.html"), BASE + "vp-114.html", selectors("page", {}))
    assert snap.title == "Calendario esami di laurea"
    pdfs = [a for a in snap.attachment_links if a["file"].endswith(".pdf")]
    assert len(pdfs) >= 10
    assert all(a["url"].startswith("https://") for a in pdfs)
    assert "Calendario sedute" in snap.content_text
    assert "ULTIMO AGGIORNAMENTO" not in snap.content_text


def test_bad_selector_does_not_crash():
    assert parse_list(fixture("news.html"), BASE, selectors("css_list", {"item": "!!nope"})) == []


def test_parse_date():
    assert parse_date(" 9.10.2026") == dt.date(2026, 10, 9)
    assert parse_date("09 Ottobre 2026") == dt.date(2026, 10, 9)
    assert parse_date("31.02.2026") is None
    assert parse_date("") is None


def test_esse3_table():
    rows = parse_table(fixture("esse3_appelli.html"))
    assert len(rows) > 50
    r = next(x for x in rows if "ANATOMIA PATOLOGICA" in x.title)
    assert "DettaglioTurnoOfferta.do?ad_id=" in r.url and "jsessionid" not in r.url
    assert r.meta["time"] == "08:30" and r.meta["reg_from"] == "2026-10-15"
    assert r.published_on == dt.date(2026, 11, 5)
    assert "#Iscr" not in r.content_text and "\n0" not in r.content_text  # live count not tracked


def test_page_monitor_reads_site_update_date():
    snap = parse_content(fixture("page_lauree.html"), BASE + "vp-114.html", selectors("page", {}))
    assert snap.published_on == dt.date(2026, 10, 6)


def test_page_keeps_tables_and_inline_file_links():
    url = BASE + "vp-118-attivita-didattiche-elettive.html"
    snap = parse_content(fixture("page_ade.html"), url, selectors("page", {}))
    html = snap.meta["html"]
    # The bold first row becomes a header, cells stay on one row
    assert "<tr><th><strong>N° ADE</strong></th><th><strong>Titolo</strong></th>" in html
    assert "<td>1/2025</td><td><a href=\"" + BASE + "upload/sub/Ade%20I%20semestre_2025_2026/" in html
    assert html.count('<div class="table-wrap"><table>') == 2
    # PDFs are linked from their own text, absolute, marked as files
    assert ('<a href="' + BASE + 'upload/sub/2020/Avvisi/Libretto%20ADE_2020_2021.pdf" target="_blank" '
            'rel="noopener noreferrer" data-file="pdf">Libretto ADE</a>') in html
    assert "Attività didattiche elettive (A.D.E.)" not in html  # title removed like in the text
    # The plain text (hash and diffs) is unchanged by the rendering
    assert "N° ADE\nTitolo\nAnno di corso\nCFU" in snap.content_text


def test_rich_html_is_sanitised():
    from app.richtext import to_html
    from app.text import soup

    evil = soup("""<div id="c">
      <p onclick="x()" style="color:red" class="k">Ciao <b>mondo</b> &lt;script&gt;</p>
      <script>alert(1)</script><style>p{}</style><iframe src="https://e.vil"></iframe>
      <img src="x" onerror="alert(1)">
      <a href="javascript:alert(1)">js</a> <a href="data:text/html,x">data</a>
      <a href="//e.vil/a.pdf">rel</a> <a href="mailto:a@b.it">mail</a> <a href="#top">anchor</a>
      <a href='https://x.it/"onmouseover="a'>q</a>
      <table><tr><td colspan="2 onmouseover=x" rowspan="3">a</td></tr></table>
      <svg><a href="https://e.vil">s</a></svg><form><input value="x"></form>
      <p>&nbsp;</p><span title="t">span</span>
    </div>""").select_one("#c")
    out = to_html(evil, "https://www.medicina.unifi.it/p.html")
    for bad in ("onclick", "style=", "class=\"k\"", "<script", "alert", "<iframe", "<img", "onerror",
                "javascript:", "data:", "<svg", "<form", "<input", "title=", "#top", "onmouseover=x"):
        assert bad not in out, bad
    assert "<p>Ciao <strong>mondo</strong> &lt;script&gt;</p>" in out
    assert 'href="https://e.vil/a.pdf"' in out and 'data-file="pdf"' in out
    assert '<a href="mailto:a@b.it">mail</a>' in out
    assert 'href="https://x.it/&quot;onmouseover=&quot;a"' in out
    assert '<td rowspan="3">a</td>' in out
    assert "<p></p>" not in out and "span" in out
