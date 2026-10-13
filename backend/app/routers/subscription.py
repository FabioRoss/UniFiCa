"""Anonymous subscriptions. A random token (kept in the browser, or in the
Telegram /impostazioni link) is the only key to a subscriber's settings."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Source, Subscriber, utcnow
from ..notify import dispatcher
from ..notify import prefs as P

router = APIRouter(prefix="/api/subscription")

PLATFORMS = {"ios", "android", "desktop", "other"}


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushSubscription(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: PushKeys


class PushIn(BaseModel):
    subscription: PushSubscription
    prefs: dict[str, Any] | None = None
    platform: str = "other"
    # Sent by the service worker when the browser rotates the subscription
    old_endpoint: str | None = Field(None, max_length=1000)


class PrefsIn(BaseModel):
    prefs: dict[str, Any]


def _valid_sources(db: Session) -> set[int]:
    return set(db.scalars(select(Source.id)))


def _out(sub: Subscriber) -> dict[str, Any]:
    return {"token": sub.token, "channel": sub.channel, "prefs": P.merged(sub.prefs), "active": sub.active,
            "is_admin": sub.is_admin, "platform": sub.platform}


def _get(db: Session, token: str) -> Subscriber:
    sub = db.scalar(select(Subscriber).where(Subscriber.token == token)) if len(token) >= 16 else None
    if sub is None:
        raise HTTPException(404, "Iscrizione non trovata")
    return sub


@router.post("/push")
def subscribe_push(body: PushIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    ep = body.subscription.endpoint
    sub = db.scalar(select(Subscriber).where(Subscriber.channel == "push", Subscriber.endpoint == ep))
    if sub is None and body.old_endpoint:
        sub = db.scalar(select(Subscriber).where(Subscriber.channel == "push",
                                                 Subscriber.endpoint == body.old_endpoint))
        if sub is not None:
            sub.endpoint = ep
    if sub is None:
        sub = Subscriber(channel="push", endpoint=ep, token=secrets.token_urlsafe(24),
                         prefs=P.clean(body.prefs, _valid_sources(db)))
        db.add(sub)
    elif body.prefs is not None:
        sub.prefs = P.clean(body.prefs, _valid_sources(db))
    sub.keys = body.subscription.keys.model_dump()
    sub.platform = body.platform if body.platform in PLATFORMS else "other"
    sub.active = True
    sub.failures = 0
    sub.last_active_at = utcnow()
    db.commit()
    return _out(sub)


@router.get("/{token}")
def get_subscription(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    sub = _get(db, token)
    sub.last_active_at = utcnow()
    db.commit()
    return _out(sub)


@router.put("/{token}")
def update_prefs(token: str, body: PrefsIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    sub = _get(db, token)
    sub.prefs = P.clean(body.prefs, _valid_sources(db))
    sub.last_active_at = utcnow()
    if sub.channel == "telegram":
        sub.active = True
    db.commit()
    return _out(sub)


@router.delete("/{token}")
def unsubscribe(token: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    sub = _get(db, token)
    if sub.channel == "push":
        db.delete(sub)
    else:
        sub.active = False
    db.commit()
    return {"ok": True}


@router.post("/{token}/test")
async def test(token: str, db: Session = Depends(get_db)) -> dict[str, str]:
    sub = _get(db, token)
    return {"result": await dispatcher.send_test(sub.id)}
