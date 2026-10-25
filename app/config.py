"""Settings come only from environment variables (Coolify secrets); nothing here reads files."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/audit.db"
    tz: str = "Asia/Yangon"
    hashtag: str = "#platinumclubmm"
    hashtag_enforced_from: str = "2026-11-01"      # before this local date, 'platinum' in text counts as legacy_match
    dash_user: str = "admin"
    dash_password: str | None = None
    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_session: str | None = None                   # Telethon StringSession made locally with tools/tg_login.py
    bot_token: str | None = None
    owner_chat_id: str | None = None
    fetch_delay_min: float = 1.5
    fetch_delay_max: float = 2.5
    collector_interval_min: int = 30
    public_base_url: str | None = None
    max_joins_per_run: int = 3
    alert_langs: tuple[str, ...] = ("th",)         # languages of the owner DM, in order (th / en / my)

    @property
    def mtproto_enabled(self) -> bool:
        return bool(self.tg_api_id and self.tg_api_hash and self.tg_session)

    @property
    def alerts_enabled(self) -> bool:
        return bool(self.bot_token and self.owner_chat_id)


def _opt(env: Mapping[str, str], key: str) -> str | None:
    v = env.get(key)
    v = v.strip() if isinstance(v, str) else None
    return v or None


def _int(env, key, default=None):
    v = _opt(env, key)
    return int(v) if v is not None else default


def _float(env, key, default):
    v = _opt(env, key)
    return float(v) if v is not None else default


def _langs(env) -> tuple[str, ...]:
    raw = _opt(env, "ALERT_LANGS") or "th"
    out = []
    for part in raw.split(","):
        p = part.strip().lower()
        if p in ("th", "en", "my") and p not in out:
            out.append(p)
    return tuple(out) or ("th",)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        alert_langs=_langs(env),
        db_path=_opt(env, "DB_PATH") or "data/audit.db",
        tz=_opt(env, "AUDIT_TZ") or "Asia/Yangon",
        hashtag=(_opt(env, "HASHTAG") or "#platinumclubmm").lower(),
        hashtag_enforced_from=_opt(env, "HASHTAG_ENFORCED_FROM") or "2026-11-01",
        dash_user=_opt(env, "DASH_USER") or "admin",
        dash_password=_opt(env, "DASH_PASSWORD"),
        tg_api_id=_int(env, "TG_API_ID"),
        tg_api_hash=_opt(env, "TG_API_HASH"),
        tg_session=_opt(env, "TG_SESSION"),
        bot_token=_opt(env, "BOT_TOKEN"),
        owner_chat_id=_opt(env, "OWNER_CHAT_ID"),
        fetch_delay_min=_float(env, "FETCH_DELAY_MIN", 1.5),
        fetch_delay_max=_float(env, "FETCH_DELAY_MAX", 2.5),
        collector_interval_min=_int(env, "COLLECTOR_INTERVAL_MIN", 30),
        public_base_url=_opt(env, "PUBLIC_BASE_URL"),
        max_joins_per_run=_int(env, "MAX_JOINS_PER_RUN", 3),
    )
