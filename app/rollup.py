"""Daily rollup: turn posts/snapshots into one status per contract per Asia/Yangon day (docs/SPEC.md §6)."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from .db import now_utc
from .rules import ChannelDay, evaluate_contract_day, now_local as _now_local


def build_channel_days(conn: sqlite3.Connection, contract_id: int, local_date: str) -> list[ChannelDay]:
    rows = conn.execute(
        "SELECT ch.* FROM channels ch JOIN contract_channels cc ON cc.channel_id = ch.id "
        "WHERE cc.contract_id = ? ORDER BY cc.position, ch.id", (contract_id,)).fetchall()
    out: list[ChannelDay] = []
    for ch in rows:
        if ch["kind"] == "not_channel":
            continue
        agg = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(qualifies), 0) AS q FROM posts "
                           "WHERE channel_id=? AND local_date=? AND deleted_seen_at IS NULL", (ch["id"], local_date)).fetchone()
        posts_total, qualified = int(agg["n"]), int(agg["q"])
        if ch["collector"] == "preview":
            readable = ch["last_checked"] is not None and (ch["last_error"] is None or posts_total > 0)
        else:  # profile / invite / mtproto: readable once the MTProto account is a member
            readable = bool(ch["joined"])
        if not readable and posts_total > 0 and conn.execute(
                "SELECT 1 FROM posts WHERE channel_id=? AND local_date=? AND source='mtproto' LIMIT 1", (ch["id"], local_date)).fetchone():
            readable = True
        pinned_today = None
        snaps = conn.execute("SELECT pinned_message_ids FROM pin_snapshots WHERE channel_id=? AND local_date=?",
                             (ch["id"], local_date)).fetchall()
        if snaps:
            pinned: set[int] = set()
            for s in snaps:
                try:
                    pinned |= {int(x) for x in json.loads(s["pinned_message_ids"] or "[]")}
                except (ValueError, TypeError):
                    pass
            ours = {r["message_id"] for r in conn.execute(
                "SELECT message_id FROM posts WHERE channel_id=? AND local_date=? AND qualifies=1", (ch["id"], local_date))}
            pinned_today = bool(pinned & ours)
        renamed = conn.execute("SELECT 1 FROM channel_events WHERE channel_id=? AND event='renamed' AND substr(happened_at,1,10)=? LIMIT 1",
                               (ch["id"], local_date)).fetchone() is not None
        out.append(ChannelDay(ch["channel_key"], ch["kind"], ch["collector"], readable, qualified, posts_total,
                              pinned_today, ch["dead_at"] is not None, renamed))
    return out


def rollup_date(conn: sqlite3.Connection, local_date: str, settings, now_local=None) -> int:
    now_local = now_local or _now_local(settings.tz)
    started = now_utc()
    n = 0
    with conn:
        for c in conn.execute("SELECT * FROM contracts ORDER BY id").fetchall():
            days = build_channel_days(conn, c["id"], local_date)
            v = evaluate_contract_day(dict(c), days, now_local, local_date, settings)
            notes = json.dumps({"notes": v.notes, "channels": [asdict(d) for d in days]}, ensure_ascii=False)
            conn.execute(
                """INSERT INTO daily_rollup(local_date, contract_id, required, qualified, pin_ok, status, notes, computed_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(local_date, contract_id) DO UPDATE SET required=excluded.required, qualified=excluded.qualified,
                       pin_ok=excluded.pin_ok, status=excluded.status, notes=excluded.notes, computed_at=excluded.computed_at""",
                (local_date, c["id"], v.required, v.qualified, None if v.pin_ok is None else int(v.pin_ok), v.status, notes, now_utc()))
            n += 1
        conn.execute("INSERT INTO runs(kind, started_at, finished_at, ok, detail) VALUES('rollup', ?, ?, 1, ?)",
                     (started, now_utc(), json.dumps({"local_date": local_date, "rows": n})))
    return n
