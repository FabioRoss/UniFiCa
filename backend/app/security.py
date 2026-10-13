"""Admin authentication: one account from the environment, signed session
cookie, simple in-memory throttle on failed logins."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from . import settings_store

COOKIE = "openunifi_admin"
SESSION_DAYS = 30
PBKDF2_ROUNDS = 600_000

_failures: dict[str, deque[float]] = defaultdict(deque)


def hash_password(password: str) -> str:
    """pbkdf2_sha256:<rounds>:<salt hex>:<hash hex>  (no `$`, safe in .env files)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256:{PBKDF2_ROUNDS}:{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256:"):
        try:
            _, rounds, salt, want = stored.split(":")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
            return hmac.compare_digest(dk.hex(), want)
        except ValueError:
            return False
    return hmac.compare_digest(password.encode(), stored.encode())


def throttled(ip: str) -> bool:
    q = _failures[ip]
    now = time.monotonic()
    while q and now - q[0] > 900:
        q.popleft()
    return len(q) >= 8


def record_failure(ip: str) -> None:
    _failures[ip].append(time.monotonic())


def _serializer(db: Session) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings_store.secret_key(db), salt="openunifi-admin")


def make_session(db: Session) -> str:
    return _serializer(db).dumps({"u": settings.admin_user, "n": secrets.token_hex(8)})


def require_admin(request: Request, db: Session = Depends(get_db)) -> str:
    # Defence in depth on top of the SameSite=Strict cookie: writes must come
    # from our own fetch() wrapper, which sets this header.
    if request.method not in ("GET", "HEAD") and request.headers.get("x-openunifi") != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Richiesta non valida")
    raw = request.cookies.get(COOKIE)
    if raw:
        try:
            data = _serializer(db).loads(raw, max_age=SESSION_DAYS * 86400)
            if data.get("u") == settings.admin_user:
                return data["u"]
        except BadSignature:
            pass
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso richiesto")
