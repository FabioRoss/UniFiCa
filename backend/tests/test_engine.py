from app.models import Source
from app.scraper.engine import apply_snapshot
from app.scraper.parsers import Snapshot
from app.text import change_summary, line_diff


def _src(db):
    s = Source(slug="t", name="Test", kind="news", parser="unifi_news", url="https://x/")
    db.add(s)
    db.commit()
    return s


def test_new_then_unchanged_then_modified(db):
    src = _src(db)
    snap = Snapshot(url="https://x/a", title="Avviso", content_text="riga uno\nriga due")
    v1 = apply_snapshot(db, src, snap, [], None, baseline=False)
    db.commit()
    assert v1.kind == "new" and v1.number == 1
    item = v1.item

    same = Snapshot(url="https://x/a", title="Avviso", content_text="riga uno\n  riga   due ")
    assert apply_snapshot(db, src, same, [], item, baseline=False) is None  # whitespace only

    changed = Snapshot(url="https://x/a", title="Avviso", content_text="riga uno\nriga tre")
    v2 = apply_snapshot(db, src, changed, [], item, baseline=False)
    db.commit()
    assert v2.kind == "modified" and v2.number == 2
    assert v2.change_summary.startswith("Testo modificato")


def test_filling_missing_attachment_hash_is_not_a_change(db):
    src = _src(db)
    snap = Snapshot(url="https://x/b", title="T", content_text="t")
    att0 = [{"url": "https://x/f.pdf", "name": "f", "hash": ""}]
    v = apply_snapshot(db, src, snap, att0, None, baseline=True)
    db.commit()
    att1 = [{"url": "https://x/f.pdf", "name": "f", "hash": "abc"}]
    assert apply_snapshot(db, src, snap, att1, v.item, baseline=False) is None
    att2 = [{"url": "https://x/f.pdf", "name": "f", "hash": "def"}]
    v2 = apply_snapshot(db, src, snap, att2, v.item, baseline=False)
    assert v2 is not None and v2.change_summary == "Allegati: 1 aggiornato"


def test_line_diff_word_level():
    rows = line_diff("a\nla lezione è alle 9\nb", "a\nla lezione è alle 11\nb")
    change = [r for r in rows if r["op"] == "change"][0]
    assert {"op": "del", "text": "9"} in change["parts"] and {"op": "add", "text": "11"} in change["parts"]


def test_exam_change_summary():
    a = {"title": "X", "content_text": "Insegnamento: X\nData: 05/11/2026 ore 08:30", "attachments": []}
    b = {"title": "X", "content_text": "Insegnamento: X\nData: 07/11/2026 ore 08:30", "attachments": []}
    assert change_summary(a, b) == "Data: 05/11/2026 ore 08:30 → 07/11/2026 ore 08:30"


def test_page_baseline_moves_to_site_date(db):
    import datetime as dt

    src = Source(slug="p", name="Pagina", kind="page", parser="page", url="https://x/p")
    db.add(src)
    db.commit()
    v = apply_snapshot(db, src, Snapshot(url="https://x/p", title="Orario", content_text="a"), [], None, baseline=True)
    db.commit()
    assert v.item.published_on is None  # recorded before the date was read
    same = Snapshot(url="https://x/p", title="Orario", content_text="a", published_on=dt.date(2026, 10, 5))
    assert apply_snapshot(db, src, same, [], v.item, baseline=False) is None  # not a change
    db.commit()
    assert v.item.published_on == dt.date(2026, 10, 5)
    assert v.created_at.date() == dt.date(2026, 10, 5)


def test_new_rendering_is_not_a_change(db):
    # Items stored before richtext.py gain the HTML silently on the next check
    src = _src(db)
    v = apply_snapshot(db, src, Snapshot(url="https://x/p", title="ADE", content_text="N° ADE\nTitolo"), [], None,
                       baseline=True)
    item = v.item
    assert not item.meta
    snap = Snapshot(url="https://x/p", title="ADE", content_text="N° ADE\nTitolo",
                    meta={"html": "<div class=\"table-wrap\"><table><tr><th>N° ADE</th><th>Titolo</th></tr></table></div>"})
    assert apply_snapshot(db, src, snap, [], item, baseline=False) is None
    assert item.meta["html"].startswith('<div class="table-wrap">')
    assert item.version_count == 1
