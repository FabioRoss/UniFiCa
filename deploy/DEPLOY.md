# Deploy Open Unifi next to WeRace and Halo

Open Unifi joins the same server and the **same shared Caddy** ("edge proxy")
as the other apps. Caddy already owns ports 80/443 and gets the Let's Encrypt
certificates; Open Unifi publishes no ports and is reached by container name
(`openunifi-app`) over the `edge` Docker network.

```
/srv/
├── edge/            ← shared Caddy (from the Halo repo, deploy/edge)
├── werace-timing/
├── halo-f1/
└── openunifi/       ← this repo
```

## 1. DNS

Point an `A` record for the domain you picked (e.g. `openunifi.it` and
`www.openunifi.it`) at the server's IP.

## 2. Add the site to the edge proxy

The Halo repo (`deploy/edge`) already contains the Open Unifi block. On the server:

```bash
cd /srv/edge
# pull the updated Caddyfile + docker-compose.yml from the Halo repo, or copy them over
nano .env
#   OPENUNIFI_DOMAIN=openunifi.it, www.openunifi.it
```

For reference, the block in `/srv/edge/Caddyfile` is:

```caddy
{$OPENUNIFI_DOMAIN} {
	encode zstd gzip
	reverse_proxy openunifi-app:8000
}
```

Don't reload the proxy yet; start the app first (step 3), so Caddy finds it.

## 3. Start Open Unifi

```bash
cd /srv
git clone https://github.com/FabioRoss/UniFiCa.git openunifi
cd openunifi
cp .env.example .env

# admin password hash (no `$` in it, paste it as is)
docker compose run --rm --no-deps openunifi-app python -m app.cli hash-password
nano .env        # OPENUNIFI_PUBLIC_URL, OPENUNIFI_ADMIN_PASSWORD, OPENUNIFI_VAPID_CONTACT, Telegram (optional)

docker compose up -d --build
docker compose logs -f openunifi-app     # first checks start within 30 s
```

Then reload the edge proxy so it picks up the new domain:

```bash
cd /srv/edge && docker compose up -d
docker compose logs -f caddy             # watch it obtain the certificate
```

Open `https://<your domain>` and `https://<your domain>/admin`.

### What happens on first start

- The database (`/data/openunifi.db` in the `openunifi_data` volume) is created and
  seeded with the Medicina sources and a starter set of useful links.
- A VAPID keypair for Web Push is generated and stored in the database.
  **Never delete the volume**: new keys would invalidate every push subscription.
- Each source's first check is a *baseline*: existing news (including the
  archive), pages and exam sessions are stored without notifying anyone.
  From the second check on, every new or changed item is notified.

## 4. Telegram bot (optional, free)

1. On Telegram, talk to **@BotFather**: `/newbot`, choose a name and a username
   (e.g. `OpenUnifiBot`), copy the token.
2. Put it in `.env` as `OPENUNIFI_TELEGRAM_BOT_TOKEN` and `docker compose up -d`.
3. Optional public channel: create it, add the bot as administrator, set
   `OPENUNIFI_TELEGRAM_CHANNEL=@yourchannel`.
4. Admin alerts on Telegram: Admin → Impostazioni → "Genera codice".

The bot uses long polling: nothing to expose, no webhook to configure.

## Everyday operations

```bash
cd /srv/openunifi
git pull && docker compose up -d --build              # update
docker compose logs -f openunifi-app                  # logs
docker compose exec openunifi-app python -m app.cli run medicina-news   # check a source now

# backup (SQLite online backup, safe while running)
docker compose exec openunifi-app python -c "import sqlite3; s=sqlite3.connect('/data/openunifi.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker cp openunifi-app:/data/backup.db ./openunifi-$(date +%F).db
```

## Traffic stats (optional)

The edge proxy's GoAccess dashboard reads only the Halo log. To get Open Unifi
stats too, give its Caddy block its own `log { output file /var/log/caddy/openunifi-access.log }`
and run a second `goaccess` service on that file (see the Halo DEPLOY.md, step 7).
