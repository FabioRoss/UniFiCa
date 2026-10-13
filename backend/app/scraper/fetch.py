"""HTTP fetching: polite, browser-like, with conditional GETs for attachments."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger("openunifi.fetch")
logging.getLogger("pypdf").setLevel(logging.ERROR)  # malformed-PDF chatter

PDF_MAX_PAGES = 60
PDF_MAX_CHARS = 150_000


class FetchError(Exception):
    pass


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": settings.user_agent,
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
        },
        follow_redirects=True,
        timeout=httpx.Timeout(40.0, connect=15.0),
    )


async def get_html(client: httpx.AsyncClient, url: str, retries: int = 2) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = await client.get(url)
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code} per {url}")
            return r.text
        except (httpx.HTTPError, FetchError) as e:  # resets happen on the unifi hosts
            last = e
            if attempt < retries:
                await asyncio.sleep(3 * (attempt + 1))
    raise FetchError(str(last) or f"Errore di rete per {url}")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    from ..text import normalize_text

    try:
        reader = PdfReader(io.BytesIO(data))
        out = []
        for page in reader.pages[:PDF_MAX_PAGES]:
            out.append(page.extract_text() or "")
            if sum(map(len, out)) > PDF_MAX_CHARS:
                break
        return normalize_text("\n".join(out))[:PDF_MAX_CHARS]
    except Exception as e:  # malformed PDFs are common; the hash still works
        log.info("pdf text extraction failed: %s", e)
        return ""


async def fetch_attachment(
    client: httpx.AsyncClient, link: dict[str, str], prev: dict[str, Any] | None
) -> dict[str, Any]:
    """Return the attachment record {url, name, file, hash, etag, last_modified,
    size, text}. Uses the previous ETag/Last-Modified so unchanged files are
    not downloaded again. On failure keeps the previous hash (never reports a
    change because the file server hiccuped)."""
    rec: dict[str, Any] = {"url": link["url"], "name": link["name"], "file": link.get("file", "")}
    headers = {}
    if prev:
        if prev.get("etag"):
            # Apache's mod_deflate appends "-gzip" to ETags and then never
            # matches them on If-None-Match: send the original ETag.
            headers["If-None-Match"] = re.sub(r'-(gzip|br|deflate)"$', '"', prev["etag"])
        if prev.get("last_modified"):
            headers["If-Modified-Since"] = prev["last_modified"]
    limit = settings.max_attachment_mb * 1024 * 1024
    try:
        async with client.stream("GET", link["url"], headers=headers) as r:
            if r.status_code == 304 and prev:
                return {**prev, **rec}
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code}")
            h = hashlib.sha256()
            buf = bytearray()
            size = 0
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise FetchError("file troppo grande")
                h.update(chunk)
                buf.extend(chunk)
            ctype = r.headers.get("content-type", "")
            rec.update(
                hash=h.hexdigest(),
                etag=r.headers.get("etag", ""),
                last_modified=r.headers.get("last-modified", ""),
                size=size,
                type=ctype.split(";")[0],
            )
            if "pdf" in ctype or link["url"].lower().split("?")[0].endswith(".pdf"):
                rec["text"] = await asyncio.to_thread(_pdf_text, bytes(buf))
            return rec
    except Exception as e:
        log.info("attachment %s failed: %s", link["url"], e)
        if prev:
            return {**prev, **rec}
        rec["hash"] = ""
        return rec
