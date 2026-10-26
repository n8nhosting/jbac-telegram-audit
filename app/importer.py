"""Import data/channels.seed.json (+ optional data/probe_report.json) into the database. Idempotent.

CLI:  python -m app.importer data/channels.seed.json [data/probe_report.json] [--db data/audit.db]
HTTP: POST /admin/import (see app/web.py) calls import_seed() with the uploaded files.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import sys
from dataclasses import dataclass

from .db import connect, migrate, now_utc

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "fab": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "septemher": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


@dataclass
class ImportStats:
    contracts: int = 0
    channels: int = 0
    aliases: int = 0
    reg_rows: int = 0
    price_rows: int = 0
    skipped_external: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def resolve_reg_months(sheet_month: str, reg_history: list[dict]) -> list[tuple[str, int]]:
    """'Sep' on the 2026-10 sheet -> 2026-09; a month name >= the sheet month belongs to the previous year."""
    y, m = (int(x) for x in sheet_month.split("-"))
    out = []
    for e in reg_history or []:
        mon = MONTHS.get(str(e.get("month", "")).lower())
        if not mon:
            continue
        year = y if mon < m else y - 1
        out.append((f"{year:04d}-{mon:02d}", int(e["reg"])))
    return out


def channel_kind_and_collector(link_kind: str, probe: dict | None) -> tuple[str, str]:
    if link_kind == "private":
        return "private", "invite"
    if link_kind != "public":
        return "unknown", "none"
    if probe and probe.get("readable"):
        return "public_preview", "preview"
    pk = (probe or {}).get("profile_kind")
    if pk == "user_or_bot":
        return "not_channel", "none"
    if pk in ("channel_no_preview", "restricted_channel"):
        return "public_no_preview", "profile"
    if pk == "group":
        return "group", "profile"
    if pk == "missing":
        return "unknown", "profile"
    return "public_preview", "preview"


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d[\d,]*", str(v))
    return int(m.group(0).replace(",", "")) if m else None


def _key(link: dict) -> str | None:
    if link.get("kind") == "public" and link.get("username"):
        return f"pub:{link['username'].lower()}"
    if link.get("kind") == "private" and link.get("invite_hash"):
        return f"prv:{link['invite_hash']}"
    return None


def import_seed(conn: sqlite3.Connection, seed: dict, probe: dict | None = None) -> ImportStats:
    probe_by_user = {r["username"].lower(): r for r in (probe or {}).get("channels", []) if r.get("username")}
    st = ImportStats()
    now = now_utc()
    seen_channels: set[str] = set()
    with conn:
        for c in seed.get("contracts", []):
            conn.execute(
                """INSERT INTO contracts(sheet_contract_id, month, section, exclusivity, quota_type, quota_posts_per_day,
                       pin_rule, amount_mmk, period_from, period_to, names, admin_accounts, remark_raw, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(sheet_contract_id) DO UPDATE SET
                       month=excluded.month, section=excluded.section, exclusivity=excluded.exclusivity,
                       quota_type=excluded.quota_type, quota_posts_per_day=excluded.quota_posts_per_day,
                       pin_rule=excluded.pin_rule, amount_mmk=excluded.amount_mmk, period_from=excluded.period_from,
                       period_to=excluded.period_to, names=excluded.names, admin_accounts=excluded.admin_accounts,
                       remark_raw=excluded.remark_raw, updated_at=excluded.updated_at
                   WHERE contracts.manual_locked=0""",
                (c["contract_id"], c["month"], c.get("section"), c.get("exclusivity"), c.get("quota_type") or "unknown",
                 c.get("quota_posts_per_day"), c.get("pin_rule") or "none", _num(c.get("amount_mmk")),
                 c.get("period_from"), c.get("period_to"), json.dumps(c.get("names") or [], ensure_ascii=False),
                 json.dumps(c.get("admin_accounts") or [], ensure_ascii=False), c.get("remark_raw"), now, now))
            cid = conn.execute("SELECT id FROM contracts WHERE sheet_contract_id=?", (c["contract_id"],)).fetchone()[0]
            st.contracts += 1

            links = c.get("links") or []
            tme = [l for l in links if _key(l)]
            st.skipped_external += len(links) - len(tme)
            names = c.get("names") or []
            subs = ((c.get("sub_view") or {}).get("subs")) or []
            positional = len(names) == len(tme) and len(tme) > 0
            first_channel_id = None
            for i, l in enumerate(tme):
                key = _key(l)
                probe_row = probe_by_user.get((l.get("username") or "").lower()) if l["kind"] == "public" else None
                kind, collector = channel_kind_and_collector(l["kind"], probe_row)
                title = names[i] if positional else (names[0] if names else None)
                sheet_subs = subs[i] if len(subs) == len(tme) else (subs[0] if len(tme) == 1 and subs else None)
                conn.execute(
                    """INSERT INTO channels(channel_key, kind, username, invite_hash, title, subscribers, collector, created_at, updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(channel_key) DO UPDATE SET
                           kind=excluded.kind,
                           collector=CASE WHEN channels.collector='mtproto' THEN channels.collector ELSE excluded.collector END,
                           username=excluded.username, invite_hash=excluded.invite_hash,
                           title=COALESCE(channels.title, excluded.title),
                           subscribers=COALESCE(channels.subscribers, excluded.subscribers),
                           updated_at=excluded.updated_at
                       WHERE channels.manual_locked=0""",
                    (key, kind, (l.get("username") or None) and l["username"].lower(), l.get("invite_hash"), title,
                     sheet_subs, collector, now, now))
                chid = conn.execute("SELECT id FROM channels WHERE channel_key=?", (key,)).fetchone()[0]
                conn.execute("INSERT OR IGNORE INTO contract_channels(contract_id, channel_id, position) VALUES(?,?,?)",
                             (cid, chid, i))
                if key not in seen_channels:
                    seen_channels.add(key)
                    st.channels += 1
                if first_channel_id is None:
                    first_channel_id = chid

            old_links = [l for l in (c.get("old_links") or []) if _key(l)]
            for l in old_links:
                okey = _key(l)
                if conn.execute("SELECT 1 FROM channel_aliases WHERE contract_id=? AND old_channel_key=?", (cid, okey)).fetchone():
                    continue
                conn.execute("INSERT INTO channel_aliases(channel_id, contract_id, old_title, old_url, old_channel_key, seen_at, source)"
                             " VALUES(?,?,?,?,?,?,?)", (first_channel_id, cid, c.get("old_name"), l.get("url"), okey, now, "sheet"))
                st.aliases += 1
            if not old_links and c.get("old_name"):
                if not conn.execute("SELECT 1 FROM channel_aliases WHERE contract_id=? AND old_channel_key IS NULL AND old_title=?",
                                    (cid, c["old_name"])).fetchone():
                    conn.execute("INSERT INTO channel_aliases(channel_id, contract_id, old_title, old_url, old_channel_key, seen_at, source)"
                                 " VALUES(?,?,?,?,?,?,?)", (first_channel_id, cid, c["old_name"], None, None, now, "sheet"))
                    st.aliases += 1

            for month, reg in resolve_reg_months(c["month"], c.get("reg_history") or []):
                conn.execute("INSERT INTO reg_monthly(contract_id, month, reg) VALUES(?,?,?)"
                             " ON CONFLICT(contract_id, month) DO UPDATE SET reg=excluded.reg", (cid, month, reg))
                st.reg_rows += 1

            note = c.get("price_history_note")
            if note:
                cur = conn.execute("INSERT OR IGNORE INTO price_history(contract_id, month, amount_mmk, note) VALUES(?,?,?,?)",
                                   (cid, c["month"], _num(note), str(note).strip()))
                st.price_rows += cur.rowcount if cur.rowcount > 0 else 0
        conn.execute("INSERT INTO runs(kind, started_at, finished_at, ok, detail) VALUES('import', ?, ?, 1, ?)",
                     (now, now_utc(), json.dumps(st.as_dict())))
    return st


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed")
    ap.add_argument("probe", nargs="?")
    ap.add_argument("--db", default=None)
    a = ap.parse_args(argv)
    from .config import load_settings
    db_path = a.db or load_settings().db_path
    conn = connect(db_path)
    migrate(conn)
    seed = json.loads(pathlib.Path(a.seed).read_text(encoding="utf-8"))
    probe = json.loads(pathlib.Path(a.probe).read_text(encoding="utf-8")) if a.probe else None
    st = import_seed(conn, seed, probe)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"db={db_path} imported: {st.as_dict()}")


if __name__ == "__main__":
    main()
