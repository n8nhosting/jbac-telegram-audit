"""Verification rules (docs/SPEC.md §6). Pure functions: no database, no network."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

CUTOFF = dt.time(23, 59)


def tz_of(tz: str) -> ZoneInfo:
    return ZoneInfo(tz)


def now_local(tz: str) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(tz))


def local_date_of(iso_utc: str, tz: str) -> str:
    """ISO timestamp (UTC or with offset) -> calendar day in the audit timezone."""
    d = dt.datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(ZoneInfo(tz)).date().isoformat()


def post_qualifies(post: dict, local_date: str, settings) -> tuple[bool, str]:
    """A post passes when it carries the hashtag (or 'platinum' before enforcement) and a photo/video/link."""
    if post.get("has_sticker"):
        return False, "sticker"
    has_tag = bool(post.get("has_target_hashtag") or post.get("has_tag"))
    legacy = False
    if not has_tag:
        text = (post.get("text") or "").lower()
        if local_date < settings.hashtag_enforced_from and "platinum" in text:
            legacy = True
        else:
            return False, "no_tag"
    if not (post.get("has_media") or post.get("has_link")):
        return False, "no_media_or_link"
    return True, ("legacy_match" if legacy else "ok")


@dataclass
class ChannelDay:
    channel_key: str
    kind: str
    collector: str
    readable: bool
    qualified: int
    posts_total: int
    pinned_today: bool | None = None
    dead: bool = False
    renamed: bool = False


@dataclass
class Verdict:
    status: str            # ok|waiting|missed|invalid|pin_missing|unverifiable|dead|paused|manual
    required: int
    qualified: int
    pin_ok: bool | None
    notes: list[str] = field(default_factory=list)


def _pin_ok(pin_rule: str | None, days: list[ChannelDay]) -> bool | None:
    # only the daily rule can be judged per day; per_month:N / every_days:N need the month's history
    if not pin_rule or pin_rule == "none" or not pin_rule.startswith("daily"):
        return None
    with_data = [d for d in days if d.pinned_today is not None]
    if not with_data:
        return None
    return all(d.pinned_today for d in with_data)


def evaluate_contract_day(contract: dict, days: list[ChannelDay], now_local: dt.datetime, local_date: str, settings) -> Verdict:
    quota = contract.get("quota_posts_per_day")
    days = [d for d in days if d.kind != "not_channel"]
    required = (quota or 0) * len(days)
    qualified = sum(d.qualified for d in days)

    def verdict(status, pin_ok=None, notes=None):
        return Verdict(status, required, qualified, pin_ok, notes or [])

    if (contract.get("status") or "active") != "active":
        return verdict("paused", notes=["contract not active"])
    pf, pt = contract.get("period_from"), contract.get("period_to")
    if (pf and local_date < pf) or (pt and local_date > pt):
        return verdict("paused", notes=["outside contract period"])
    dead = [d for d in days if d.dead]
    if dead:
        return verdict("dead", notes=[f"{d.channel_key}: dead" for d in dead])
    if contract.get("quota_type") != "daily_post" or not quota:
        return verdict("manual", notes=["custom quota — check by hand"])
    if not days:
        return verdict("unverifiable", notes=["no channel linked"])

    readable = [d for d in days if d.readable]
    unreadable = [d for d in days if not d.readable]
    short = [d for d in readable if d.qualified < quota]
    today = now_local.date().isoformat()
    before_cutoff = today < local_date or (today == local_date and now_local.time() < CUTOFF)
    if short:
        notes = [f"{d.channel_key}: {d.qualified}/{quota}" for d in short] + \
                [f"{d.channel_key} ({d.collector}): not readable" for d in unreadable]
        if before_cutoff:
            return verdict("waiting", notes=notes)
        if all(d.posts_total > 0 and d.qualified == 0 for d in short):
            return verdict("invalid", notes=notes)
        return verdict("missed", notes=notes)
    if unreadable:
        return verdict("unverifiable", notes=[f"{d.channel_key} ({d.collector}): not readable" for d in unreadable])
    pin_ok = _pin_ok(contract.get("pin_rule"), days)
    return verdict("pin_missing" if pin_ok is False else "ok", pin_ok)
