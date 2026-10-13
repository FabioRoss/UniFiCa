"""Text normalisation, content hashing and diffs.

Change detection compares *normalised* text, so whitespace shuffles, &nbsp;
and markup-only edits by the CMS never count as a modification.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "blockquote", "hr", "dd", "dt",
}


def normalize_line(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("\xa0", " ").replace("​", "")
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def normalize_text(s: str) -> str:
    lines = (normalize_line(x) for x in s.splitlines())
    return "\n".join(x for x in lines if x)


def html_to_text(node: Tag | None) -> str:
    """Readable text with one block per line; list items get a bullet."""
    if node is None:
        return ""
    parts: list[str] = []

    def walk(el: Tag) -> None:
        for child in el.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in ("Comment", "Doctype"):
                    continue
                parts.append(str(child))
            elif isinstance(child, Tag):
                name = child.name.lower()
                if name in ("script", "style", "noscript"):
                    continue
                if name == "br":
                    parts.append("\n")
                    continue
                block = name in BLOCK_TAGS
                if block:
                    parts.append("\n")
                if name == "li":
                    parts.append("• ")
                if name in ("td", "th"):
                    parts.append(" ")
                walk(child)
                if block:
                    parts.append("\n")

    walk(node)
    return normalize_text("".join(parts))


def fold(s: str) -> str:
    """Lowercase without accents, for keyword matching and search."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def content_hash(title: str, text: str, attachments: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update(normalize_line(title).encode())
    h.update(b"\x00")
    h.update(normalize_text(text).encode())
    for a in sorted(attachments, key=lambda a: a["url"]):
        h.update(b"\x00")
        h.update(a["url"].encode())
        h.update(b"|")
        h.update((a.get("hash") or "").encode())
    return h.hexdigest()


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ── Diffs ────────────────────────────────────────────────────────────────

def _word_diff(old: str, new: str) -> list[dict[str, str]]:
    a, b = re.findall(r"\S+|\s+", old), re.findall(r"\S+|\s+", new)
    out: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append({"op": "eq", "text": "".join(a[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "del", "text": "".join(a[i1:i2])})
            if j2 > j1:
                out.append({"op": "add", "text": "".join(b[j1:j2])})
    return out


def line_diff(old: str, new: str, context: int = 2) -> list[dict[str, Any]]:
    """Line diff for the UI. Ops: eq, add, del, change (with word-level
    parts), skip (n unchanged lines collapsed)."""
    a, b = old.splitlines(), new.splitlines()
    rows: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            rows.extend({"op": "eq", "text": x} for x in a[i1:i2])
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            for x, y in zip(a[i1:i2], b[j1:j2]):
                if difflib.SequenceMatcher(None, x, y).ratio() > 0.4:
                    rows.append({"op": "change", "parts": _word_diff(x, y)})
                else:
                    rows.append({"op": "del", "text": x})
                    rows.append({"op": "add", "text": y})
        else:
            rows.extend({"op": "del", "text": x} for x in a[i1:i2])
            rows.extend({"op": "add", "text": y} for y in b[j1:j2])

    # Collapse long unchanged stretches, keeping `context` lines around edits.
    keep = [r["op"] != "eq" for r in rows]
    near = [False] * len(rows)
    for i, k in enumerate(keep):
        if k:
            for j in range(max(0, i - context), min(len(rows), i + context + 1)):
                near[j] = True
    out: list[dict[str, Any]] = []
    skipped = 0
    for r, n in zip(rows, near):
        if n:
            if skipped:
                out.append({"op": "skip", "count": skipped})
                skipped = 0
            out.append(r)
        else:
            skipped += 1
    if skipped:
        out.append({"op": "skip", "count": skipped})
    return out


def diff_stats(old: str, new: str) -> tuple[int, int]:
    added = removed = 0
    sm = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines(), autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            removed += i2 - i1
            added += j2 - j1
    return added, removed


def attachment_changes(old: list[dict], new: list[dict]) -> dict[str, list[dict]]:
    o = {a["url"]: a for a in old}
    n = {a["url"]: a for a in new}
    return {
        "added": [n[u] for u in n if u not in o],
        "removed": [o[u] for u in o if u not in n],
        "changed": [
            n[u] for u in n
            if u in o and o[u].get("hash") and n[u].get("hash") and o[u]["hash"] != n[u]["hash"]
        ],
    }


def _labelled_changes(old: str, new: str) -> list[str] | None:
    """For "Label: value" texts (exam sessions) describe each changed field,
    e.g. "data: 05/11/2026 ore 08:30 → 07/11/2026 ore 09:00". None when the
    text is not in that format."""
    def fields(s: str) -> dict[str, str] | None:
        out = {}
        for line in s.splitlines():
            label, sep, value = line.partition(": ")
            if not sep or len(label) > 20:
                return None
            out[label] = value
        return out or None

    a, b = fields(old), fields(new)
    if a is None or b is None:
        return None
    out = []
    for label in dict.fromkeys([*a, *b]):
        if a.get(label) != b.get(label):
            out.append(f"{label.lower()}: {a.get(label, '-')} → {b.get(label, '-')}")
    return out


def change_summary(prev: dict[str, Any], cur: dict[str, Any]) -> str:
    """Short Italian description of what changed between two snapshots."""
    bits: list[str] = []
    if normalize_line(prev["title"]) != normalize_line(cur["title"]):
        bits.append("titolo modificato")
    labelled = _labelled_changes(prev["content_text"], cur["content_text"])
    added, removed = diff_stats(prev["content_text"], cur["content_text"])
    if labelled is not None:
        bits.extend(labelled)
    elif added or removed:
        bits.append(f"testo modificato (+{added} / -{removed} righe)")
    ch = attachment_changes(prev["attachments"], cur["attachments"])
    att = []
    if ch["added"]:
        att.append(f"{len(ch['added'])} nuov{'o' if len(ch['added']) == 1 else 'i'}")
    if ch["changed"]:
        att.append(f"{len(ch['changed'])} aggiornat{'o' if len(ch['changed']) == 1 else 'i'}")
    if ch["removed"]:
        att.append(f"{len(ch['removed'])} rimoss{'o' if len(ch['removed']) == 1 else 'i'}")
    if att:
        bits.append("allegati: " + ", ".join(att))
    s = ", ".join(bits) or "contenuto aggiornato"
    return s[0].upper() + s[1:]
