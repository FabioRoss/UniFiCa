"""Key/value settings in the DB, plus the keys generated on first start
(VAPID keypair, cookie secret) so a fresh deploy needs no key ceremony."""
from __future__ import annotations

import base64
import secrets
from typing import Any

from sqlalchemy.orm import Session

from .config import settings
from .models import Setting

# Texts the admin edits from the panel; defaults shown until then.
SITE_DEFAULTS: dict[str, Any] = {
    "intro": "Tutte le novità dei siti dell'Università di Firenze in un unico posto, "
    "con notifiche quando qualcosa viene pubblicato o modificato.",
    "disclaimer": "Open Unifi è un progetto indipendente e non ufficiale, non affiliato "
    "all'Università degli Studi di Firenze. I contenuti provengono dai siti pubblici "
    "dell'Ateneo: in caso di dubbio fa sempre fede la pagina originale.",
    "contact_email": "",
    "telegram_channel_url": "",
}


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return default if row is None else row.value


def put(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def site(db: Session) -> dict[str, Any]:
    return {**SITE_DEFAULTS, **(get(db, "site") or {})}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid_keys(db: Session) -> dict[str, str]:
    """{"public": base64url uncompressed point, "private": base64url scalar}."""
    keys = get(db, "vapid")
    if keys:
        return keys
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = ec.generate_private_key(ec.SECP256R1())
    raw_priv = priv.private_numbers().private_value.to_bytes(32, "big")
    raw_pub = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    keys = {"public": _b64url(raw_pub), "private": _b64url(raw_priv)}
    put(db, "vapid", keys)
    return keys


def secret_key(db: Session) -> str:
    if settings.secret_key:
        return settings.secret_key
    key = get(db, "secret_key")
    if not key:
        key = secrets.token_urlsafe(48)
        put(db, "secret_key", key)
    return key
