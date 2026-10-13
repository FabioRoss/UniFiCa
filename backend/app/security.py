"""Admin authentication: one account from the environment, signed session
cookie, in-memory throttle on failed logins.

- Login throttle: 8 failures per IP and 40 overall per 15 minutes.
- Sessions carry a fingerprint of the credentials, so changing the admin
  password (or user) logs out every existing session.
- Login needs both an email/username and a password; an empty or guessable
  user ("admin", "root"...) or a placeholder password keeps the panel locked.
  The user is matched case-insensitively (emails are)."""
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

WINDOW_SECONDS = 900
MAX_FAILURES_PER_IP = 8
MAX_FAILURES_TOTAL = 40  # spread-out guessing from many IPs
PLACEHOLDERS = {"", "change_me", "changeme", "admin", "password"}
GUESSABLE_USERS = {"", "change_me", "changeme", "admin", "administrator", "root", "user", "test", "openunifi"}

_failures: dict[str, deque[float]] = defaultdict(deque)
_all_failures: deque[float] = deque()


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


def normalize_user(user: str) -> str:
    return user.strip().casefold()


def admin_locked() -> bool:
    """No usable credentials configured: nobody can log in."""
    return (settings.admin_password.strip().lower() in PLACEHOLDERS
            or normalize_user(settings.admin_user) in GUESSABLE_USERS)


def user_matches(user: str) -> bool:
    return hmac.compare_digest(normalize_user(user).encode(), normalize_user(settings.admin_user).encode())


def client_ip(request: Request) -> str:
    """The address Caddy saw. Caddy appends the real peer to X-Forwarded-For,
    so the *last* entry is trustworthy; earlier ones are client-supplied."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff.strip():
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def _prune(q: deque[float], now: float) -> None:
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()


def throttled(ip: str) -> bool:
    now = time.monotonic()
    q = _failures[ip]
    _prune(q, now)
    _prune(_all_failures, now)
    return len(q) >= MAX_FAILURES_PER_IP or len(_all_failures) >= MAX_FAILURES_TOTAL


def record_failure(ip: str) -> None:
    now = time.monotonic()
    _failures[ip].append(now)
    _all_failures.append(now)


def _fingerprint() -> str:
    raw = f"{normalize_user(settings.admin_user)}\x00{settings.admin_password}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _serializer(db: Session) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings_store.secret_key(db), salt="openunifi-admin")


def make_session(db: Session) -> str:
    return _serializer(db).dumps({"u": settings.admin_user, "f": _fingerprint(), "n": secrets.token_hex(8)})


def require_admin(request: Request, db: Session = Depends(get_db)) -> str:
    # Defence in depth on top of the SameSite=Strict cookie: writes must come
    # from our own fetch() wrapper, which sets this header.
    if request.method not in ("GET", "HEAD") and request.headers.get("x-openunifi") != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Richiesta non valida")
    raw = request.cookies.get(COOKIE)
    if raw and not admin_locked():
        try:
            data = _serializer(db).loads(raw, max_age=SESSION_DAYS * 86400)
            if hmac.compare_digest(data.get("f", ""), _fingerprint()):
                return data["u"]
        except BadSignature:
            pass
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso richiesto")
