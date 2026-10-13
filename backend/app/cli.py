"""Maintenance commands, run inside the container:

    python -m app.cli hash-password            # prompt, print a hash for .env
    python -m app.cli run [slug ...]           # check sources now (all if none)
    python -m app.cli vapid                    # print the VAPID public key
    python -m app.cli backup                   # take a database backup now
    python -m app.cli export-exams FILE [--source SLUG]   # exam sessions to JSON
    python -m app.cli import-exams FILE [--source SLUG] [--sync]
                                  # load them; --sync = daily feed, notifies changes
    python -m app.cli exams-direct [--source SLUG]        # read ESSE3 from this server again
    python -m app.cli fetch-exams FILE [--source SLUG]    # read ESSE3 straight to JSON (no DB)
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
        if name == "import-exams":
            cmd.add_argument("--sync", action="store_true",
                             help="daily feed: notify changes, skip ESSE3 checks from this server")
    sub.add_parser("exams-direct").add_argument("--source", default="medicina-appelli")
    fe = sub.add_parser("fetch-exams")
    fe.add_argument("file")
    fe.add_argument("--source", default="medicina-appelli")
    args = ap.parse_args()

    if args.cmd == "fetch-exams":
        import json

        from . import exam_snapshot

        data = asyncio.run(exam_snapshot.fetch(args.source))
        with open(args.file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(f"{len(data['sessions'])} appelli scritti in {args.file}")
        return

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
            res = exam_snapshot.import_(db, data, args.source, sync=args.sync)
            if res["skipped"]:
                print(f"Snapshot del {data['fetched_at']} già importato: niente da fare.")
                return
            sent = ""
            if res["version_ids"]:
                from .notify import dispatcher

                asyncio.run(dispatcher.dispatch_versions(res["version_ids"]))
                sent = f" Notificate {len(res['version_ids'])} novità."
            print(f"Importati: {res['sessions']} appelli ({res['added']} nuovi, {res['changed']} aggiornati), "
                  f"dati del {data['fetched_at']}.{sent or ' Nessuna notifica inviata.'}")
        return
    if args.cmd == "exams-direct":
        from . import exam_snapshot

        exam_snapshot.set_direct(db, args.source)
        print(f"{args.source}: torna a leggere ESSE3 direttamente da questo server.")
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
