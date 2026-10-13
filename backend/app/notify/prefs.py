"""Subscriber preferences: validation, matching and delivery timing.

prefs = {
  "sources": null | [source ids]   # null = every source
  "keywords": [str]                # also notify when any of these appears anywhere
  "notify_new": bool, "notify_modified": bool,
  "announcements": bool,
  "quiet": null | {"start": "23:00", "end": "07:00"},
  "digest": null | "18:00"         # one summary a day instead of instant
}
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo

from ..config import settings
from ..text import fold

DEFAULT_PREFS: dict[str, Any] = {
    "sources": None,
    "keywords": [],
    "notify_new": True,
    "notify_modified": True,
    "announcements": True,
    "quiet": None,
    "digest": None,
}

MAX_KEYWORDS = 25
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def _time(v: Any) -> str | None:
    return v if isinstance(v, str) and TIME_RE.match(v) else None


def clean(raw: dict[str, Any] | None, valid_sources: set[int]) -> dict[str, Any]:
    raw = raw or {}
    out = dict(DEFAULT_PREFS)
    src = raw.get("sources")
    if isinstance(src, list):
        out["sources"] = sorted({int(s) for s in src if str(s).isdigit() and int(s) in valid_sources})
    kws = raw.get("keywords") or []
    if isinstance(kws, list):
        seen: list[str] = []
        for k in kws:
            k = re.sub(r"\s+", " ", str(k)).strip()[:60]
            if len(k) >= 2 and fold(k) not in map(fold, seen):
                seen.append(k)
        out["keywords"] = seen[:MAX_KEYWORDS]
    for key in ("notify_new", "notify_modified", "announcements"):
        if key in raw:
            out[key] = bool(raw[key])
    q = raw.get("quiet")
    if isinstance(q, dict) and _time(q.get("start")) and _time(q.get("end")) and q["start"] != q["end"]:
        out["quiet"] = {"start": q["start"], "end": q["end"]}
    out["digest"] = _time(raw.get("digest"))
    return out


def merged(prefs: dict[str, Any] | None) -> dict[str, Any]:
    return {**DEFAULT_PREFS, **(prefs or {})}


def keyword_hits(prefs: dict[str, Any], haystack: str) -> list[str]:
    h = fold(haystack)
    return [k for k in prefs.get("keywords") or [] if fold(k) in h]


def matches(prefs: dict[str, Any], kind: str, source_id: int, haystack: str) -> bool:
    p = merged(prefs)
    if kind == "new" and not p["notify_new"]:
        return False
    if kind == "modified" and not p["notify_modified"]:
        return False
    if p["sources"] is None or source_id in p["sources"]:
        return True
    return bool(keyword_hits(p, haystack))


def _hm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def in_quiet(prefs: dict[str, Any], now_local: dt.datetime) -> bool:
    q = merged(prefs)["quiet"]
    if not q:
        return False
    start, end, t = _hm(q["start"]), _hm(q["end"]), now_local.time()
    return start <= t < end if start < end else (t >= start or t < end)


def hold(prefs: dict[str, Any], now_local: dt.datetime) -> bool:
    """Should a notification be queued instead of sent right now?"""
    p = merged(prefs)
    return bool(p["digest"]) or in_quiet(p, now_local)


def flush_cutoff(prefs: dict[str, Any], now_local: dt.datetime) -> dt.datetime | None:
    """Queued notifications created before the returned local time may be sent
    now; None means keep holding everything."""
    p = merged(prefs)
    if p["digest"]:
        today = dt.datetime.combine(now_local.date(), _hm(p["digest"]), tzinfo=now_local.tzinfo)
        return today if now_local >= today else None
    if in_quiet(p, now_local):
        return None
    return now_local
