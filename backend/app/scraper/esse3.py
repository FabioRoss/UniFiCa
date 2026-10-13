"""Exam sessions from ESSE3's public "Bacheca Appelli" (no login needed).

studenti.unifi.it/ListaAppelliOfferta.do is a server-side form: a GET opens
a session (cookie), then a POST with school (fac_id), course (cds_id) and a
date range returns a table of sessions. Each row links to
DettaglioTurnoOfferta.do?ad_id=..&app_id=..&cds_id=..&app_log_id=.., which
gives a stable identity, so a moved date shows up as a modification.

The "#Iscr./#Posti" column changes all the time and is deliberately left
out of the tracked text.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from ..text import normalize_line, soup
from .fetch import FetchError
from .parsers import Snapshot, parse_date

BASE = "https://studenti.unifi.it/"
LIST_URL = BASE + "ListaAppelliOfferta.do"
DETAIL_URL = BASE + "DettaglioTurnoOfferta.do"
DEFAULT_MONTHS = 6


def _form(fac_id: str, cds_id: str, start: dt.date, end: dt.date, **extra: str) -> dict[str, str]:
    return {
        "data_da": start.strftime("%d/%m/%Y"), "data_a": end.strftime("%d/%m/%Y"),
        "fac_id": fac_id, "cds_id": cds_id, "ad_id": "", "docente_id": "",
        "TIPO_FORM": "1", "form_id_formRicercaCds": "formRicercaCds", **extra,
    }


def _cell(td: Any) -> str:
    return normalize_line(td.get_text(" ", strip=True)) if td is not None else ""


def parse_table(html: str) -> list[Snapshot]:
    doc = soup(html)
    table = doc.select_one("#tabellaAppelli")
    if table is None:
        if "Nessun" in doc.get_text() or "nessun" in doc.get_text():
            return []
        raise FetchError("Tabella appelli non trovata: la pagina ESSE3 potrebbe essere cambiata")
    out: list[Snapshot] = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        link = tds[3].find("a", href=True)
        if link is None:
            continue
        q = parse_qs(urlparse(link["href"]).query)
        key = {k: q.get(k, [""])[0] for k in ("ad_id", "app_id", "cds_id", "app_log_id")}
        url = f"{DETAIL_URL}?{urlencode(key)}"

        activity = _cell(tds[0])
        m = re.match(r"\[([^\]]+)\]\s*(.*)", activity)
        code, name = (m[1], m[2]) if m else ("", activity)
        appello = _cell(tds[1])
        reg = _cell(tds[2])
        reg_dates = re.findall(r"\d{2}/\d{2}/\d{4}", reg)
        when = _cell(tds[3])
        date = parse_date(when)
        tm = re.search(r"\b(\d{1,2}[:.]\d{2})\b", when)
        time = tm[1].replace(".", ":") if tm else ""
        tipo = _cell(tds[4])
        docenti = [normalize_line(x) for x in tds[5].get_text("\n").split("\n") if normalize_line(x)]

        # ESSE3 cuts the session name at 40 chars; a prefix of the course name adds nothing
        if appello and name.upper().startswith(appello.upper().rstrip(" (")):
            appello = ""
        title = f"{name}: {appello}" if appello else name
        reg_txt = f"iscrizioni {reg_dates[0]} - {reg_dates[1]}" if len(reg_dates) == 2 else ""
        summary = " · ".join(x for x in (
            f"{date.strftime('%d/%m/%Y') if date else when}" + (f" ore {time}" if time else ""),
            tipo, reg_txt) if x)
        lines = [
            # (course code left out on purpose: shared sessions list several, in no fixed order)
            f"Insegnamento: {name}",
            f"Prova: {appello}" if appello else "",
            f"Data: {date.strftime('%d/%m/%Y') if date else when}" + (f" ore {time}" if time else ""),
            f"Iscrizioni: dal {reg_dates[0]} al {reg_dates[1]}" if len(reg_dates) == 2 else "",
            f"Tipo: {tipo}" if tipo else "",
            f"Docenti: {', '.join(docenti)}" if docenti else "",
        ]
        out.append(Snapshot(
            url=url, title=title, summary=summary, published_on=date,
            content_text="\n".join(x for x in lines if x),
            meta={
                "code": code, "name": name, "appello": appello, "date": date.isoformat() if date else None,
                "time": time, "type": tipo, "teachers": docenti,
                "reg_from": _iso(reg_dates[0]) if reg_dates else None,
                "reg_to": _iso(reg_dates[1]) if len(reg_dates) > 1 else None,
            },
        ))
    return out


def _iso(d: str) -> str | None:
    p = parse_date(d)
    return p.isoformat() if p else None


async def _open_session(client: httpx.AsyncClient) -> str:
    r = await client.get(LIST_URL)
    if r.status_code >= 400:
        raise FetchError(f"HTTP {r.status_code} per {LIST_URL}")
    return r.text


async def fetch_sessions(client: httpx.AsyncClient, config: dict[str, Any]) -> list[Snapshot]:
    fac_id = str(config.get("fac_id") or "").strip()
    cds_ids = [c.strip() for c in str(config.get("cds_ids") or "").split(",") if c.strip()]
    if not fac_id or not cds_ids:
        raise FetchError("Configura fac_id e cds_ids (scuola e corsi ESSE3)")
    months = int(config.get("months_ahead") or DEFAULT_MONTHS)
    start = dt.date.today()
    end = start + dt.timedelta(days=31 * months)
    await _open_session(client)
    seen: dict[str, Snapshot] = {}
    for cds in cds_ids:
        r = await client.post(LIST_URL, data=_form(fac_id, cds, start, end, btnSubmit="Avvia Ricerca"))
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code} da ESSE3")
        for s in parse_table(r.text):
            # The same session can be listed under several courses: keep one
            key = re.sub(r"cds_id=\d*&?", "", s.url)
            if key in seen:
                # Same session listed under another course code (old/new curriculum)
                codes = seen[key].meta.setdefault("codes", [seen[key].meta.get("code")])
                if s.meta.get("code") not in codes:
                    codes.append(s.meta.get("code"))
            else:
                seen[key] = s
    return sorted(seen.values(), key=lambda s: (s.published_on or dt.date.max, s.title))


def _options(html: str, select_id: str) -> list[dict[str, str]]:
    sel = soup(html).select_one(f"#{select_id}")
    if sel is None:
        return []
    return [{"value": o["value"], "label": normalize_line(o.get_text())}
            for o in sel.select("option") if o.get("value")]


async def options(client: httpx.AsyncClient, fac_id: str | None) -> dict[str, list[dict[str, str]]]:
    """Schools, and the courses of one school, for the admin form."""
    html = await _open_session(client)
    out = {"schools": _options(html, "selectionFacolta"), "courses": []}
    if fac_id:
        today = dt.date.today()
        r = await client.post(LIST_URL, data=_form(fac_id, "", today, today + dt.timedelta(days=7),
                                                   **{"_fw_refresh-form.x": "selectionFacolta"}))
        out["courses"] = _options(r.text, "selectionCds")
    return out
