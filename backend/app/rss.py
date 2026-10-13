"""RSS 2.0 feeds: everything, or one source."""
from __future__ import annotations

from email.utils import format_datetime
from xml.sax.saxutils import escape

import datetime as dt

from .config import settings


def _rfc822(t: dt.datetime) -> str:
    return format_datetime(t.replace(tzinfo=dt.timezone.utc))


def build(title: str, link: str, description: str, entries: list[dict]) -> str:
    """entries: [{title, link, guid, description, date (naive UTC), category}]"""
    base = settings.base_url
    items = []
    for e in entries:
        items.append(
            "<item>"
            f"<title>{escape(e['title'])}</title>"
            f"<link>{escape(e['link'])}</link>"
            f"<guid isPermaLink=\"false\">{escape(e['guid'])}</guid>"
            f"<pubDate>{_rfc822(e['date'])}</pubDate>"
            f"<category>{escape(e.get('category', ''))}</category>"
            f"<description>{escape(e['description'])}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{escape(title)}</title><link>{escape(base + link)}</link>"
        f"<description>{escape(description)}</description><language>it-it</language>"
        f'<atom:link href="{escape(base)}/rss.xml" rel="self" type="application/rss+xml"/>'
        + "".join(items)
        + "</channel></rss>"
    )
