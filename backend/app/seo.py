"""What search engines and link previews see.

The PWA renders in the browser, but crawlers and social previews (Telegram,
WhatsApp, Facebook, X, LinkedIn...) mostly read the raw HTML. For every page
the server therefore writes into index.html:
- title, description, canonical URL, Open Graph / Twitter tags with a
  generated preview image (og.py) and JSON-LD structured data;
- a plain HTML version of the content inside #root, which React replaces
  as soon as the app starts (same content, so it is not cloaking).
Plus robots.txt and sitemap.xml.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import og, settings_store
from .config import settings
from .models import Item, LinkGroup, Source, utcnow

e = html.escape
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
SMALL = {"e", "ed", "di", "del", "della", "dello", "dei", "degli", "delle", "dell", "da", "dal", "dalla", "in",
         "nel", "nella", "a", "al", "alla", "ai", "agli", "alle", "con", "per", "tra", "fra", "il", "lo", "la",
         "i", "gli", "le", "o", "su", "sul"}
WS = re.compile(r"\s+")


def fmt_date(d: dt.date | dt.datetime | None) -> str:
    return f"{d.day} {MESI[d.month - 1]} {d.year}" if d else ""


def title_case(s: str) -> str:
    """ESSE3 titles are all caps (same rules as titleCase in format.ts)."""
    first = True

    def word(m: re.Match[str]) -> str:
        nonlocal first
        orig = m.group(0)
        if orig != orig.upper():
            first = False
            return orig
        w = orig.lower()
        if not first and re.fullmatch(r"i{1,3}|iv|vi{0,3}|ix|x", w) or re.fullmatch(r"c\.i\.?", w):
            out = w.upper()
        elif not first and w in SMALL:
            out = w
        else:
            out = w[:1].upper() + w[1:]
        first = False
        return out

    return re.sub(r"[a-zà-ù0-9.]+", word, s, flags=re.I)


def clip(s: str, n: int = 160) -> str:
    s = WS.sub(" ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def host() -> str:
    return urlparse(settings.base_url).hostname or settings.base_url


@dataclass
class Page:
    title: str
    description: str
    path: str  # canonical
    card: tuple[str, str, str] | None = None  # preview image: title, label, footer
    card_key: str = "home"
    og_type: str = "website"
    status: int = 200
    noindex: bool = False
    body: str = ""
    meta: list[tuple[str, str]] = field(default_factory=list)  # extra og/article properties
    jsonld: list[dict[str, Any]] = field(default_factory=list)


# ── Pages ────────────────────────────────────────────────────────────────

# path: (name, preview image key, tagline on the preview image)
SECTIONS = {
    "/esami": ("Appelli d'esame", "esami", "Date, orari e iscrizioni dalla bacheca ESSE3"),
    "/notifiche": ("Notifiche", "notifiche", "Push e Telegram gratis, con i tuoi filtri"),
    "/link": ("Link utili e contatti", "link", "Segreterie, servizi online, biblioteche e contatti"),
    "/info": ("Come funziona", "info", "Quali siti controlliamo e come"),
}


def _wrap(body: str) -> str:
    return f'<div class="prerender"><main>{body}</main></div>'


def _crumbs(*items: tuple[str, str]) -> dict[str, Any]:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": n, "name": name, "item": settings.base_url + path}
        for n, (name, path) in enumerate(items, 1)]}


def _exam_sources(db: Session) -> list[Source]:
    return list(db.scalars(select(Source).where(Source.kind == "exams", Source.enabled.is_(True))))


def home(db: Session) -> Page:
    site = settings_store.site(db)
    rows = db.execute(
        select(Item, Source).join(Source, Item.source_id == Source.id)
        .where(Item.hidden.is_(False), Source.enabled.is_(True), Source.kind != "exams")
        .order_by(Item.changed_at.desc()).limit(60)
    ).all()
    lis = "".join(
        f'<li><a href="/n/{i.id}">{e(i.title)}</a> <small>{e(s.name)}'
        f'{" · " + fmt_date(i.published_on) if i.published_on else ""}</small></li>' for i, s in rows)
    body = (f"<h1>Le novità di UniFI, in un posto solo</h1><p>{e(site['intro'])}</p>"
            f"<h2>Ultimi aggiornamenti</h2><ul>{lis}</ul>")
    desc = clip(site["intro"] + " Notifiche push e Telegram gratuite, appelli d'esame e link utili.")
    return Page(
        title=f"{settings.site_name}: avvisi, modifiche e appelli di UniFI",
        description=desc, path="/", card=("Le novità di UniFI, in un posto solo", "",
                                          f"Avvisi, modifiche e appelli con notifiche · {host()}"),
        card_key="home", body=_wrap(body),
        jsonld=[{"@context": "https://schema.org", "@type": "WebSite", "name": settings.site_name,
                 "url": settings.base_url + "/", "inLanguage": "it-IT", "description": desc,
                 "potentialAction": {"@type": "SearchAction",
                                     "target": settings.base_url + "/?q={search_term_string}",
                                     "query-input": "required name=search_term_string"}}],
    )


def exams(db: Session) -> Page:
    today = dt.date.today()
    srcs = _exam_sources(db)
    names = ", ".join(dict.fromkeys(s.category or s.name for s in srcs)) or "UniFI"
    rows = db.scalars(
        select(Item).where(Item.source_id.in_([s.id for s in srcs]), Item.hidden.is_(False),
                           Item.published_on >= today).order_by(Item.published_on, Item.title).limit(400))
    lis = "".join(f'<li>{fmt_date(i.published_on)}: <a href="/n/{i.id}">{e(title_case(i.title))}</a></li>'
                  for i in rows)
    desc = clip(f"Calendario degli appelli d'esame di {names} dalla bacheca pubblica ESSE3: date, orari, "
                "iscrizioni e docenti, con avvisi quando un appello viene aggiunto o spostato.")
    body = f"<h1>Appelli d'esame</h1><p>{e(desc)}</p><ul>{lis or '<li>Nessun appello rilevato</li>'}</ul>"
    return _section("/esami", desc, body)


def links_page(db: Session) -> Page:
    groups = db.scalars(select(LinkGroup).order_by(LinkGroup.position, LinkGroup.id))
    parts = []
    for g in groups:
        lis = []
        for link in g.links:
            label = e(link.title)
            item = f'<a href="{e(link.url)}" rel="noopener">{label}</a>' if link.url.startswith("http") else label
            extra = " · ".join(e(x) for x in (link.description, link.email, link.phone, link.location) if x)
            lis.append(f"<li>{item}{' <small>' + extra + '</small>' if extra else ''}</li>")
        parts.append(f"<h2>{e(g.name)}</h2>{f'<p>{e(g.description)}</p>' if g.description else ''}<ul>{''.join(lis)}</ul>")
    desc = ("Link utili e contatti per gli studenti UniFI: segreterie, servizi online, orari, biblioteche, "
            "tutor e rappresentanti, cercabili al volo.")
    return _section("/link", desc, f"<h1>Link utili e contatti</h1><p>{e(desc)}</p>{''.join(parts)}")


def info(db: Session) -> Page:
    site = settings_store.site(db)
    srcs = db.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.position, Source.id))
    lis = "".join(f'<li><a href="{e(s.url)}" rel="noopener">{e(s.name)}</a></li>' for s in srcs)
    desc = clip(f"Come funziona {settings.site_name}: {site['intro']}")
    body = (f"<h1>Come funziona</h1><p>{e(site['intro'])}</p><h2>Siti controllati</h2><ul>{lis}</ul>"
            f"<p>{e(site['disclaimer'])}</p>")
    return _section("/info", desc, body)


def notifications(db: Session) -> Page:
    desc = ("Ricevi gratis una notifica push o un messaggio Telegram quando i siti UniFI pubblicano o "
            "modificano qualcosa: scegli fonti, parole chiave e orari di silenzio.")
    return _section("/notifiche", desc, f"<h1>Notifiche</h1><p>{e(desc)}</p>")


def _section(path: str, desc: str, body: str) -> Page:
    name, key, tagline = SECTIONS[path]
    return Page(title=f"{name} · {settings.site_name}", description=desc, path=path,
                card=(name, "", f"{tagline} · {host()}"), card_key=key,
                body=_wrap(body), jsonld=[_crumbs((settings.site_name, "/"), (name, path))])


def item_page(db: Session, item_id: int) -> Page | None:
    item = db.get(Item, item_id)
    if item is None or item.hidden or not item.source.enabled:
        return None
    src = item.source
    exam = src.kind == "exams"
    title = title_case(item.title) if exam else item.title
    if exam:
        date_label = f"Appello del {fmt_date(item.published_on)}"
    elif src.kind == "page":
        date_label = f"Aggiornata sul sito il {fmt_date(item.published_on)}"
    else:
        date_label = f"Pubblicato il {fmt_date(item.published_on)}"
    if not item.published_on:
        date_label = f"Aggiornato il {fmt_date(item.changed_at)}"
    desc = clip(item.summary or item.content_text or f"{title}: {src.name}")
    content = (item.meta or {}).get("html") or "".join(
        f"<p>{e(line)}</p>" for line in (item.content_text or "").splitlines() if line.strip())
    atts = "".join(f'<li><a href="{e(a["url"])}" rel="noopener">{e(a.get("name") or a.get("file") or a["url"])}</a></li>'
                   for a in item.attachments or [])
    back = ("Appelli", "/esami") if exam else ("Novità", "/")
    body = (f'<p><a href="{back[1]}">{back[0]}</a> · {e(src.name)}</p><article><h1>{e(title)}</h1>'
            f"<p>{e(date_label)}</p>{content}"
            f"{'<h2>Allegati</h2><ul>' + atts + '</ul>' if atts else ''}"
            f'<p><a href="{e(item.url)}" rel="noopener">Pagina originale sul sito ufficiale</a></p></article>')
    published = item.published_on.isoformat() if item.published_on else item.first_seen_at.date().isoformat()
    modified = item.changed_at.replace(tzinfo=dt.timezone.utc).isoformat(timespec="seconds")
    path = f"/n/{item.id}"
    card = (title, src.name, f"{date_label} · {host()}")
    image = image_url(f"n{item.id}", card)
    return Page(
        title=f"{title} · {settings.site_name}", description=desc, path=path, card=card,
        card_key=f"n{item.id}", og_type="article", body=_wrap(body),
        meta=[("article:published_time", published), ("article:modified_time", modified),
              ("article:section", src.name)],
        jsonld=[
            {"@context": "https://schema.org", "@type": "WebPage" if src.kind == "page" else "Article",
             "headline": clip(title, 110), "name": title, "description": desc, "inLanguage": "it-IT",
             "url": settings.base_url + path, "image": [image], "datePublished": published,
             "dateModified": modified, "isBasedOn": item.url,
             "author": {"@type": "Organization", "name": src.name, "url": src.url},
             "publisher": {"@type": "Organization", "name": settings.site_name, "url": settings.base_url + "/",
                           "logo": {"@type": "ImageObject", "url": settings.base_url + "/icons/icon-512.png"}}},
            _crumbs((settings.site_name, "/"), (back[0], back[1]), (clip(title, 60), path)),
        ],
    )


def page_for(db: Session, path: str, query: dict[str, str]) -> Page:
    path = "/" + path.strip("/")
    if path == "/":
        page = home(db)
    elif path == "/esami":
        page = exams(db)
    elif path == "/link":
        page = links_page(db)
    elif path == "/info":
        page = info(db)
    elif path == "/notifiche":
        page = notifications(db)
        page.noindex = "t" in query  # personal settings link
    elif path == "/admin" or path.startswith("/admin/"):
        page = Page(title=f"Admin · {settings.site_name}", description="", path="/admin", noindex=True)
    elif (m := re.fullmatch(r"/n/(\d+)", path)) and (found := item_page(db, int(m[1]))):
        page = found
    else:
        page = Page(title=f"Pagina non trovata · {settings.site_name}", description="", path=path,
                    status=404, noindex=True,
                    body=_wrap('<h1>Pagina non trovata</h1><p><a href="/">Torna alle novità</a></p>'))
    return page


# ── HTML ─────────────────────────────────────────────────────────────────

def image_url(key: str, card: tuple[str, str, str]) -> str:
    return f"{settings.base_url}/og/{key}.png?v={og.version(*card)}"


def head(page: Page) -> str:
    url = settings.base_url + page.path
    tags = [f"<title>{e(page.title)}</title>"]
    if page.description:
        tags.append(f'<meta name="description" content="{e(page.description)}">')
    tags.append(f'<meta name="robots" content="{"noindex, nofollow" if page.noindex else "index, follow, max-image-preview:large"}">')
    if not page.noindex:
        tags.append(f'<link rel="canonical" href="{e(url)}">')
    og_props = [("og:site_name", settings.site_name), ("og:locale", "it_IT"), ("og:type", page.og_type),
                ("og:title", page.title.removesuffix(f" · {settings.site_name}")), ("og:url", url)]
    if page.description:
        og_props.append(("og:description", page.description))
    twitter = [("twitter:card", "summary_large_image")]
    if page.card:
        img = image_url(page.card_key, page.card)
        og_props += [("og:image", img), ("og:image:type", "image/png"), ("og:image:width", str(og.W)),
                     ("og:image:height", str(og.H)), ("og:image:alt", page.card[0])]
        twitter.append(("twitter:image", img))
    og_props += page.meta
    tags += [f'<meta property="{k}" content="{e(v)}">' for k, v in og_props]
    tags += [f'<meta name="{k}" content="{e(v)}">' for k, v in twitter]
    if settings.google_site_verification:
        tags.append(f'<meta name="google-site-verification" content="{e(settings.google_site_verification)}">')
    if settings.bing_site_verification:
        tags.append(f'<meta name="msvalidate.01" content="{e(settings.bing_site_verification)}">')
    for data in page.jsonld:
        tags.append('<script type="application/ld+json">'
                    + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "\n    ".join(tags)


TITLE_RE = re.compile(r"<title>.*?</title>\s*", re.S)
DESC_RE = re.compile(r'<meta name="description"[^>]*>\s*')


def inject(index_html: str, page: Page) -> str:
    out = DESC_RE.sub("", TITLE_RE.sub("", index_html, count=1), count=1)
    out = out.replace("</head>", f"    {head(page)}\n  </head>", 1)
    if page.body:
        out = out.replace('<div id="root"></div>', f'<div id="root">{page.body}</div>', 1)
    return out


# ── Crawling ─────────────────────────────────────────────────────────────

def robots() -> str:
    return ("User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /*?t=\n\n"
            f"Sitemap: {settings.base_url}/sitemap.xml\n")


def sitemap(db: Session) -> str:
    today = dt.date.today()
    urls: list[tuple[str, str]] = []
    newest = db.scalar(select(Item.changed_at).order_by(Item.changed_at.desc()).limit(1)) or utcnow()
    for path in ("/", "/esami", "/link", "/info", "/notifiche"):
        urls.append((path, (newest if path in ("/", "/esami") else utcnow()).date().isoformat()))
    rows = db.execute(
        select(Item.id, Item.changed_at, Item.published_on, Source.kind).join(Source, Item.source_id == Source.id)
        .where(Item.hidden.is_(False), Source.enabled.is_(True)).order_by(Item.changed_at.desc()).limit(45000)
    ).all()
    for item_id, changed, published, kind in rows:
        if kind == "exams" and (published is None or published < today):
            continue  # past sessions: nothing to find there any more
        urls.append((f"/n/{item_id}", changed.date().isoformat()))
    body = "".join(f"<url><loc>{e(settings.base_url + p)}</loc><lastmod>{d}</lastmod></url>" for p, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n')


def card_for(db: Session, key: str) -> tuple[str, str, str] | None:
    """Preview image content for /og/<key>.png."""
    if key == "home":
        return home(db).card
    for path, (_, k, _) in SECTIONS.items():
        if k == key:
            return page_for(db, path, {}).card
    if m := re.fullmatch(r"n(\d+)", key):
        page = item_page(db, int(m[1]))
        return page.card if page else None
    return None
