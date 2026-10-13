"""Maintenance commands, run inside the container:

    python -m app.cli hash-password            # prompt, print a hash for .env
    python -m app.cli run [slug ...]           # check sources now (all if none)
    python -m app.cli vapid                    # print the VAPID public key
"""
from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_engine
from .models import Source
from .security import hash_password
from .seed import seed
from . import settings_store


def main() -> None:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hash-password")
    run = sub.add_parser("run")
    run.add_argument("slugs", nargs="*")
    run.add_argument("--no-notify", action="store_true")
    sub.add_parser("vapid")
    args = ap.parse_args()

    if args.cmd == "hash-password":
        pw = getpass.getpass("Password admin: ")
        if pw != getpass.getpass("Ripeti: "):
            raise SystemExit("Le password non coincidono")
        print(hash_password(pw))
        return

    init_engine(settings.db_path)
    db = SessionLocal()
    seed(db)
    if args.cmd == "vapid":
        print(settings_store.vapid_keys(db)["public"])
        return
    if args.cmd == "run":
        from .scraper import engine

        stmt = select(Source).order_by(Source.position)
        if args.slugs:
            stmt = stmt.where(Source.slug.in_(args.slugs))
        ids = [(s.id, s.slug) for s in db.scalars(stmt)]
        db.close()

        async def go() -> None:
            for sid, slug in ids:
                res = await engine.run_source(sid, dispatch=not args.no_notify)
                print(slug, res.as_dict())

        asyncio.run(go())


if __name__ == "__main__":
    main()
