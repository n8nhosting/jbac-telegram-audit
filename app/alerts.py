"""Owner alerts over the Telegram Bot API (DM only — the bot is never in any channel)."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass

from .db import now_utc
from .i18n import t

STATUS_FIELDS = ("ok", "waiting", "missed", "invalid", "pin_missing", "unverifiable", "dead", "paused", "manual")


@dataclass
class Summary:
    local_date: str
    total: int = 0
    ok: int = 0
    waiting: int = 0
    missed: int = 0
    invalid: int = 0
    pin_missing: int = 0
    unverifiable: int = 0
    dead: int = 0
    paused: int = 0
    manual: int = 0
    posts: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def build_summary(conn: sqlite3.Connection, local_date: str) -> Summary:
    s = Summary(local_date)
    for r in conn.execute("SELECT status, COUNT(*) AS n FROM daily_rollup WHERE local_date=? GROUP BY status", (local_date,)):
        if r["status"] in STATUS_FIELDS:
            setattr(s, r["status"], int(r["n"]))
        s.total += int(r["n"])
    s.posts = int(conn.execute("SELECT COUNT(*) FROM posts WHERE local_date=? AND qualifies=1", (local_date,)).fetchone()[0])
    return s


def format_alert(s: Summary, kind: str, lang: str = "th", tz: str = "Asia/Yangon") -> str:
    head_key = {"warn": "a.head_warn", "summary": "a.head_summary", "final": "a.head_final"}.get(kind, "a.head_other")
    lines = [t(lang, head_key, d=s.local_date)]
    if kind == "warn":
        lines.append(t(lang, "a.warn_line", n=s.waiting + s.missed, tz=tz))
    lines.append(t(lang, "a.line1", ok=s.ok, waiting=s.waiting, missed=s.missed, invalid=s.invalid, pin=s.pin_missing))
    lines.append(t(lang, "a.line2", u=s.unverifiable, dead=s.dead, paused=s.paused, manual=s.manual))
    lines.append(t(lang, "a.line3", total=s.total, posts=s.posts))
    return "\n".join(lines)


def alert_text(s: Summary, kind: str, langs=("th",), tz: str = "Asia/Yangon") -> str:
    """One block per configured language, separated by a blank line."""
    return "\n\n".join(format_alert(s, kind, lang, tz) for lang in (langs or ("th",)))


async def send_telegram(settings, text: str, client=None) -> bool:
    import httpx
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        r = await client.post(url, json={"chat_id": settings.owner_chat_id, "text": text, "disable_web_page_preview": True})
        return r.status_code == 200
    except httpx.HTTPError:
        return False
    finally:
        if own:
            await client.aclose()


async def maybe_send(conn: sqlite3.Connection, settings, local_date: str, kind: str, sender=None) -> bool:
    """Send one alert of `kind` for `local_date` at most once. Returns True when a message went out."""
    if conn.execute("SELECT 1 FROM alerts WHERE local_date=? AND kind=?", (local_date, kind)).fetchone():
        return False
    if sender is None:
        if not settings.alerts_enabled:
            return False

        async def sender(text):
            return await send_telegram(settings, text)
    text = alert_text(build_summary(conn, local_date), kind, getattr(settings, "alert_langs", ("th",)), settings.tz)
    ok = await sender(text)
    if ok:
        conn.execute("INSERT INTO alerts(local_date, kind, sent_at, text) VALUES(?,?,?,?)", (local_date, kind, now_utc(), text))
        conn.commit()
    return bool(ok)
