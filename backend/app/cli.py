"""Maintenance commands, run inside the container:

    python -m app.cli hash-password            # prompt, print a hash for .env
    python -m app.cli run [slug ...]           # check sources now (all if none)
    python -m app.cli vapid                    # print the VAPID public key
    python -m app.cli backup                   # take a database backup now
    python -m app.cli export-exams FILE [--source SLUG]   # exam sessions to JSON
    python -m app.cli import-exams FILE [--source SLUG]   # load them (no notifications)
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
    sub.add_parser("backup")
    for name in ("export-exams", "import-exams"):
        cmd = sub.add_parser(name)
        cmd.add_argument("file")
        cmd.add_argument("--source", default=None, help="default: medicina-appelli / the file's source")
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
    if args.cmd in ("export-exams", "import-exams"):
        import json

        from . import exam_snapshot

        if args.cmd == "export-exams":
            data = exam_snapshot.export(db, args.source or "medicina-appelli")
            with open(args.file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            print(f"{len(data['sessions'])} appelli esportati in {args.file} (dati del {data['fetched_at']})")
        else:
            with open(args.file, encoding="utf-8") as f:
                data = json.load(f)
            res = exam_snapshot.import_(db, data, args.source)
            print(f"Importati: {res['sessions']} appelli ({res['added']} nuovi, {res['changed']} aggiornati), "
                  f"dati del {data['fetched_at']}. Nessuna notifica inviata.")
        return
    if args.cmd == "backup":
        from . import backup

        print(backup.run())
        return
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
