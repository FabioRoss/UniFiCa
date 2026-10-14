"""FastAPI entrypoint: JSON API, RSS, background jobs and the built PWA."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import og, scheduler, seo, settings_store
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


# ── Search engines and link previews (seo.py, og.py) ─────────────────────

@app.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    return PlainTextResponse(seo.robots(), headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap() -> Response:
    with SessionLocal() as db:
        xml = seo.sitemap(db)
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/og/{key}.png", include_in_schema=False)
def og_image(key: str) -> FileResponse:
    # Sync on purpose: FastAPI runs it in a thread, drawing takes a moment
    with SessionLocal() as db:
        card = seo.card_for(db, key)
    if card is None:
        raise HTTPException(404)
    # The URL carries ?v=<content hash>, so the image can be cached for long
    return FileResponse(og.cached(key, *card), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


# ── PWA ──────────────────────────────────────────────────────────────────

NO_CACHE = {"Cache-Control": "no-cache"}
_index: tuple[float, str] | None = None


def _index_html() -> str:
    global _index
    path = DIST / "index.html"
    mtime = path.stat().st_mtime
    if _index is None or _index[0] != mtime:
        _index = (mtime, path.read_text(encoding="utf-8"))
    return _index[1]


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str, request: Request) -> Response:
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
        if path == "version.json":
            # Installed apps poll this to notice a new build: never cache it
            return FileResponse(target, media_type="application/json", headers={"Cache-Control": "no-store"})
        if path.endswith(".webmanifest"):
            return FileResponse(target, media_type="application/manifest+json", headers=NO_CACHE)
        return FileResponse(target, headers={"Cache-Control": "public, max-age=3600"})
    # App routes: index.html with this page's title, description, preview
    # image and a plain HTML version of its content (seo.py)
    with SessionLocal() as db:
        page = seo.page_for(db, path, dict(request.query_params))
    return HTMLResponse(seo.inject(_index_html(), page), status_code=page.status, headers=NO_CACHE)
