"""HTML management pages (server-rendered forms) for the sheets in Platinum Marketing Plan.xlsx:
contracts · channels · monthly reg · stop/refund/follow-up lists · import/export · settings.

Registered from create_app() so the routes share its auth dependency, templates and page context.
Every POST goes through forms.require_form_post (CSRF + Origin) and writes an admin_log row.
Rows touched here get manual_locked=1 so a later sheet import does not overwrite them.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
import sqlite3

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import collector as _collector
from .collector import run_public_collector
from .db import connect, now_utc, one
from .forms import log_admin, require_form_post, set_flash
from .i18n import pin_label, t as _t
from .importer import import_seed
from .links import channel_key_for, classify_url
from .reports import month_days, month_grid, month_summary
from .rollup import rollup_date
from .rules import now_local

SECTIONS = ["only_us", "only_two", "only_three", "only_four", "only_five", "influencer", "unknown"]
CONTRACT_STATUSES = ["active", "paused", "stopped", "refund"]
PIN_KINDS = ["none", "daily", "per_month", "every_days"]
QUOTA_TYPES = ["daily_post", "custom"]
CHANNEL_KINDS = ["public_preview", "public_no_preview", "private", "group", "not_channel", "unknown"]
LIST_EVENTS = ["stop", "refund", "follow_up", "substitute"]          # the Stop list / Refund ch / Follow Up ch / Substitute ch sheets
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------------------------------------------------------------- helpers

def next_manual_id(conn: sqlite3.Connection, month: str) -> str:
    """Manual contracts are numbered YYYY-MM-mNNN so they never collide with rNNN rows from the sheet."""
    n = 0
    for (sid,) in conn.execute("SELECT sheet_contract_id FROM contracts WHERE sheet_contract_id LIKE ?", (f"{month}-m%",)):
        tail = sid.rsplit("m", 1)[1]
        if tail.isdigit():
            n = max(n, int(tail))
    return f"{month}-m{n + 1:03d}"


def _date_or_none(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    return dt.date.fromisoformat(v).isoformat()


def _int_or_none(v: str | None) -> int | None:
    v = re.sub(r"[,\s_]", "", v or "")
    if not v:
        return None
    return int(v)


def parse_contract_form(form) -> tuple[dict, dict]:
    """Validate the contract form. Returns (clean values, errors keyed by field with an i18n key as value)."""
    g = lambda k: (form.get(k) or "").strip()
    errors: dict[str, str] = {}
    data: dict = {}
    data["month"] = g("month")
    if not _MONTH.match(data["month"]):
        errors["month"] = "err.month"
    data["names"] = [n.strip() for n in re.split(r"[\r\n]+", g("names")) if n.strip()]
    if not data["names"]:
        errors["names"] = "err.required"
    data["section"] = g("section") if g("section") in SECTIONS else "unknown"
    try:
        ex = _int_or_none(g("exclusivity"))
        data["exclusivity"] = ex if ex is None or 1 <= ex <= 9 else None
    except ValueError:
        errors["exclusivity"] = "err.number"
    data["quota_type"] = g("quota_type") if g("quota_type") in QUOTA_TYPES else "daily_post"
    try:
        q = _int_or_none(g("quota_posts_per_day"))
        data["quota_posts_per_day"] = q if data["quota_type"] == "daily_post" else None
        if data["quota_type"] == "daily_post" and not q:
            data["quota_posts_per_day"] = 1
    except ValueError:
        errors["quota_posts_per_day"] = "err.number"
    kind = g("pin_kind") if g("pin_kind") in PIN_KINDS else "none"
    try:
        n = _int_or_none(g("pin_n"))
    except ValueError:
        n, errors["pin_n"] = None, "err.number"
    if kind in ("per_month", "every_days"):
        if not n:
            errors["pin_n"] = "err.number"
        data["pin_rule"] = f"{kind}:{n}"
    else:
        data["pin_rule"] = kind
    try:
        data["amount_mmk"] = _int_or_none(g("amount_mmk"))
    except ValueError:
        errors["amount_mmk"] = "err.number"
    for f in ("period_from", "period_to"):
        try:
            data[f] = _date_or_none(g(f))
        except ValueError:
            errors[f] = "err.date"
    admins = [a if a.startswith("@") else f"@{a}" for a in re.split(r"[\s,]+", g("admin_accounts")) if a]
    data["admin_accounts"] = admins
    data["remark_raw"] = g("remark_raw") or None
    data["note"] = g("note") or None
    data["status"] = g("status") if g("status") in CONTRACT_STATUSES else "active"
    return data, errors


def form_values_from_row(row: dict) -> dict:
    """Row → the flat strings the form shows."""
    pin = row.get("pin_rule") or "none"
    kind, _, n = pin.partition(":")
    return {
        "month": row.get("month") or "", "names": "\n".join(json.loads(row.get("names") or "[]")),
        "section": row.get("section") or "unknown", "exclusivity": row.get("exclusivity") or "",
        "quota_type": row.get("quota_type") or "daily_post", "quota_posts_per_day": row.get("quota_posts_per_day") or "",
        "pin_kind": kind if kind in PIN_KINDS else "none", "pin_n": n,
        "amount_mmk": row.get("amount_mmk") or "", "period_from": row.get("period_from") or "", "period_to": row.get("period_to") or "",
        "admin_accounts": " ".join(json.loads(row.get("admin_accounts") or "[]")), "remark_raw": row.get("remark_raw") or "",
        "note": row.get("note") or "", "status": row.get("status") or "active",
    }


def form_values_from_form(form) -> dict:
    keys = ("month", "names", "section", "exclusivity", "quota_type", "quota_posts_per_day", "pin_kind", "pin_n", "amount_mmk",
            "period_from", "period_to", "admin_accounts", "remark_raw", "note", "status")
    return {k: (form.get(k) or "") for k in keys}


def ensure_channel(conn: sqlite3.Connection, info: dict, title: str | None, user: str | None) -> tuple[int | None, bool]:
    """Find or create the channel row for a classified link. Returns (channel_id, created)."""
    key = channel_key_for(info)
    if not key:
        return None, False
    row = one(conn, "SELECT id, title FROM channels WHERE channel_key=?", (key,))
    if row:
        if title and not row["title"]:
            conn.execute("UPDATE channels SET title=?, updated_at=? WHERE id=?", (title, now_utc(), row["id"]))
            conn.commit()
        return row["id"], False
    kind, collector = ("private", "invite") if info["kind"] == "private" else ("public_preview", "preview")
    now = now_utc()
    cur = conn.execute(
        "INSERT INTO channels(channel_key, kind, username, invite_hash, title, collector, manual_locked, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,1,?,?)", (key, kind, info.get("username"), info.get("invite_hash"), title or None, collector, now, now))
    conn.commit()
    log_admin(conn, user, "channel.create", key, {"kind": kind, "title": title})
    return cur.lastrowid, True


def contract_rows(conn: sqlite3.Connection, lang: str, q: str = "", status: str = "", month: str = "") -> list[dict]:
    where, params = [], []
    if q:
        like = f"%{q}%"
        where.append("(c.names LIKE ? OR c.sheet_contract_id LIKE ? OR c.admin_accounts LIKE ? OR c.remark_raw LIKE ?)")
        params += [like, like, like, like]
    if status:
        where.append("c.status=?")
        params.append(status)
    if month:
        where.append("c.month=?")
        params.append(month)
    sql = f"""SELECT c.*, (SELECT COUNT(*) FROM contract_channels cc WHERE cc.contract_id=c.id) AS n_channels
              FROM contracts c {"WHERE " + " AND ".join(where) if where else ""}
              ORDER BY c.month DESC, c.sheet_contract_id"""
    out = []
    for r in conn.execute(sql, params):
        d = dict(r)
        d["names_list"] = json.loads(d["names"] or "[]")
        d["admins_list"] = json.loads(d["admin_accounts"] or "[]")
        d["pin_label"] = pin_label(lang, d["pin_rule"])
        out.append(d)
    return out


def attached_channels(conn: sqlite3.Connection, contract_id: int) -> list[dict]:
    rows = conn.execute("SELECT ch.* FROM channels ch JOIN contract_channels cc ON cc.channel_id=ch.id WHERE cc.contract_id=? ORDER BY cc.position, ch.id",
                        (contract_id,))
    out = []
    for r in rows:
        d = dict(r)
        d["url"] = f"https://t.me/{d['username']}" if d["username"] else (f"https://t.me/+{d['invite_hash']}" if d["invite_hash"] else None)
        out.append(d)
    return out


def _redirect(url: str, flash_text: str | None = None, kind: str = "ok") -> RedirectResponse:
    resp = RedirectResponse(url, status_code=303)
    if flash_text:
        set_flash(resp, flash_text, kind)
    return resp


# ---------------------------------------------------------------- routes

def register(app, *, auth, page_context, lang_of, remember, settings, db, templates):
    def render(request: Request, name: str, nav: str, **ctx):
        lang = lang_of(request)
        full = page_context(request, lang, nav)
        full.update(ctx)
        return remember(templates.TemplateResponse(request, name, full), request, lang)

    # ---- contracts -------------------------------------------------------
    @app.get("/manage/contracts", response_class=HTMLResponse)
    async def contracts_list(request: Request, q: str = "", status: str = "", month: str = "", _=Depends(auth)):
        rows = contract_rows(db(), lang_of(request), q.strip(), status if status in CONTRACT_STATUSES else "", month if _MONTH.match(month) else "")
        return render(request, "manage/contracts.html", "contracts", rows=rows, q=q, status=status, month=month,
                      statuses=CONTRACT_STATUSES, sections=SECTIONS)

    @app.get("/manage/contracts/new", response_class=HTMLResponse)
    async def contract_new(request: Request, _=Depends(auth)):
        today = dt.date.today().isoformat()
        values = {"month": today[:7], "names": "", "section": "only_us", "exclusivity": "1", "quota_type": "daily_post",
                  "quota_posts_per_day": "1", "pin_kind": "daily", "pin_n": "", "amount_mmk": "", "period_from": today, "period_to": "",
                  "admin_accounts": "", "remark_raw": "", "note": "", "status": "active"}
        return render(request, "manage/contract_form.html", "contracts", mode="new", values=values, errors={}, c=None, channels=[],
                      sections=SECTIONS, statuses=CONTRACT_STATUSES, pin_kinds=PIN_KINDS, quota_types=QUOTA_TYPES)

    @app.post("/manage/contracts/new")
    async def contract_create(request: Request, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        data, errors = parse_contract_form(form)
        if errors:
            return render(request, "manage/contract_form.html", "contracts", mode="new", values=form_values_from_form(form), errors=errors,
                          c=None, channels=[], sections=SECTIONS, statuses=CONTRACT_STATUSES, pin_kinds=PIN_KINDS, quota_types=QUOTA_TYPES)
        conn = db()
        sid = next_manual_id(conn, data["month"])
        now = now_utc()
        cur = conn.execute(
            """INSERT INTO contracts(sheet_contract_id, month, section, exclusivity, quota_type, quota_posts_per_day, pin_rule, amount_mmk,
                   period_from, period_to, names, admin_accounts, remark_raw, status, note, manual_locked, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (sid, data["month"], data["section"], data["exclusivity"], data["quota_type"], data["quota_posts_per_day"], data["pin_rule"],
             data["amount_mmk"], data["period_from"], data["period_to"], json.dumps(data["names"], ensure_ascii=False),
             json.dumps(data["admin_accounts"], ensure_ascii=False), data["remark_raw"], data["status"], data["note"], now, now))
        conn.commit()
        log_admin(conn, settings.dash_user, "contract.create", sid, data)
        return _redirect(f"/manage/contracts/{cur.lastrowid}/edit", _t(lang_of(request), "mg.saved_add_channels"))

    def _load_contract(contract_id: int) -> dict:
        row = one(db(), "SELECT * FROM contracts WHERE id=?", (contract_id,))
        if not row:
            raise HTTPException(status_code=404, detail="contract not found")
        return dict(row)

    @app.get("/manage/contracts/{contract_id}/edit", response_class=HTMLResponse)
    async def contract_edit(request: Request, contract_id: int, _=Depends(auth)):
        c = _load_contract(contract_id)
        return render(request, "manage/contract_form.html", "contracts", mode="edit", values=form_values_from_row(c), errors={}, c=c,
                      channels=attached_channels(db(), contract_id), sections=SECTIONS, statuses=CONTRACT_STATUSES, pin_kinds=PIN_KINDS,
                      quota_types=QUOTA_TYPES)

    @app.post("/manage/contracts/{contract_id}/edit")
    async def contract_update(request: Request, contract_id: int, _=Depends(auth)):
        c = _load_contract(contract_id)
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        data, errors = parse_contract_form(form)
        if errors:
            return render(request, "manage/contract_form.html", "contracts", mode="edit", values=form_values_from_form(form), errors=errors, c=c,
                          channels=attached_channels(db(), contract_id), sections=SECTIONS, statuses=CONTRACT_STATUSES, pin_kinds=PIN_KINDS,
                          quota_types=QUOTA_TYPES)
        conn = db()
        conn.execute(
            """UPDATE contracts SET month=?, section=?, exclusivity=?, quota_type=?, quota_posts_per_day=?, pin_rule=?, amount_mmk=?,
                   period_from=?, period_to=?, names=?, admin_accounts=?, remark_raw=?, status=?, note=?, manual_locked=1, updated_at=?
               WHERE id=?""",
            (data["month"], data["section"], data["exclusivity"], data["quota_type"], data["quota_posts_per_day"], data["pin_rule"],
             data["amount_mmk"], data["period_from"], data["period_to"], json.dumps(data["names"], ensure_ascii=False),
             json.dumps(data["admin_accounts"], ensure_ascii=False), data["remark_raw"], data["status"], data["note"], now_utc(), contract_id))
        conn.commit()
        log_admin(conn, settings.dash_user, "contract.update", c["sheet_contract_id"], data)
        return _redirect(f"/manage/contracts/{contract_id}/edit", _t(lang_of(request), "mg.saved"))

    @app.post("/manage/contracts/{contract_id}/channels/add")
    async def contract_add_channel(request: Request, contract_id: int, _=Depends(auth)):
        c = _load_contract(contract_id)
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        lang = lang_of(request)
        info = classify_url(form.get("url"))
        conn = db()
        chid, created = ensure_channel(conn, info, (form.get("title") or "").strip() or None, settings.dash_user)
        if chid is None:
            return _redirect(f"/manage/contracts/{contract_id}/edit", _t(lang, "mg.bad_link"), "bad")
        pos = one(conn, "SELECT COALESCE(MAX(position),-1)+1 AS p FROM contract_channels WHERE contract_id=?", (contract_id,))["p"]
        conn.execute("INSERT OR IGNORE INTO contract_channels(contract_id, channel_id, position) VALUES(?,?,?)", (contract_id, chid, pos))
        conn.execute("UPDATE contracts SET manual_locked=1, updated_at=? WHERE id=?", (now_utc(), contract_id))
        conn.commit()
        log_admin(conn, settings.dash_user, "contract.attach", c["sheet_contract_id"], {"channel_id": chid, "created": created, "url": info.get("url")})
        return _redirect(f"/manage/contracts/{contract_id}/edit", _t(lang, "mg.channel_added" if created else "mg.channel_attached"))

    # ---- channels --------------------------------------------------------
    def _channel_rows(conn, q: str = "", kind: str = "", dead: bool = False) -> list[dict]:
        where, params = [], []
        if q:
            like = f"%{q}%"
            where.append("(ch.channel_key LIKE ? OR ch.title LIKE ? OR ch.title_observed LIKE ? OR ch.username LIKE ?)")
            params += [like, like, like, like]
        if kind:
            where.append("ch.kind=?")
            params.append(kind)
        if dead:
            where.append("ch.dead_at IS NOT NULL")
        sql = f"""SELECT ch.*, (SELECT GROUP_CONCAT(c.sheet_contract_id, ', ') FROM contract_channels cc JOIN contracts c ON c.id=cc.contract_id
                                WHERE cc.channel_id=ch.id) AS contracts_txt,
                         (SELECT COUNT(*) FROM contract_channels cc WHERE cc.channel_id=ch.id) AS n_contracts
                  FROM channels ch {"WHERE " + " AND ".join(where) if where else ""}
                  ORDER BY (ch.dead_at IS NOT NULL) DESC, ch.last_error IS NOT NULL DESC, ch.title_observed, ch.title, ch.channel_key"""
        out = []
        for r in conn.execute(sql, params):
            d = dict(r)
            d["url"] = f"https://t.me/{d['username']}" if d["username"] else (f"https://t.me/+{d['invite_hash']}" if d["invite_hash"] else None)
            out.append(d)
        return out

    def _load_channel(channel_id: int) -> dict:
        row = one(db(), "SELECT * FROM channels WHERE id=?", (channel_id,))
        if not row:
            raise HTTPException(status_code=404, detail="channel not found")
        d = dict(row)
        d["url"] = f"https://t.me/{d['username']}" if d["username"] else (f"https://t.me/+{d['invite_hash']}" if d["invite_hash"] else None)
        return d

    def _contract_options(conn) -> list[dict]:
        return [{"id": r["id"], "label": f"{r['sheet_contract_id']} · {' / '.join(json.loads(r['names'] or '[]'))}"}
                for r in conn.execute("SELECT id, sheet_contract_id, names FROM contracts ORDER BY month DESC, sheet_contract_id")]

    @app.get("/manage/channels", response_class=HTMLResponse)
    async def channels_list(request: Request, q: str = "", kind: str = "", dead: str = "", _=Depends(auth)):
        rows = _channel_rows(db(), q.strip(), kind if kind in CHANNEL_KINDS else "", dead == "1")
        return render(request, "manage/channels.html", "channels", rows=rows, q=q, kind=kind, dead=dead == "1", kinds=CHANNEL_KINDS)

    @app.get("/manage/channels/new", response_class=HTMLResponse)
    async def channel_new(request: Request, contract_id: int | None = None, _=Depends(auth)):
        return render(request, "manage/channel_form.html", "channels", mode="new", ch=None,
                      values={"url": "", "title": "", "note": "", "contract_id": contract_id or ""}, errors={},
                      contracts=_contract_options(db()), linked=[])

    @app.post("/manage/channels/new")
    async def channel_create(request: Request, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        lang = lang_of(request)
        values = {k: (form.get(k) or "").strip() for k in ("url", "title", "note", "contract_id")}
        info = classify_url(values["url"])
        if not channel_key_for(info):
            return render(request, "manage/channel_form.html", "channels", mode="new", ch=None, values=values,
                          errors={"url": "mg.bad_link"}, contracts=_contract_options(db()), linked=[])
        conn = db()
        chid, created = ensure_channel(conn, info, values["title"] or None, settings.dash_user)
        if values["note"]:
            conn.execute("UPDATE channels SET note=?, manual_locked=1 WHERE id=?", (values["note"], chid))
        if values["contract_id"].isdigit() and one(conn, "SELECT 1 FROM contracts WHERE id=?", (int(values["contract_id"]),)):
            cid = int(values["contract_id"])
            pos = one(conn, "SELECT COALESCE(MAX(position),-1)+1 AS p FROM contract_channels WHERE contract_id=?", (cid,))["p"]
            conn.execute("INSERT OR IGNORE INTO contract_channels(contract_id, channel_id, position) VALUES(?,?,?)", (cid, chid, pos))
            conn.execute("UPDATE contracts SET manual_locked=1, updated_at=? WHERE id=?", (now_utc(), cid))
        conn.commit()
        return _redirect(f"/manage/channels/{chid}/edit", _t(lang, "mg.channel_added" if created else "mg.channel_attached"))

    @app.get("/manage/channels/{channel_id}/edit", response_class=HTMLResponse)
    async def channel_edit(request: Request, channel_id: int, _=Depends(auth)):
        ch = _load_channel(channel_id)
        conn = db()
        linked = [dict(r) for r in conn.execute(
            "SELECT c.id, c.sheet_contract_id, c.names FROM contracts c JOIN contract_channels cc ON cc.contract_id=c.id WHERE cc.channel_id=?", (channel_id,))]
        for l in linked:
            l["names_list"] = json.loads(l["names"] or "[]")
        return render(request, "manage/channel_form.html", "channels", mode="edit", ch=ch,
                      values={"url": ch["url"] or "", "title": ch["title"] or "", "note": ch["note"] or "", "contract_id": ""}, errors={},
                      contracts=_contract_options(conn), linked=linked)

    @app.post("/manage/channels/{channel_id}/edit")
    async def channel_update(request: Request, channel_id: int, _=Depends(auth)):
        ch = _load_channel(channel_id)
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        lang = lang_of(request)
        values = {k: (form.get(k) or "").strip() for k in ("url", "title", "note", "contract_id")}
        conn = db()
        info = classify_url(values["url"])
        new_key = channel_key_for(info)
        errors = {}
        if not new_key:
            errors["url"] = "mg.bad_link"
        elif new_key != ch["channel_key"] and one(conn, "SELECT 1 FROM channels WHERE channel_key=?", (new_key,)):
            errors["url"] = "mg.link_taken"
        if errors:
            linked = [dict(r) for r in conn.execute(
                "SELECT c.id, c.sheet_contract_id, c.names FROM contracts c JOIN contract_channels cc ON cc.contract_id=c.id WHERE cc.channel_id=?", (channel_id,))]
            for l in linked:
                l["names_list"] = json.loads(l["names"] or "[]")
            return render(request, "manage/channel_form.html", "channels", mode="edit", ch=ch, values=values, errors=errors,
                          contracts=_contract_options(conn), linked=linked)
        now = now_utc()
        if new_key != ch["channel_key"]:
            # the link moved: remember the old one, and start history afresh (message ids belong to the old channel)
            kind, collector = ("private", "invite") if info["kind"] == "private" else ("public_preview", "preview")
            conn.execute("INSERT INTO channel_aliases(channel_id, contract_id, old_title, old_url, old_channel_key, seen_at, source) VALUES(?,?,?,?,?,?,?)",
                         (channel_id, None, ch["title_observed"] or ch["title"], ch["url"], ch["channel_key"], now, "manual"))
            conn.execute("""UPDATE channels SET channel_key=?, kind=?, collector=?, username=?, invite_hash=?, tg_peer_id=NULL, title_observed=NULL,
                               joined=0, join_requested_at=NULL, dead_misses=0, dead_at=NULL, last_message_id=NULL, last_checked=NULL, last_error=NULL
                            WHERE id=?""", (new_key, kind, collector, info.get("username"), info.get("invite_hash"), channel_id))
        conn.execute("UPDATE channels SET title=?, note=?, manual_locked=1, updated_at=? WHERE id=?",
                     (values["title"] or None, values["note"] or None, now, channel_id))
        if values["contract_id"].isdigit() and one(conn, "SELECT 1 FROM contracts WHERE id=?", (int(values["contract_id"]),)):
            cid = int(values["contract_id"])
            pos = one(conn, "SELECT COALESCE(MAX(position),-1)+1 AS p FROM contract_channels WHERE contract_id=?", (cid,))["p"]
            conn.execute("INSERT OR IGNORE INTO contract_channels(contract_id, channel_id, position) VALUES(?,?,?)", (cid, channel_id, pos))
        conn.commit()
        log_admin(conn, settings.dash_user, "channel.update", new_key, {"from": ch["channel_key"], "title": values["title"], "note": values["note"]})
        return _redirect(f"/manage/channels/{channel_id}/edit", _t(lang, "mg.saved"))

    @app.post("/manage/channels/{channel_id}/revive")
    async def channel_revive(request: Request, channel_id: int, _=Depends(auth)):
        ch = _load_channel(channel_id)
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        conn = db()
        conn.execute("UPDATE channels SET dead_at=NULL, dead_misses=0, last_error=NULL, updated_at=? WHERE id=?", (now_utc(), channel_id))
        conn.commit()
        log_admin(conn, settings.dash_user, "channel.revive", ch["channel_key"])
        return _redirect(f"/manage/channels/{channel_id}/edit", _t(lang_of(request), "mg.revived"))

    # ---- monthly reg grid ------------------------------------------------
    def _months_ending(to: str, n: int) -> list[str]:
        y, m = int(to[:4]), int(to[5:7])
        out = []
        for _ in range(n):
            out.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        return list(reversed(out))

    def _reg_grid(conn, months: list[str]) -> list[dict]:
        regs = {}
        for r in conn.execute("SELECT contract_id, month, reg FROM reg_monthly WHERE month BETWEEN ? AND ?", (months[0], months[-1])):
            regs[(r["contract_id"], r["month"])] = r["reg"]
        rows = []
        for c in conn.execute("SELECT id, sheet_contract_id, names, status, amount_mmk FROM contracts ORDER BY "
                              "CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END, month DESC, sheet_contract_id"):
            rows.append({"id": c["id"], "sheet_contract_id": c["sheet_contract_id"], "names_list": json.loads(c["names"] or "[]"),
                         "status": c["status"], "amount_mmk": c["amount_mmk"],
                         "cells": [{"month": mth, "value": regs.get((c["id"], mth))} for mth in months],
                         "total": sum(v for (cid, _), v in regs.items() if cid == c["id"])})
        return rows

    def _reg_params(to: str, months: str) -> tuple[str, int]:
        to = to if _MONTH.match(to or "") else dt.date.today().strftime("%Y-%m")
        n = int(months) if (months or "").isdigit() and 1 <= int(months) <= 24 else 6
        return to, n

    @app.get("/manage/regs", response_class=HTMLResponse)
    async def regs_page(request: Request, to: str = "", months: str = "", _=Depends(auth)):
        to, n = _reg_params(to, months)
        cols = _months_ending(to, n)
        return render(request, "manage/regs.html", "regs", months=cols, rows=_reg_grid(db(), cols), to=to, n=n, errors=[])

    @app.post("/manage/regs")
    async def regs_save(request: Request, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        to, n = _reg_params(form.get("to") or "", form.get("months") or "")
        cols = _months_ending(to, n)
        conn = db()
        upserts, deletes, errors = [], [], []
        for key, raw in form.multi_items():
            m = re.fullmatch(r"reg-(\d+)-(\d{4}-\d{2})", key)
            if not m:
                continue
            cid, month, val = int(m.group(1)), m.group(2), (raw or "").strip()
            if not val:
                continue
            if val == "-":
                deletes.append((cid, month))
                continue
            try:
                upserts.append((cid, month, int(re.sub(r"[,\s]", "", val))))
            except ValueError:
                errors.append(f"{month}: {val}")
        if errors:
            return render(request, "manage/regs.html", "regs", months=cols, rows=_reg_grid(conn, cols), to=to, n=n, errors=errors)
        with conn:
            for cid, month, reg in upserts:
                conn.execute("INSERT INTO reg_monthly(contract_id, month, reg) VALUES(?,?,?) ON CONFLICT(contract_id, month) DO UPDATE SET reg=excluded.reg",
                             (cid, month, reg))
            for cid, month in deletes:
                conn.execute("DELETE FROM reg_monthly WHERE contract_id=? AND month=?", (cid, month))
        log_admin(conn, settings.dash_user, "reg.save", to, {"upserts": len(upserts), "deletes": len(deletes)})
        return _redirect(f"/manage/regs?to={to}&months={n}", _t(lang_of(request), "mg.regs_saved", n=len(upserts) + len(deletes)))

    # ---- stop / refund / follow-up / substitute lists ---------------------
    def _list_rows(conn, kind: str = "") -> list[dict]:
        where = "WHERE e.event IN ('stop','refund','follow_up','substitute')" + (" AND e.event=?" if kind else "")
        rows = conn.execute(f"""SELECT e.*, c.sheet_contract_id, c.names, c.status AS contract_status, ch.channel_key
                                FROM channel_events e LEFT JOIN contracts c ON c.id=e.contract_id LEFT JOIN channels ch ON ch.id=e.channel_id
                                {where} ORDER BY e.happened_at DESC, e.id DESC LIMIT 500""", (kind,) if kind else ())
        out = []
        for r in rows:
            d = dict(r)
            d["names_list"] = json.loads(d["names"] or "[]")
            out.append(d)
        return out

    def _list_form_defaults() -> dict:
        return {"contract_id": "", "event": "stop", "happened_at": dt.date.today().isoformat(), "amount_mmk": "", "note": ""}

    @app.get("/manage/lists", response_class=HTMLResponse)
    async def lists_page(request: Request, kind: str = "", _=Depends(auth)):
        kind = kind if kind in LIST_EVENTS else ""
        return render(request, "manage/lists.html", "lists", rows=_list_rows(db(), kind), kind=kind, kinds=LIST_EVENTS,
                      contracts=_contract_options(db()), values=_list_form_defaults(), errors={})

    @app.post("/manage/lists/add")
    async def lists_add(request: Request, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        values = {k: (form.get(k) or "").strip() for k in ("contract_id", "event", "happened_at", "amount_mmk", "note")}
        conn = db()
        errors = {}
        if values["event"] not in LIST_EVENTS:
            errors["event"] = "err.required"
        cid = int(values["contract_id"]) if values["contract_id"].isdigit() else None
        c = one(conn, "SELECT id, sheet_contract_id FROM contracts WHERE id=?", (cid,)) if cid else None
        if not c:
            errors["contract_id"] = "err.required"
        try:
            when = _date_or_none(values["happened_at"]) or dt.date.today().isoformat()
        except ValueError:
            errors["happened_at"] = "err.date"
        try:
            amount = _int_or_none(values["amount_mmk"])
        except ValueError:
            errors["amount_mmk"] = "err.number"
        if errors:
            return render(request, "manage/lists.html", "lists", rows=_list_rows(conn), kind="", kinds=LIST_EVENTS,
                          contracts=_contract_options(conn), values=values, errors=errors)
        with conn:
            conn.execute("INSERT INTO channel_events(channel_id, contract_id, event, happened_at, amount_mmk, note) VALUES(NULL,?,?,?,?,?)",
                         (c["id"], values["event"], f"{when}T00:00:00+00:00", amount, values["note"] or None))
            new_status = {"stop": "stopped", "refund": "refund"}.get(values["event"])
            if new_status:
                conn.execute("UPDATE contracts SET status=?, manual_locked=1, updated_at=? WHERE id=?", (new_status, now_utc(), c["id"]))
            else:
                conn.execute("UPDATE contracts SET manual_locked=1, updated_at=? WHERE id=?", (now_utc(), c["id"]))
        log_admin(conn, settings.dash_user, "list.add", c["sheet_contract_id"], {"event": values["event"], "amount": amount, "note": values["note"]})
        return _redirect(f"/manage/lists?kind={values['event']}", _t(lang_of(request), "mg.saved"))

    @app.post("/manage/lists/{event_id}/delete")
    async def lists_delete(request: Request, event_id: int, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        conn = db()
        ev = one(conn, "SELECT e.*, c.sheet_contract_id FROM channel_events e LEFT JOIN contracts c ON c.id=e.contract_id WHERE e.id=?", (event_id,))
        if not ev:
            raise HTTPException(status_code=404, detail="event not found")
        conn.execute("DELETE FROM channel_events WHERE id=?", (event_id,))
        conn.commit()
        log_admin(conn, settings.dash_user, "list.delete", ev["sheet_contract_id"], {"event": ev["event"], "happened_at": ev["happened_at"]})
        return _redirect("/manage/lists", _t(lang_of(request), "mg.list_deleted"))

    # ---- monthly report ---------------------------------------------------
    def _shift_month(month: str, delta: int) -> str:
        y, m = int(month[:4]), int(month[5:7]) + delta
        while m < 1:
            y, m = y - 1, m + 12
        while m > 12:
            y, m = y + 1, m - 12
        return f"{y:04d}-{m:02d}"

    @app.get("/reports/month", response_class=HTMLResponse)
    async def report_month(request: Request, month: str = "", _=Depends(auth)):
        today = now_local(settings.tz).date()
        month = month if _MONTH.match(month or "") else today.strftime("%Y-%m")
        conn = db()
        days = month_days(month)
        return render(request, "reports/month.html", "reports", month=month, days=days, summary=month_summary(conn, month),
                      rows=month_grid(conn, month), prev_month=_shift_month(month, -1), next_month=_shift_month(month, 1),
                      today=today.isoformat(), day_from=days[0], day_to=days[-1])

    # ---- import / export / runs -------------------------------------------
    def _runs(conn, n: int = 20) -> list[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,))]

    @app.get("/manage/data", response_class=HTMLResponse)
    async def data_page(request: Request, _=Depends(auth)):
        today = now_local(settings.tz).date().isoformat()
        task = app.state.collector_task
        running = _collector.is_running() or (task is not None and not task.done())
        return render(request, "manage/data.html", "data", runs=_runs(db()), today=today, month_start=today[:8] + "01",
                      collector_running=running, mtproto=settings.mtproto_enabled)

    @app.post("/manage/data/import")
    async def data_import(request: Request, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        lang = lang_of(request)
        seed_file, probe_file = form.get("seed"), form.get("probe")
        try:
            if seed_file is None or not hasattr(seed_file, "read"):
                raise ValueError("seed file missing")
            seed_obj = json.loads((await seed_file.read()).decode("utf-8"))
            probe_obj = None
            if probe_file is not None and hasattr(probe_file, "read"):
                raw = await probe_file.read()
                probe_obj = json.loads(raw.decode("utf-8")) if raw else None
            if "contracts" not in seed_obj:
                raise ValueError("seed must contain 'contracts'")
        except (ValueError, UnicodeDecodeError) as e:
            return _redirect("/manage/data", _t(lang, "dt.import_failed", err=str(e)[:120]), "bad")
        st = import_seed(db(), seed_obj, probe_obj)
        log_admin(db(), settings.dash_user, "data.import", seed_obj.get("source_sheet"), st.as_dict())
        return _redirect("/manage/data", _t(lang, "dt.imported", c=st.contracts, ch=st.channels, a=st.aliases))

    @app.post("/manage/data/run/{kind}")
    async def data_run(request: Request, kind: str, _=Depends(auth)):
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        lang = lang_of(request)
        conn = db()
        if kind == "rollup":
            day = (form.get("date") or "").strip() or now_local(settings.tz).date().isoformat()
            try:
                day = dt.date.fromisoformat(day).isoformat()
            except ValueError:
                return _redirect("/manage/data", _t(lang, "err.date"), "bad")
            n = rollup_date(conn, day, settings)
            log_admin(conn, settings.dash_user, "data.rollup", day, {"rows": n})
            return _redirect("/manage/data", _t(lang, "dt.rollup_done", d=day, n=n))
        if kind == "collector":
            task = app.state.collector_task
            if _collector.is_running() or (task is not None and not task.done()):
                return _redirect("/manage/data", _t(lang, "dt.collector_busy"), "bad")

            async def _run():
                own = settings.db_path != ":memory:"
                c = connect(settings.db_path) if own else conn
                try:
                    await run_public_collector(c, settings)
                finally:
                    if own:
                        c.close()
            task = asyncio.create_task(_run())
            task.add_done_callback(lambda t: t.exception() and logging.getLogger("audit.web").error("collector task failed: %r", t.exception()))
            app.state.collector_task = task
            log_admin(conn, settings.dash_user, "data.collector", None)
            return _redirect("/manage/data", _t(lang, "dt.collector_started"))
        if kind == "mtproto":
            if not settings.mtproto_enabled:
                return _redirect("/manage/data", _t(lang, "dt.mtproto_off"), "bad")
            from .mtproto import run_mtproto_collector
            st = await run_mtproto_collector(conn, settings)
            log_admin(conn, settings.dash_user, "data.mtproto", None, st)
            return _redirect("/manage/data", _t(lang, "dt.mtproto_done"))
        raise HTTPException(status_code=404, detail="unknown job")

    # ---- settings & status --------------------------------------------------
    def _mask(v) -> str | None:
        if not v:
            return None
        s = str(v)
        return "••••" + s[-2:] if len(s) > 4 else "••••"

    @app.get("/manage/settings", response_class=HTMLResponse)
    async def settings_page(request: Request, _=Depends(auth)):
        conn = db()
        s = settings
        items = [
            ("DB_PATH", s.db_path, False), ("AUDIT_TZ", s.tz, False), ("HASHTAG", s.hashtag, False),
            ("HASHTAG_ENFORCED_FROM", s.hashtag_enforced_from, False), ("DASH_USER", s.dash_user, False),
            ("DASH_PASSWORD", _mask(s.dash_password), True), ("COLLECTOR_INTERVAL_MIN", s.collector_interval_min, False),
            ("FETCH_DELAY_MIN / MAX", f"{s.fetch_delay_min} / {s.fetch_delay_max}", False),
            ("BOT_TOKEN", _mask(s.bot_token), True), ("OWNER_CHAT_ID", s.owner_chat_id, False), ("ALERT_LANGS", ",".join(s.alert_langs), False),
            ("TG_API_ID", s.tg_api_id, False), ("TG_API_HASH", _mask(s.tg_api_hash), True), ("TG_SESSION", _mask(s.tg_session), True),
            ("MAX_JOINS_PER_RUN", s.max_joins_per_run, False),
        ]
        jobs = []
        sched = getattr(app.state, "scheduler", None)
        if sched:
            for j in sched.get_jobs():
                nxt = getattr(j, "next_run_time", None)
                label = (j.name or "").rsplit(".", 1)[-1].replace("job_", "")      # build_scheduler.<locals>.job_rollup → rollup
                jobs.append({"name": label, "next": nxt})
        health = {
            "contracts": conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
            "channels": conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0],
            "posts": conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            "rollups": conn.execute("SELECT COUNT(*) FROM daily_rollup").fetchone()[0],
            "db_mb": round(os.path.getsize(s.db_path) / 1048576, 1) if s.db_path != ":memory:" and os.path.exists(s.db_path) else None,
        }
        log = [dict(r) for r in conn.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT 50")]
        return render(request, "manage/settings.html", "settings", items=items, jobs=jobs, health=health, log=log, runs=_runs(conn, 10),
                      mtproto=s.mtproto_enabled, alerts=s.alerts_enabled)

    @app.post("/manage/contracts/{contract_id}/channels/{channel_id}/detach")
    async def contract_detach_channel(request: Request, contract_id: int, channel_id: int, _=Depends(auth)):
        c = _load_contract(contract_id)
        form = await request.form()
        require_form_post(request, form.get("csrf"))
        conn = db()
        conn.execute("DELETE FROM contract_channels WHERE contract_id=? AND channel_id=?", (contract_id, channel_id))
        conn.execute("UPDATE contracts SET manual_locked=1, updated_at=? WHERE id=?", (now_utc(), contract_id))
        conn.commit()
        log_admin(conn, settings.dash_user, "contract.detach", c["sheet_contract_id"], {"channel_id": channel_id})
        return _redirect(f"/manage/contracts/{contract_id}/edit", _t(lang_of(request), "mg.channel_detached"))
