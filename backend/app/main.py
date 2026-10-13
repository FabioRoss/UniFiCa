"""FastAPI entrypoint: JSON API, RSS, background jobs and the built PWA."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import scheduler, settings_store
from .config import settings
from .db import SessionLocal, init_engine
from .notify import telegram
from .routers import admin, public, subscription
from .security import admin_locked
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("openunifi")

DIST = Path(settings.frontend_dist)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine(settings.db_path)
    db = SessionLocal()
    try:
        seed(db)
        settings_store.vapid_keys(db)  # generate on first start
        settings_store.secret_key(db)
    finally:
        db.close()
    if admin_locked():
        log.warning("Admin panel locked: set OPENUNIFI_ADMIN_USER (an email or username, not 'admin') "
                    "and OPENUNIFI_ADMIN_PASSWORD")
    elif not settings.admin_password.startswith("pbkdf2_sha256:") and len(settings.admin_password) < 12:
        log.warning("The admin password is short: use 12+ characters (python -m app.cli hash-password)")

    tasks = []
    if settings.scheduler_enabled:
        tasks.append(asyncio.create_task(scheduler.run_forever(), name="scheduler"))
    if telegram.enabled():
        tasks.append(asyncio.create_task(telegram.poll_forever(), name="telegram"))
    yield
    for t in tasks:
        t.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await t


app = FastAPI(title="Open Unifi", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(public.router)
app.include_router(subscription.router)
app.include_router(admin.router)


@app.middleware("http")
async def headers(request: Request, call_next):  # noqa: ANN001, ANN201
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    if request.url.path.startswith(("/admin", "/api/admin")):
        resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    return resp


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
def api_404(rest: str) -> JSONResponse:
    return JSONResponse({"detail": "Not found"}, status_code=404)


# ── PWA ──────────────────────────────────────────────────────────────────

NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Response:
    if not DIST.exists():
        raise HTTPException(503, "Frontend non compilato (npm run build)")
    target = (DIST / path).resolve()
    if path and target.is_file() and DIST.resolve() in target.parents:
        if path.startswith("assets/"):
            # Vite fingerprints these: cache forever
            return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})
        if path == "sw.js":
            return FileResponse(target, media_type="text/javascript",
                                headers={**NO_CACHE, "Service-Worker-Allowed": "/"})
        if path.endswith(".webmanifest"):
            return FileResponse(target, media_type="application/manifest+json", headers=NO_CACHE)
        return FileResponse(target, headers={"Cache-Control": "public, max-age=3600"})
    return FileResponse(DIST / "index.html", headers=NO_CACHE)
