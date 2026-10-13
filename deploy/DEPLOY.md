# Deploy Open Unifi next to WeRace and Halo

Open Unifi joins the same server and the **same shared Caddy** ("edge proxy")
as the other apps. Caddy already owns ports 80/443 and gets the Let's Encrypt
certificates; Open Unifi publishes no ports and is reached by container name
(`openunifi-app`) over the `edge` Docker network.

```
/srv/
├── edge/            ← shared Caddy, repo FabioRoss/edge-caddy
├── werace-timing/
├── halo-f1/
└── openunifi/       ← this repo
```

## 1. DNS

At the registrar (register.it for `openunifi.it`), with `SERVER_IP` being the
same IP the WeRace and Halo domains already point to:

| Name | Type | Value | Action |
|---|---|---|---|
| `openunifi.it` | A | `SERVER_IP` | **change** the existing one (it points to register.it's hosting) |
| `www.openunifi.it` | CNAME | `openunifi.it.` | **add** (redirected to the bare domain by Caddy) |
| `ftp.openunifi.it` | CNAME | `openunifi.it.` | delete, unless you use register.it's FTP |
| MX, TXT (SPF), `_autodiscover` SRV, `autoconfig`, `authsmtp` | | | **leave as they are**: they run the register.it mailbox |

Only add an `AAAA` record if the server has a working IPv6 address (and ports
80/443 open on it): a wrong `AAAA` makes Let's Encrypt fail. If you ever add a
`CAA` record, it must allow `letsencrypt.org`.

Check it has propagated (TTL is 15 minutes) before starting Caddy:
`dig +short openunifi.it` and `dig +short www.openunifi.it` must print the server IP.

## 2. Add the site to the edge proxy

The shared proxy lives in its own repo, **FabioRoss/edge-caddy**, which already
contains the Open Unifi block. If `/srv/edge` on the server is still the old copy
taken from the Halo repo, first follow that repo's `MIGRATION.md` (it keeps the
certificates). Then:

```bash
nano /srv/edge/.env
#   OPENUNIFI_DOMAIN=openunifi.it          (bare domain only; www redirects to it)
```

For reference, the block in `caddy/Caddyfile` is:

```caddy
{$OPENUNIFI_DOMAIN} {
	encode zstd gzip
	reverse_proxy openunifi-app:8000
}
www.{$OPENUNIFI_DOMAIN} {
	redir https://{$OPENUNIFI_DOMAIN}{uri} permanent
}
```

One origin only, on purpose: push subscriptions, the admin login and the
installed PWA all belong to the exact host they were created on.

Don't reload the proxy yet; start the app first (step 3), so Caddy finds it.

## 3. Start Open Unifi

```bash
cd /srv
git clone https://github.com/FabioRoss/UniFiCa.git openunifi
cd openunifi
cp .env.example .env

# admin password hash (no `$` in it, paste it as is)
docker compose run --rm --no-deps openunifi-app python -m app.cli hash-password
nano .env        # OPENUNIFI_PUBLIC_URL, OPENUNIFI_ADMIN_USER, OPENUNIFI_ADMIN_PASSWORD, OPENUNIFI_VAPID_CONTACT, Telegram (optional)

docker compose up -d --build
docker compose logs -f openunifi-app     # first checks start within 30 s
```

Then reload the edge proxy so it picks up the new domain:

```bash
/srv/edge/deploy.sh                      # validates, then reloads with no downtime
cd /srv/edge && docker compose logs -f caddy   # watch it obtain the certificate
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

### Admin panel security

`/admin` asks for **both** an email/username and a password, the
`OPENUNIFI_ADMIN_USER` and `OPENUNIFI_ADMIN_PASSWORD` from `.env`; every
`/api/admin` call is refused without a valid session. In detail:

- Session: signed, `HttpOnly`, `Secure`, `SameSite=Strict` cookie, valid 30 days.
  Changing `OPENUNIFI_ADMIN_PASSWORD` (or the user) logs out every session.
- Brute force: 8 wrong attempts per IP, and 40 overall, in 15 minutes lock
  the login for a while. The IP is the one Caddy saw, so faking
  `X-Forwarded-For` does not help.
- Writes also need a custom header only the app sends (CSRF protection).
- With an empty or placeholder password (`CHANGE_ME`), or an empty or
  guessable user (`admin`, `root`...), nobody can log in. The user is not
  case-sensitive (handy for emails). A wrong login never says which of the two was wrong.
- The admin pages are marked `noindex` for search engines.

## 4. Telegram bot (optional, free)

1. On Telegram, talk to **@BotFather**: `/newbot`, choose a name and a username
   (e.g. `OpenUnifiBot`), copy the token.
2. Put it in `.env` as `OPENUNIFI_TELEGRAM_BOT_TOKEN` and `docker compose up -d`.
3. Optional public channel: create it, add the bot as administrator, set
   `OPENUNIFI_TELEGRAM_CHANNEL=@yourchannel`.
4. Admin alerts on Telegram: Admin → Impostazioni → "Genera codice".

The bot uses long polling: nothing to expose, no webhook to configure.

## What runs by itself

Once `docker compose up -d` is done there is nothing to schedule: the app has
its own scheduler (no cron needed) and Docker restarts it after crashes or
server reboots (`restart: unless-stopped`).

| Job | When |
|---|---|
| Check each source for news and changes | its own interval, set per source in Admin → Fonti (news every 10 min, timetables 30 min, regulations daily, exam board hourly) |
| Send notifications | right after a change is found |
| Deliver held notifications (quiet hours, daily digests) | every minute |
| Back off a source that keeps failing, alert you after 3 failures | automatic |
| Database backup into `/srv/openunifi/backups` | every night at 04:00, last 14 kept |

The backups are plain files on the server, so copying them somewhere else
(another machine, cloud storage) is a normal file copy. To restore one:

```bash
cd /srv/openunifi
docker compose stop openunifi-app
docker compose run --rm --no-deps openunifi-app sh -c \
  "rm -f /data/openunifi.db-wal /data/openunifi.db-shm && cp /data/backups/openunifi-2026-10-13.db /data/openunifi.db"
docker compose up -d
```

## Only when you want to

```bash
cd /srv/openunifi
git pull && docker compose up -d --build     # install a new version
docker compose logs -f openunifi-app         # look at the logs
```

Updates stay manual on purpose: deploying new code automatically could take
the site down without anyone noticing. A source can also be checked
immediately from Admin → Fonti (the refresh button), no terminal needed.

## Traffic stats (optional)

The edge proxy's GoAccess dashboard reads only the Halo log. To get Open Unifi
stats too, give its Caddy block its own `log { output file /var/log/caddy/openunifi-access.log }`
and run a second `goaccess` service on that file (see the edge-caddy README).
