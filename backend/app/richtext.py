"""Safe, simplified HTML of a page's content area, for display.

The output is built from scratch, not filtered: only the tags below are ever
written, text is always escaped, and the only attributes are absolute
http(s)/mailto/tel hrefs and numeric colspan/rowspan. The PWA can therefore
render it as HTML, keeping the tables and the links (files linked from the
text they belong to) that the plain text used for change detection loses.

Display only: change detection and diffs keep using the plain text, so a new
rendering never counts as a modification.
"""
from __future__ import annotations

import html
import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import Comment, NavigableString, Tag

DROP = {
    "script", "style", "noscript", "template", "head", "title", "meta", "link", "nav",
    "form", "input", "select", "option", "button", "textarea", "label",
    "iframe", "object", "embed", "svg", "math", "canvas", "img", "picture", "video", "audio", "map",
}
RENAME = {
    "b": "strong", "i": "em", "h1": "h2", "h5": "h4", "h6": "h4",
    "section": "div", "article": "div", "header": "div", "footer": "div", "aside": "div",
    "main": "div", "figure": "div", "figcaption": "p", "center": "div", "dl": "div", "dt": "p", "dd": "p",
}
INLINE = {"strong", "em", "u", "s", "sub", "sup", "code"}
BLOCK = {"p", "div", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "pre",
         "table", "thead", "tbody", "tfoot", "tr", "th", "td"}
# Blocks dropped when they hold no text (cells stay: they keep the grid)
DROP_EMPTY = {"p", "div", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "pre"} | INLINE

FILE_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|odp|rtf|zip|rar|7z|csv|txt)$", re.I)
WS = re.compile(r"[ \t\r\n\f\v\xa0​]+")
MAX_LEN = 400_000


def _has_text(el: Tag) -> bool:
    return bool(WS.sub("", el.get_text()))


def _href(raw: str, base_url: str) -> str | None:
    raw = raw.strip()
    if raw.lower().startswith(("mailto:", "tel:")):
        return raw if len(raw) < 300 else None
    url = urljoin(base_url, raw)
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    if url.split("#")[0] == base_url.split("#")[0]:
        return None  # in-page anchors go nowhere outside the page
    return url


def _span(v: object) -> int | None:
    try:
        n = int(str(v).strip())
    except ValueError:
        return None
    return n if 1 < n <= 50 else None


def _header_row(table: Tag) -> Tag | None:
    """First row when it is a header the CMS wrote as bold <td>s."""
    if table.find("th"):
        return None
    row = table.find("tr")
    if row is None:
        return None
    cells = row.find_all(["td"], recursive=False)
    if len(cells) < 2:
        return None
    for c in cells:
        text = WS.sub("", c.get_text())
        if not text:
            continue
        bold = "".join(WS.sub("", b.get_text()) for b in c.find_all(["strong", "b"]))
        if bold != text:
            return None
    return row


def to_html(node: Tag | None, base_url: str) -> str:
    if node is None:
        return ""
    cell = [0]  # depth of table cells around the current element
    headers: set[int] = set()
    for t in node.find_all("table"):
        row = _header_row(t)
        if row is not None:
            headers.add(id(row))

    def inner(el: Tag, in_pre: bool, in_link: bool, head: bool) -> str:
        out = []
        for child in el.children:
            if isinstance(child, Comment) or child.__class__.__name__ in ("Doctype", "ProcessingInstruction", "CData"):
                continue
            if isinstance(child, NavigableString):
                s = str(child)
                if not in_pre:
                    s = WS.sub(" ", s)
                out.append(html.escape(s, quote=False))
            elif isinstance(child, Tag):
                out.append(emit(child, in_pre, in_link, head))
        return "".join(out)

    def emit(el: Tag, in_pre: bool, in_link: bool, head: bool) -> str:
        name = (el.name or "").lower()
        if name in DROP:
            return ""
        name = RENAME.get(name, name)
        if name == "br":
            return "<br>"
        if name == "hr":
            return "<hr>"
        if name == "tr" and head is False and id(el) in headers:
            head = True
        if name == "td" and head:
            name = "th"
        if name == "a":
            href = _href(el.get("href", ""), base_url) if not in_link else None
            body = inner(el, in_pre, True, head)
            if href is None or not WS.sub("", body):
                return body
            attrs = f' href="{html.escape(href)}"'
            if href.startswith("http"):
                attrs += ' target="_blank" rel="noopener noreferrer"'
                m = FILE_RE.search(unquote(urlparse(href).path))
                if m:
                    attrs += f' data-file="{m[1].lower()}"'
            # Spaces at the edges go outside, so the underline stops at the words
            lead = " " if body[:1] == " " else ""
            trail = " " if body[-1:] == " " else ""
            return f"{lead}<a{attrs}>{body.strip(' ')}</a>{trail}"
        if name not in INLINE and name not in BLOCK:
            return inner(el, in_pre, in_link, head)  # span, font, unknown: keep the text only
        if name in DROP_EMPTY and not _has_text(el):
            return ""
        if name == "tr" and not _has_text(el):
            return ""
        if name == "p" and cell[0]:
            # Paragraphs inside a cell are just lines
            return inner(el, in_pre, in_link, head) + "<br>"
        if name in ("td", "th"):
            cell[0] += 1
        try:
            body = inner(el, in_pre or name == "pre", in_link, head)
        finally:
            if name in ("td", "th"):
                cell[0] -= 1
        if name == "table":
            return f'<div class="table-wrap"><table>{body}</table></div>'
        attrs = ""
        if name in ("td", "th"):
            for a in ("colspan", "rowspan"):
                n = _span(el.get(a))
                if n:
                    attrs += f' {a}="{n}"'
        return f"<{name}{attrs}>{body}</{name}>"

    out = inner(node, False, False, False)
    # Runs of breaks left by removed blocks; spaces next to block edges
    out = re.sub(r"(?:<br>\s*){3,}", "<br><br>", out)
    out = re.sub(r"\s*(<(?:/?(?:p|div|h[234]|ul|ol|li|blockquote|table|thead|tbody|tfoot|tr|th|td)\b[^>]*|hr|br)>)\s*",
                 r"\1", out)
    # Breaks at the edges of a block add nothing
    out = re.sub(r"(?:<br>)+(</(?:p|li|td|th|h[234]|div|blockquote)>)", r"\1", out)
    out = re.sub(r"(<(?:p|li|td|th|h[234]|div|blockquote)(?: [^>]*)?>)(?:<br>)+", r"\1", out)
    out = re.sub(r"<(p|li|h[234]|div)></\1>", "", out)
    out = out.strip()
    return out if len(out) <= MAX_LEN else ""
