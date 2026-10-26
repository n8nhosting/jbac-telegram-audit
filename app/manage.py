"""HTML management pages (server-rendered forms) for the sheets in Platinum Marketing Plan.xlsx:
contracts · channels · monthly reg · stop/refund/follow-up lists · import/export · settings.

Registered from create_app() so the routes share its auth dependency, templates and page context.
Every POST goes through forms.require_form_post (CSRF + Origin) and writes an admin_log row.
Rows touched here get manual_locked=1 so a later sheet import does not overwrite them.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .db import now_utc, one
from .forms import log_admin, require_form_post, set_flash
from .i18n import pin_label, t as _t
from .links import channel_key_for, classify_url

SECTIONS = ["only_us", "only_two", "only_three", "only_four", "only_five", "influencer", "unknown"]
CONTRACT_STATUSES = ["active", "paused", "stopped", "refund"]
PIN_KINDS = ["none", "daily", "per_month", "every_days"]
QUOTA_TYPES = ["daily_post", "custom"]
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
