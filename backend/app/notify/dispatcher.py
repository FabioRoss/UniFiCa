"""Who gets what, and when.

Each new/modified version is matched against every active subscriber's
filters. Matches are sent at once, or queued (Pending) when the subscriber is
in quiet hours or wants a daily digest; `flush_pending` runs every minute and
delivers the queue as one summary message.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections import defaultdict
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import Announcement, Item, Pending, Source, Subscriber, Version, utcnow
from .. import settings_store
from . import prefs as P
from . import telegram, webpush

log = logging.getLogger("openunifi.dispatch")

PUSH_CONCURRENCY = 10
# More matches than this in one run (e.g. a whole exam session published at
# once) are sent to a subscriber as a single summary message.
GROUP_THRESHOLD = 3
TELEGRAM_DELAY = 0.05  # stay well under the 30 msg/s bot limit


# ── Message building ─────────────────────────────────────────────────────

def _haystack(item: Item, version: Version) -> str:
    names = " ".join(a.get("name", "") for a in version.attachments or [])
    return f"{item.title}\n{item.summary}\n{version.content_text}\n{names}"


def version_message(v: Version, item: Item, src: Source) -> dict[str, Any]:
    url = f"/n/{item.id}?v={v.number}"
    if v.kind == "new":
        title = f"🆕 {src.name}"
        body = item.title + (f"\n{item.summary}" if item.summary else "")
    else:
        title = f"✏️ Modificato: {src.name}"
        body = f"{item.title}\n{v.change_summary}"
    return {"title": title[:120], "body": body[:300], "url": url, "tag": f"item-{item.id}",
            "kind": v.kind, "item_title": item.title, "source": src.name,
            "original": item.url, "change": v.change_summary, "summary": item.summary}


def announcement_message(a: Announcement) -> dict[str, Any]:
    return {"title": f"📣 {a.title}"[:120], "body": a.body[:300], "url": a.url or "/",
            "tag": f"ann-{a.id}", "kind": "announcement", "item_title": a.title,
            "summary": a.body, "original": a.url}


def telegram_text(m: dict[str, Any]) -> str:
    e = telegram.esc
    base = settings.base_url
    if m["kind"] == "announcement":
        text = f"📣 <b>{e(m['item_title'])}</b>\n\n{e(m['summary'])}"
        if m.get("original"):
            link = m["original"] if m["original"].startswith("http") else base + m["original"]
            text += f"\n\n<a href=\"{e(link)}\">Apri</a>"
        return text
    head = "🆕 <b>Nuovo</b>" if m["kind"] == "new" else "✏️ <b>Modificato</b>"
    text = f"{head} · <i>{e(m['source'])}</i>\n<b>{e(m['item_title'])}</b>"
    if m["kind"] == "modified" and m.get("change"):
        text += f"\n{e(m['change'])}"
    elif m.get("summary"):
        text += f"\n{e(m['summary'][:400])}"
    text += (f"\n\n<a href=\"{base}{m['url']}\">Dettagli e modifiche</a>"
             f" | <a href=\"{e(m['original'])}\">Sito ufficiale</a>")
    return text


def digest_message(msgs: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(msgs)
    lines = [f"• {m['item_title']}" for m in msgs[:6]]
    if n > 6:
        lines.append(f"e altri {n - 6}")
    return {"title": f"Open Unifi: {n} aggiornament{'o' if n == 1 else 'i'}", "body": "\n".join(lines)[:300],
            "url": "/", "tag": "digest", "kind": "digest", "items": msgs}


def telegram_digest(msgs: list[dict[str, Any]]) -> str:
    e = telegram.esc
    base = settings.base_url
    lines = [f"🗞 <b>Riepilogo Open Unifi</b> ({len(msgs)})\n"]
    for m in msgs[:40]:
        icon = {"new": "🆕", "modified": "✏️"}.get(m["kind"], "📣")
        link = m["url"] if m["url"].startswith("http") else base + m["url"]
        lines.append(f"{icon} <a href=\"{e(link)}\">{e(m['item_title'])}</a>"
                     + (f" <i>({e(m['source'])})</i>" if m.get("source") else ""))
    return "\n".join(lines)


# ── Sending ──────────────────────────────────────────────────────────────

class Sender:
    """Sends to many subscribers with bounded concurrency and cleans up
    subscriptions the push service or Telegram reports as gone."""

    def __init__(self, db: Session):
        self.db = db
        self.vapid = settings_store.vapid_keys(db)["private"]
        self.sem = asyncio.Semaphore(PUSH_CONCURRENCY)
        self.tg: httpx.AsyncClient | None = None
        self.counts = {"push": 0, "telegram": 0}

    async def __aenter__(self) -> Sender:
        if telegram.enabled():
            self.tg = httpx.AsyncClient(timeout=20)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.tg:
            await self.tg.aclose()

    async def _one(self, sub: Subscriber, push_payload: dict[str, Any], tg_text: str,
                   urgency: str = "normal") -> str:
        if sub.channel == "push":
            async with self.sem:
                res = await webpush.send(sub.endpoint, sub.keys, push_payload, self.vapid, urgency)
        elif sub.channel == "telegram" and self.tg is not None:
            res = await telegram.send(self.tg, sub.endpoint, tg_text)
            await asyncio.sleep(TELEGRAM_DELAY)
        else:
            return "skip"
        if res == webpush.OK:
            sub.failures = 0
            sub.last_sent_at = utcnow()
            self.counts[sub.channel] += 1
        elif res == webpush.GONE:
            sub.active = False
        else:
            sub.failures += 1
            if sub.failures >= 20:  # weeks of errors: stop trying
                sub.active = False
        return res

    async def send_many(self, items: list[tuple[Subscriber, dict[str, Any], str]],
                        urgency: str = "normal") -> list[str]:
        """Results aligned with `items`."""
        results: list[str] = ["skip"] * len(items)
        push = [i for i, x in enumerate(items) if x[0].channel == "push"]
        tg = [i for i, x in enumerate(items) if x[0].channel == "telegram"]

        async def one(i: int) -> None:
            s, p, t = items[i]
            results[i] = await self._one(s, p, t, urgency)

        await asyncio.gather(*(one(i) for i in push))
        for i in tg:  # sequential: Telegram rate limits per bot
            await one(i)
        # Expired push subscriptions are removed outright (no personal data kept)
        for i in push:
            s = items[i][0]
            if not s.active and s in self.db:
                self.db.delete(s)
        return results


def _push_payload(m: dict[str, Any]) -> dict[str, Any]:
    return {k: m[k] for k in ("title", "body", "url", "tag") if k in m}


async def dispatch_versions(version_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Version, Item, Source).join(Item, Version.item_id == Item.id)
            .join(Source, Item.source_id == Source.id)
            .where(Version.id.in_(version_ids), Version.dispatched.is_(False))
            .order_by(Version.created_at)
        ).all()
        if not rows:
            return
        subs = list(db.scalars(select(Subscriber).where(Subscriber.active.is_(True))))
        now_local = dt.datetime.now(P.tz())
        msgs = {v.id: version_message(v, item, src) for v, item, src in rows}
        per_sub: dict[int, list[Version]] = defaultdict(list)
        for v, item, src in rows:
            hay = _haystack(item, v)
            for sub in subs:
                if not P.matches(sub.prefs, v.kind, src.id, hay):
                    continue
                if P.hold(sub.prefs, now_local):
                    db.add(Pending(subscriber_id=sub.id, version_id=v.id))
                else:
                    per_sub[sub.id].append(v)

        batch: list[tuple[Subscriber, dict[str, Any], str]] = []
        covered: list[list[Version]] = []
        by_id = {s.id: s for s in subs}
        for sub_id, vs in per_sub.items():
            sub = by_id[sub_id]
            if len(vs) > GROUP_THRESHOLD:
                group = [msgs[v.id] for v in vs]
                batch.append((sub, _push_payload(digest_message(group)), telegram_digest(group)))
                covered.append(vs)
            else:
                for v in vs:
                    batch.append((sub, _push_payload(msgs[v.id]), telegram_text(msgs[v.id])))
                    covered.append([v])

        async with Sender(db) as sender:
            urgency = "high" if any(v.kind == "new" for v, _, _ in rows) else "normal"
            results = await sender.send_many(batch, urgency)
            for (sub, _, _), res, vs in zip(batch, results, covered):
                if res == webpush.OK:
                    for v in vs:
                        if sub.channel == "push":
                            v.push_sent += 1
                        else:
                            v.telegram_sent += 1
            if sender.tg is not None and settings.telegram_channel:
                all_msgs = [msgs[v.id] for v, _, _ in rows]
                if len(all_msgs) > GROUP_THRESHOLD:
                    await telegram.send(sender.tg, settings.telegram_channel, telegram_digest(all_msgs))
                else:
                    for m in all_msgs:
                        await telegram.send(sender.tg, settings.telegram_channel, telegram_text(m))
        for v, _, _ in rows:
            v.dispatched = True
        db.commit()
    finally:
        db.close()


async def broadcast(announcement_id: int) -> dict[str, int]:
    db = SessionLocal()
    try:
        a = db.get(Announcement, announcement_id)
        if a is None:
            return {}
        msg = announcement_message(a)
        subs = [s for s in db.scalars(select(Subscriber).where(Subscriber.active.is_(True)))
                if P.merged(s.prefs)["announcements"]]
        now_local = dt.datetime.now(P.tz())
        batch = []
        for sub in subs:
            if P.hold(sub.prefs, now_local):
                db.add(Pending(subscriber_id=sub.id, announcement_id=a.id))
            else:
                batch.append((sub, _push_payload(msg), telegram_text(msg)))
        async with Sender(db) as sender:
            await sender.send_many(batch, "high")
            if sender.tg is not None and settings.telegram_channel:
                await telegram.send(sender.tg, settings.telegram_channel, telegram_text(msg))
            a.push_sent += sender.counts["push"]
            a.telegram_sent += sender.counts["telegram"]
        db.commit()
        return {"push": a.push_sent, "telegram": a.telegram_sent, "queued": len(subs) - len(batch)}
    finally:
        db.close()


async def flush_pending() -> int:
    """Deliver queued notifications whose hold has ended. Returns how many
    subscribers got a message."""
    db = SessionLocal()
    sent = 0
    try:
        pend = list(db.scalars(select(Pending).order_by(Pending.created_at)))
        if not pend:
            return 0
        by_sub: dict[int, list[Pending]] = defaultdict(list)
        for p in pend:
            by_sub[p.subscriber_id].append(p)
        now_local = dt.datetime.now(P.tz())
        utc = dt.timezone.utc
        out = []
        for sub_id, rows in by_sub.items():
            sub = db.get(Subscriber, sub_id)
            if sub is None or not sub.active:
                for p in rows:
                    db.delete(p)
                continue
            cutoff = P.flush_cutoff(sub.prefs, now_local)
            if cutoff is None:
                continue
            due = [p for p in rows if p.created_at.replace(tzinfo=utc) <= cutoff]
            if not due:
                continue
            msgs = []
            for p in due:
                if p.version_id:
                    v = db.get(Version, p.version_id)
                    if v is not None:
                        msgs.append(version_message(v, v.item, v.item.source))
                elif p.announcement_id:
                    a = db.get(Announcement, p.announcement_id)
                    if a is not None:
                        msgs.append(announcement_message(a))
                db.delete(p)
            if not msgs:
                continue
            if len(msgs) == 1:
                out.append((sub, _push_payload(msgs[0]), telegram_text(msgs[0])))
            else:
                d = digest_message(msgs)
                out.append((sub, _push_payload(d), telegram_digest(msgs)))
        async with Sender(db) as sender:
            await sender.send_many(out)
            sent = sender.counts["push"] + sender.counts["telegram"]
        db.commit()
        return sent
    finally:
        db.close()


async def notify_admins(text: str, url: str = "/admin") -> None:
    db = SessionLocal()
    try:
        admins = list(db.scalars(select(Subscriber).where(Subscriber.is_admin.is_(True),
                                                          Subscriber.active.is_(True))))
        if not admins:
            return
        payload = {"title": "Open Unifi admin", "body": text[:300], "url": url, "tag": "admin"}
        async with Sender(db) as sender:
            await sender.send_many([(s, payload, telegram.esc(text)) for s in admins], "high")
        db.commit()
    finally:
        db.close()


async def send_test(sub_id: int) -> str:
    db = SessionLocal()
    try:
        sub = db.get(Subscriber, sub_id)
        if sub is None:
            return "error"
        payload = {"title": "Open Unifi", "body": "Notifiche attive! Ti avviseremo qui per ogni novità. 🎓",
                   "url": "/", "tag": "test"}
        async with Sender(db) as sender:
            res = await sender._one(sub, payload, "✅ Notifiche attive! Ti avviseremo qui per ogni novità.",
                                    "high")
        if sub.channel == "push" and not sub.active:
            db.delete(sub)
        db.commit()
        return res
    finally:
        db.close()
