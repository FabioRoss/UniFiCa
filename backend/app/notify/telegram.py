"""Telegram bot: long polling (no webhook, so nothing extra to expose through
Caddy), a handful of Italian commands, and message sending.

Users fine-tune sources and keywords on the web: /impostazioni replies with a
private link (?t=<token>) that opens the same preferences page the PWA uses.
"""
from __future__ import annotations

import asyncio
import html
import logging
import secrets
from typing import Any

import httpx
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import Item, Source, Subscriber, Version, utcnow
from .. import settings_store

log = logging.getLogger("openunifi.telegram")

OK, GONE, ERROR = "ok", "gone", "error"
API = "https://api.telegram.org/bot{token}/{method}"

_bot_username: str | None = None


def enabled() -> bool:
    return bool(settings.telegram_bot_token)


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


async def call(client: httpx.AsyncClient, method: str, **params: Any) -> dict[str, Any]:
    r = await client.post(API.format(token=settings.telegram_bot_token, method=method), json=params)
    data = r.json()
    if not data.get("ok"):
        raise TelegramError(data.get("error_code", r.status_code), data.get("description", ""), data)
    return data["result"]


class TelegramError(Exception):
    def __init__(self, code: int, description: str, data: dict[str, Any]):
        super().__init__(f"{code} {description}")
        self.code, self.description, self.data = code, description, data


async def send(client: httpx.AsyncClient, chat_id: str | int, text: str,
               buttons: list[list[dict[str, str]]] | None = None) -> str:
    params: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    for _ in range(3):
        try:
            await call(client, "sendMessage", **params)
            return OK
        except TelegramError as e:
            if e.code == 429:
                retry = (e.data.get("parameters") or {}).get("retry_after", 3)
                await asyncio.sleep(min(int(retry), 30))
                continue
            if e.code in (400, 403) and any(
                s in e.description.lower() for s in ("blocked", "deactivated", "chat not found", "kicked")
            ):
                return GONE
            log.info("telegram send to %s failed: %s", chat_id, e)
            return ERROR
        except httpx.HTTPError as e:
            log.info("telegram send to %s failed: %s", chat_id, e)
            return ERROR
    return ERROR


def bot_username() -> str | None:
    return _bot_username


# ── Commands ─────────────────────────────────────────────────────────────

HELP = (
    "<b>Open Unifi</b> ti avvisa quando i siti UniFI pubblicano o modificano qualcosa.\n\n"
    "/impostazioni scegli fonti, parole chiave, orari di silenzio\n"
    "/ultime gli ultimi aggiornamenti\n"
    "/stato le tue impostazioni attuali\n"
    "/stop metti in pausa le notifiche\n"
    "/start riattiva le notifiche\n"
    "/cancella cancella i tuoi dati (chat, nome, preferenze)"
)


def _prefs_link(token: str) -> str:
    return f"{settings.base_url}/notifiche?t={token}"


def _subscriber(db, chat_id: str) -> Subscriber | None:  # noqa: ANN001
    return db.scalar(select(Subscriber).where(Subscriber.channel == "telegram", Subscriber.endpoint == chat_id))


def _status_text(db, sub: Subscriber) -> str:  # noqa: ANN001
    from .prefs import merged

    p = merged(sub.prefs)
    if p["sources"] is None:
        fonti = "tutte"
    else:
        names = [s.name for s in db.scalars(select(Source).where(Source.id.in_(p["sources"] or [0])))]
        fonti = ", ".join(names) if names else "nessuna (solo parole chiave)"
    lines = [
        f"<b>Stato:</b> {'attivo ✅' if sub.active else 'in pausa ⏸'}",
        f"<b>Fonti:</b> {esc(fonti)}",
        f"<b>Parole chiave:</b> {esc(', '.join(p['keywords'])) or 'nessuna'}",
        f"<b>Modifiche:</b> {'sì' if p['notify_modified'] else 'no'}",
    ]
    if p["digest"]:
        lines.append(f"<b>Riepilogo giornaliero:</b> alle {p['digest']}")
    elif p["quiet"]:
        lines.append(f"<b>Silenzio:</b> {p['quiet']['start']} - {p['quiet']['end']}")
    return "\n".join(lines)


def profile(chat: dict[str, Any]) -> dict[str, str]:
    """Public @username and name of a private chat, shown in the admin panel."""
    name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
    return {"username": chat.get("username") or "", "name": name}


def _remember_profile(sub: Subscriber, chat: dict[str, Any]) -> None:
    p = profile(chat)
    if (sub.keys or {}) != p:
        sub.keys = p  # unused for Telegram otherwise (push keys live here for push)


async def backfill_profiles(client: httpx.AsyncClient) -> None:
    """Subscribers from before profiles were saved: ask Telegram once."""
    db = SessionLocal()
    try:
        subs = db.scalars(select(Subscriber).where(Subscriber.channel == "telegram")).all()
        for sub in subs:
            if "username" in (sub.keys or {}):
                continue
            try:
                _remember_profile(sub, await call(client, "getChat", chat_id=sub.endpoint))
                db.commit()
            except TelegramError as e:
                log.info("getChat %s failed: %s", sub.endpoint, e)
            await asyncio.sleep(0.2)
    finally:
        db.close()


async def handle_message(client: httpx.AsyncClient, msg: dict[str, Any]) -> None:
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return
    chat_id = str(chat["id"])
    text = (msg.get("text") or "").strip()
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()

    db = SessionLocal()
    try:
        sub = _subscriber(db, chat_id)
        if sub is not None:
            _remember_profile(sub, chat)
            db.commit()
        if cmd == "/start":
            created = sub is None
            if created:
                sub = Subscriber(channel="telegram", endpoint=chat_id, token=secrets.token_urlsafe(24),
                                 platform="telegram", prefs={}, keys=profile(chat))
                db.add(sub)
            sub.active = True
            sub.last_active_at = utcnow()
            db.commit()
            await send(
                client, chat_id,
                ("Benvenuto su <b>Open Unifi</b>! 🎓\n\n" if created else "Notifiche riattivate ✅\n\n")
                + "Riceverai un messaggio per ogni nuova pubblicazione o modifica sui siti monitorati.\n"
                "Puoi scegliere fonti e parole chiave dal pulsante qui sotto.\n\n" + HELP,
                [[{"text": "⚙️ Impostazioni", "url": _prefs_link(sub.token)}]],
            )
            if arg.startswith("admin_"):
                await _try_admin(client, db, sub, arg.removeprefix("admin_"))
            return
        if sub is None:
            await send(client, chat_id, "Scrivi /start per attivare le notifiche.")
            return
        sub.last_active_at = utcnow()
        db.commit()
        if cmd in ("/cancella", "/elimina", "/delete"):
            db.delete(sub)
            db.commit()
            await send(client, chat_id, "Fatto: chat, nome e preferenze cancellati. Scrivi /start se vuoi ricominciare.")
            return
        if cmd == "/stop":
            sub.active = False
            db.commit()
            await send(client, chat_id, "Notifiche in pausa. Scrivi /start per riattivarle.")
        elif cmd in ("/impostazioni", "/settings", "/fonti"):
            await send(client, chat_id, "Gestisci le tue preferenze da qui (link personale, non condividerlo):",
                       [[{"text": "⚙️ Apri impostazioni", "url": _prefs_link(sub.token)}]])
        elif cmd == "/stato":
            await send(client, chat_id, _status_text(db, sub))
        elif cmd == "/ultime":
            rows = db.execute(
                select(Version, Item, Source).join(Item, Version.item_id == Item.id)
                .join(Source, Item.source_id == Source.id)
                .where(Item.hidden.is_(False))
                .order_by(Version.created_at.desc()).limit(6)
            ).all()
            if not rows:
                await send(client, chat_id, "Ancora nessun aggiornamento.")
            else:
                lines = [
                    f"{'🆕' if v.kind == 'new' else '✏️'} <a href=\"{settings.base_url}/n/{i.id}?v={v.number}\">"
                    f"{esc(i.title)}</a> <i>({esc(s.name)})</i>"
                    for v, i, s in rows
                ]
                await send(client, chat_id, "<b>Ultimi aggiornamenti</b>\n\n" + "\n".join(lines))
        elif cmd == "/admin":
            await _try_admin(client, db, sub, arg.strip())
        else:
            await send(client, chat_id, HELP)
    finally:
        db.close()


async def _try_admin(client: httpx.AsyncClient, db, sub: Subscriber, code: str) -> None:  # noqa: ANN001
    pending = settings_store.get(db, "admin_link_code") or {}
    import datetime as dt

    valid = (
        pending.get("code")
        and secrets.compare_digest(pending["code"], code)
        and dt.datetime.fromisoformat(pending["expires"]) > utcnow()
    )
    if not valid:
        await send(client, sub.endpoint, "Codice non valido o scaduto.")
        return
    sub.is_admin = True
    db.commit()
    settings_store.put(db, "admin_link_code", {})
    await send(client, sub.endpoint, "🔐 Questa chat ora riceve gli avvisi di amministrazione.")


async def poll_forever() -> None:
    """Long-poll getUpdates. Survives network errors and a bad token."""
    global _bot_username
    offset = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(70.0, connect=15.0)) as client:
        while True:
            try:
                if _bot_username is None:
                    me = await call(client, "getMe")
                    _bot_username = me.get("username")
                    await call(client, "setMyCommands", commands=[
                        {"command": "impostazioni", "description": "Fonti, parole chiave e orari"},
                        {"command": "ultime", "description": "Ultimi aggiornamenti"},
                        {"command": "stato", "description": "Le tue impostazioni"},
                        {"command": "stop", "description": "Metti in pausa le notifiche"},
                        {"command": "cancella", "description": "Cancella i tuoi dati"},
                    ])
                    await call(client, "deleteWebhook")
                    try:
                        await backfill_profiles(client)
                    except Exception as e:  # never block polling for it
                        log.warning("telegram profile backfill failed: %s", e)
                updates = await call(client, "getUpdates", offset=offset, timeout=50,
                                     allowed_updates=["message"])
                for u in updates:
                    offset = u["update_id"] + 1
                    if "message" in u:
                        try:
                            await handle_message(client, u["message"])
                        except Exception:
                            log.exception("telegram update failed")
            except asyncio.CancelledError:
                raise
            except TelegramError as e:
                log.warning("telegram api error: %s", e)
                await asyncio.sleep(60 if e.code == 401 else 10)
            except Exception as e:
                log.warning("telegram polling error: %s", e)
                await asyncio.sleep(10)
