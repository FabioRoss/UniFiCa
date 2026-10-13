"""Turn fetched HTML into list entries and content snapshots.

Every parser is driven by CSS selectors. The "unifi_news" preset matches the
CMS shared by the *.unifi.it course sites (NEWSpro module), so adding another
course's news usually needs only its URL. Any key can be overridden per
source from the admin panel (Source.config).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import Tag

from .. import richtext
from ..text import html_to_text, normalize_line, soup

PRESETS: dict[str, dict[str, str]] = {
    "unifi_news": {
        "item": ".media--news",
        "link": "a.media__link",
        "title": ".media__body h2",
        "summary": ".media__body p.line-clamp",
        "date": ".media__body p.right-text",
        "content": "#intro_contenuto .content-right",
        "content_title": "h1",
        "remove": "h1, .social, script, style",
    },
    # Generic news list: the admin fills every selector.
    "css_list": {
        "item": "article",
        "link": "a",
        "title": "h2, h3",
        "summary": "p",
        "date": "time, .date",
        "content": "main, article, #content, body",
        "content_title": "h1",
        "remove": "script, style, nav, footer",
    },
    # Whole page watched for changes. Default content area fits *.unifi.it.
    "page": {
        "content": "#intro_contenuto .content-right, main, #content, body",
        "content_title": "h1",
        "remove": "#intro_titolo, .social, script, style, nav",
    },
    # ESSE3 public exam board (scraper/esse3.py). Config: fac_id, cds_ids
    # (comma separated internal ids, pick them in the admin form), months_ahead.
    "esse3_appelli": {
        "fac_id": "",
        "cds_ids": "",
        "months_ahead": "6",
    },
}

PARSERS = list(PRESETS)

DOC_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|odp|rtf|zip|rar|7z|csv|txt)$", re.I)

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


@dataclass
class Entry:
    """One row of a news list."""

    url: str
    title: str
    summary: str = ""
    published_on: dt.date | None = None


@dataclass
class Snapshot:
    """The content of one article or watched page."""

    url: str
    title: str
    content_text: str
    summary: str = ""
    published_on: dt.date | None = None
    attachment_links: list[dict[str, str]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def selectors(parser: str, overrides: dict[str, Any] | None) -> dict[str, str]:
    cfg = dict(PRESETS.get(parser, PRESETS["page"]))
    for k, v in (overrides or {}).items():
        if isinstance(v, (str, int)) and str(v).strip():
            cfg[k] = str(v).strip()
    return cfg


def parse_date(text: str) -> dt.date | None:
    if not text:
        return None
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text)
    try:
        if m:
            return dt.date(int(m[3]), int(m[2]), int(m[1]))
        m = re.search(r"\b(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b", text)
        if m and m[2].lower() in MESI:
            return dt.date(int(m[3]), MESI[m[2].lower()], int(m[1]))
        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if m:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return None


def _first(node: Tag, selector: str) -> Tag | None:
    try:
        return node.select_one(selector)
    except Exception:  # invalid selector typed in the admin panel
        return None


def _text(node: Tag | None) -> str:
    return normalize_line(node.get_text(" ", strip=True)) if node is not None else ""


def parse_list(html: str, base_url: str, cfg: dict[str, str]) -> list[Entry]:
    doc = soup(html)
    entries: list[Entry] = []
    seen: set[str] = set()
    try:
        nodes = doc.select(cfg["item"])
    except Exception:
        return []
    for node in nodes:
        a = node if node.name == "a" and node.get("href") else _first(node, cfg["link"])
        if a is None or not a.get("href"):
            continue
        url = urljoin(base_url, a["href"].strip())
        if url in seen:
            continue
        seen.add(url)
        title = _text(_first(node, cfg["title"])) or normalize_line(a.get("title", "")) or _text(a)
        entries.append(
            Entry(
                url=url,
                title=title,
                summary=_text(_first(node, cfg["summary"])),
                published_on=parse_date(_text(_first(node, cfg["date"]))),
            )
        )
    return entries


def _content_node(doc: Tag, cfg: dict[str, str]) -> Tag | None:
    # A comma list means "first selector that matches", not "all of them".
    for sel in cfg["content"].split(","):
        node = _first(doc, sel.strip())
        if node is not None:
            return node
    return None


def parse_content(html: str, url: str, cfg: dict[str, str]) -> Snapshot:
    doc = soup(html)
    node = _content_node(doc, cfg)
    title = ""
    if node is not None:
        title = _text(_first(node, cfg.get("content_title", "h1")))
    if not title:
        title = _text(_first(doc, "h1")) or _text(doc.title)

    attachments: list[dict[str, str]] = []
    links: list[dict[str, str]] = []
    if node is not None:
        seen: set[str] = set()
        for a in node.select("a[href]"):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            abs_url = urljoin(url, href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            # Share buttons and similar sit in removed blocks; skip them anyway
            if any(h in urlparse(abs_url).netloc for h in ("twitter.com", "facebook.com", "x.com")):
                continue
            name = normalize_line(a.get_text(" ", strip=True))
            path = urlparse(abs_url).path
            if DOC_RE.search(path):
                fname = unquote(path.rsplit("/", 1)[-1])
                attachments.append({"url": abs_url, "name": name or fname, "file": fname})
            elif "identity.unifi.it" not in abs_url:  # SSO links carry per-request ids
                links.append({"url": abs_url, "text": name or abs_url})
        for sel in cfg.get("remove", "").split(","):
            sel = sel.strip()
            if not sel:
                continue
            try:
                for bad in node.select(sel):
                    bad.decompose()
            except Exception:
                continue

    text = html_to_text(node)
    rich = richtext.to_html(node, url)
    date_node = None
    if node is not None:
        date_node = node.select_one(".right-text")
    published = parse_date(_text(date_node)) if date_node is not None else None
    if published is None:
        # Pages of the unifi CMS end with "ULTIMO AGGIORNAMENTO dd.mm.yyyy",
        # outside the content area (so it never counts as a change)
        upd = _first(doc, ".update-at")
        published = parse_date(_text(upd)) if upd is not None else None
    return Snapshot(
        url=url,
        title=title,
        content_text=text,
        published_on=published,
        attachment_links=attachments,
        links=links,
        meta={"html": rich} if rich else {},
    )
