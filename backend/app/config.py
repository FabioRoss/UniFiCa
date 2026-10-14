"""Runtime configuration, read from the environment (see ../.env.example)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENUNIFI_", env_file=".env", extra="ignore")

    # Public base URL, used in notification links, RSS and the Telegram bot.
    public_url: str = "http://localhost:8000"
    site_name: str = "Open Unifi"

    # Everything persistent lives here: the SQLite DB and generated keys.
    data_dir: str = "/data"
    frontend_dist: str = str(Path(__file__).resolve().parents[2] / "frontend" / "dist")

    # Admin login: an email or a username of your choice (not "admin") plus a
    # password, plaintext or a hash from `python -m app.cli hash-password`
    # (format pbkdf2_sha256:...). Both empty = admin panel locked.
    admin_user: str = ""
    admin_password: str = ""

    # Signs admin session cookies. Generated and stored in data_dir when empty.
    secret_key: str = ""
    # Contact for the Web Push service (VAPID "sub" claim).
    vapid_contact: str = "mailto:admin@example.com"

    # Telegram bot (optional). Token from @BotFather.
    telegram_bot_token: str = ""
    # Public channel the bot also posts every update to, e.g. @openunifi_news (optional).
    telegram_channel: str = ""

    # Search engine ownership checks (optional): the content of the
    # google-site-verification / msvalidate.01 meta tags from Search Console
    # and Bing Webmaster Tools. Not needed if you verify the domain by DNS.
    google_site_verification: str = ""
    bing_site_verification: str = ""

    # Scraper behaviour
    scheduler_enabled: bool = True
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36 OpenUnifi/1.0"
    )
    request_delay_seconds: float = 1.0
    max_attachment_mb: int = 25
    timezone: str = "Europe/Rome"

    # Automatic daily database backup (local hour, copies kept). 0 keeps none.
    backup_hour: int = 4
    backup_keep: int = 14

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "openunifi.db"

    @property
    def base_url(self) -> str:
        return self.public_url.rstrip("/")


settings = Settings()
