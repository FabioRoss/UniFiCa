import datetime as dt
from zoneinfo import ZoneInfo

from app.notify import prefs as P

ROME = ZoneInfo("Europe/Rome")


def at(h, m=0):
    return dt.datetime(2026, 10, 13, h, m, tzinfo=ROME)


def test_clean_drops_garbage():
    p = P.clean({"sources": [1, 2, 99, "x"], "keywords": ["  Tirocinio ", "tirocinio", "a"],
                 "quiet": {"start": "23:00", "end": "07:00"}, "digest": "25:00"}, {1, 2})
    assert p["sources"] == [1, 2]
    assert p["keywords"] == ["Tirocinio"]
    assert p["quiet"] == {"start": "23:00", "end": "07:00"}
    assert p["digest"] is None


def test_matching():
    p = {"sources": [1], "keywords": ["borsa di studio"]}
    assert P.matches(p, "new", 1, "qualsiasi")
    assert not P.matches(p, "new", 2, "orario lezioni")
    assert P.matches(p, "new", 2, "Bando BORSA DI STUDIO 2026")
    assert P.matches({"sources": None}, "modified", 5, "")
    assert not P.matches({"notify_modified": False}, "modified", 5, "")


def test_accent_insensitive_keywords():
    assert P.matches({"sources": [], "keywords": ["attivita"]}, "new", 3, "Attività didattiche")


def test_quiet_hours_overnight():
    p = {"quiet": {"start": "23:00", "end": "07:00"}}
    assert P.in_quiet(p, at(23, 30)) and P.in_quiet(p, at(6, 59))
    assert not P.in_quiet(p, at(7)) and not P.in_quiet(p, at(12))
    assert P.flush_cutoff(p, at(3)) is None
    assert P.flush_cutoff(p, at(8)) == at(8)


def test_digest_cutoff():
    p = {"digest": "18:00"}
    assert P.hold(p, at(9))
    assert P.flush_cutoff(p, at(17, 59)) is None
    assert P.flush_cutoff(p, at(18, 5)) == at(18)
