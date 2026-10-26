"""FastAPI app: Thai exception-first dashboard, JSON API, CSV export, admin import/run endpoints."""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import json
import logging
import pathlib
import re
import secrets
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .alerts import build_summary
from .collector import run_public_collector
from .db import connect, migrate
from .i18n import LANGS, LANG_NAMES, STRINGS, pin_label, resolve_lang, status_label, t as _t
from .importer import import_seed
from .rollup import rollup_date
from .rules import now_local

TEMPLATES = Jinja2Templates(directory=str(pathlib.Path(__file__).parent / "templates"))
FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#172029"/>'
               '<path d="M10 24V8h7a5 5 0 0 1 0 10h-4" fill="none" stroke="#dfe5ea" stroke-width="3" stroke-linecap="round"/>'
               '<circle cx="22" cy="23" r="3" fill="#7cb7ee"/></svg>')
STATUS_ORDER = "CASE r.status WHEN 'missed' THEN 0 WHEN 'invalid' THEN 1 WHEN 'pin_missing' THEN 2 WHEN 'dead' THEN 3 " \
               "WHEN 'unverifiable' THEN 4 WHEN 'waiting' THEN 5 WHEN 'manual' THEN 6 WHEN 'paused' THEN 7 WHEN 'ok' THEN 8 ELSE 9 END"
STATUS_KEYS = ["missed", "invalid", "pin_missing", "unverifiable", "waiting", "ok", "dead", "paused", "manual"]
# severity bands used by the overview: hero bar segments, table group rows and ?status=<band> filters
BANDS = ("action", "unverifiable", "waiting", "other", "ok")
BAND_STATUSES = {"action": ["missed", "invalid", "pin_missing", "dead"], "unverifiable": ["unverifiable"],
                 "waiting": ["waiting"], "other": ["paused", "manual"], "ok": ["ok"]}
_BAND_OF = {st: band for band, sts in BAND_STATUSES.items() for st in sts}
_NOTE_NOT_READABLE = re.compile(r"^(?P<key>\S+) \((?P<collector>[a-z]+)\): not readable$")
_NOTE_SHORT = re.compile(r"^(?P<key>\S+): (?P<q>\d+)/(?P<need>\d+)$")
_NOTE_DEAD = re.compile(r"^(?P<key>\S+): dead$")


def group_of(status: str | None) -> str:
    return _BAND_OF.get(status or "", "other")


def cutoff_info(local_date: str, now: dt.datetime) -> dict:
    """Where `local_date` stands relative to the 23:59 cutoff in `now`'s timezone: open (with time left), closed, or future."""
    day = dt.date.fromisoformat(local_date)
    if day < now.date():
        return {"state": "closed"}
    if day > now.date():
        return {"state": "future"}
    end = dt.datetime.combine(day, dt.time(23, 59), tzinfo=now.tzinfo)
    left = max(0, int((end - now).total_seconds())) // 60
    return {"state": "open", "hours": left // 60, "minutes": left % 60}


def notes_digest(notes_obj: dict | None, lang: str) -> str:
    """One short line for the overview: counts unreadable channels instead of listing their keys, keeps shortfalls by name."""
    if not notes_obj:
        return ""
    unreadable, parts = 0, []
    for note in notes_obj.get("notes") or []:
        if _NOTE_NOT_READABLE.match(note):
            unreadable += 1
            continue
        m = _NOTE_SHORT.match(note)
        if m:
            key = m.group("key")
            parts.append(f"{key.split(':', 1)[1] if ':' in key else key} {m.group('q')}/{m.group('need')}")
            continue
        m = _NOTE_DEAD.match(note)
        if m:
            key = m.group("key")
            parts.append(f"{key.split(':', 1)[1] if ':' in key else key}: {status_label(lang, 'dead')}")
            continue
        parts.append(note)
    if unreadable:
        parts.insert(0, _t(lang, "row.unreadable", n=unreadable))
    return " · ".join(parts)
_security = HTTPBasic(auto_error=False)


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def lang_of(request: Request) -> str:
    return resolve_lang(request.query_params.get("lang"), request.cookies.get("lang"), request.headers.get("accept-language"))


def switch_urls(request: Request) -> dict[str, str]:
    out = {}
    for lang in LANGS:
        q = dict(request.query_params)
        q["lang"] = lang
        out[lang] = f"{request.url.path}?{urlencode(q)}"
    return out


def _remember_lang(resp, request: Request, lang: str):
    if request.query_params.get("lang"):
        resp.set_cookie("lang", lang, max_age=365 * 24 * 3600, samesite="lax")
    return resp


def contracts_for_day(conn: sqlite3.Connection, local_date: str, status: str | None = None, lang: str = "th", tz: str = "Asia/Yangon") -> list[dict]:
    statuses = (BAND_STATUSES.get(status) or [status]) if status else []
    where = f"WHERE r.status IN ({','.join('?' * len(statuses))})" if statuses else ""
    sql = f"""
        SELECT c.id, c.sheet_contract_id, c.names, c.section, c.exclusivity, c.pin_rule, c.quota_type, c.quota_posts_per_day,
               c.amount_mmk, c.admin_accounts, c.period_from, c.period_to,
               r.status, r.required, r.qualified, r.pin_ok, r.notes, r.computed_at,
               (SELECT COUNT(*) FROM contract_channels cc JOIN channels ch ON ch.id=cc.channel_id
                 WHERE cc.contract_id=c.id AND ch.kind<>'not_channel') AS n_channels,
               (SELECT MAX(p.posted_at) FROM posts p JOIN contract_channels cc ON cc.channel_id=p.channel_id
                 WHERE cc.contract_id=c.id AND p.local_date=? AND p.qualifies=1) AS last_post_at,
               (SELECT COUNT(*) FROM daily_rollup r2 WHERE r2.contract_id=c.id AND r2.status='missed'
                 AND r2.local_date >= date(?, '-30 day') AND r2.local_date < ?) AS missed_30d,
               (SELECT reg FROM reg_monthly rm WHERE rm.contract_id=c.id ORDER BY month DESC LIMIT 1) AS last_reg
        FROM contracts c LEFT JOIN daily_rollup r ON r.contract_id=c.id AND r.local_date=?
        {where}
        ORDER BY {STATUS_ORDER}, c.amount_mmk DESC"""
    params = [local_date, local_date, local_date, local_date] + statuses
    out = []
    for r in conn.execute(sql, params):
        d = dict(r)
        d["names_list"] = json.loads(d["names"] or "[]")
        d["admins_list"] = json.loads(d["admin_accounts"] or "[]")
        d["status_th"] = status_label("th", d["status"])
        d["status_label"] = status_label(lang, d["status"])
        d["pin_label"] = pin_label(lang, d["pin_rule"])
        try:
            d["notes_obj"] = json.loads(d["notes"]) if d["notes"] else {"notes": [], "channels": []}
        except ValueError:
            d["notes_obj"] = {"notes": [], "channels": []}
        d["band"] = group_of(d["status"])
        d["digest"] = notes_digest(d["notes_obj"], lang)
        d["last_post_local"] = None
        if d["last_post_at"]:
            try:   # the post is on the selected local day by construction, so the time alone is enough
                d["last_post_local"] = dt.datetime.fromisoformat(d["last_post_at"]).astimezone(ZoneInfo(tz)).strftime("%H:%M")
            except (ValueError, TypeError):
                d["last_post_local"] = d["last_post_at"][11:16]
        out.append(d)
    return out


def contract_detail(conn: sqlite3.Connection, contract_id: int, local_date: str, lang: str = "th", tz: str = "Asia/Yangon") -> dict | None:
    c = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
    if not c:
        return None
    d = dict(c)
    d["names_list"] = json.loads(d["names"] or "[]")
    d["admins_list"] = json.loads(d["admin_accounts"] or "[]")
    d["pin_label"] = pin_label(lang, d["pin_rule"])
    d["channels"] = _rows(conn.execute(
        "SELECT ch.* FROM channels ch JOIN contract_channels cc ON cc.channel_id=ch.id WHERE cc.contract_id=? ORDER BY cc.position", (contract_id,)))
    for ch in d["channels"]:
        ch["url"] = f"https://t.me/{ch['username']}" if ch["username"] else (f"https://t.me/+{ch['invite_hash']}" if ch["invite_hash"] else None)
    since = (dt.date.fromisoformat(local_date) - dt.timedelta(days=7)).isoformat()
    d["posts"] = _rows(conn.execute(
        """SELECT p.*, ch.channel_key FROM posts p JOIN channels ch ON ch.id=p.channel_id
           JOIN contract_channels cc ON cc.channel_id=p.channel_id
           WHERE cc.contract_id=? AND p.local_date BETWEEN ? AND ? ORDER BY p.posted_at DESC LIMIT 200""", (contract_id, since, local_date)))
    d["rollups"] = _rows(conn.execute(
        "SELECT * FROM daily_rollup WHERE contract_id=? AND local_date <= ? ORDER BY local_date DESC LIMIT 31", (contract_id, local_date)))
    for r in d["rollups"]:
        r["status_label"] = status_label(lang, r["status"])
    for p in d["posts"]:
        try:
            p["time_local"] = dt.datetime.fromisoformat(p["posted_at"]).astimezone(ZoneInfo(tz)).strftime("%H:%M")
        except (ValueError, TypeError):
            p["time_local"] = (p.get("posted_at") or "")[11:16]
    d["regs"] = _rows(conn.execute("SELECT month, reg FROM reg_monthly WHERE contract_id=? ORDER BY month DESC", (contract_id,)))
    d["aliases"] = _rows(conn.execute("SELECT * FROM channel_aliases WHERE contract_id=? OR channel_id IN "
                                      "(SELECT channel_id FROM contract_channels WHERE contract_id=?) ORDER BY seen_at DESC", (contract_id, contract_id)))
    d["events"] = _rows(conn.execute("SELECT e.*, ch.channel_key FROM channel_events e LEFT JOIN channels ch ON ch.id=e.channel_id "
                                     "WHERE e.channel_id IN (SELECT channel_id FROM contract_channels WHERE contract_id=?) ORDER BY e.happened_at DESC LIMIT 50", (contract_id,)))
    d["snapshots"] = _rows(conn.execute(
        """SELECT s.channel_id, s.captured_at, s.subscribers FROM snapshots s
           WHERE s.channel_id IN (SELECT channel_id FROM contract_channels WHERE contract_id=?) ORDER BY s.captured_at DESC LIMIT 60""", (contract_id,)))
    d["today"] = next((r for r in d["rollups"] if r["local_date"] == local_date), None)
    if d["today"]:
        try:
            d["today"]["digest"] = notes_digest(json.loads(d["today"]["notes"] or "{}"), lang)
        except ValueError:
            d["today"]["digest"] = ""
    return d


def create_app(settings, conn: sqlite3.Connection | None = None, start_scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Platinum audit", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.conn = conn or connect(settings.db_path)
    migrate(app.state.conn)
    app.state.scheduler = None
    app.state.collector_task = None

    def db() -> sqlite3.Connection:
        return app.state.conn

    def today() -> str:
        return now_local(settings.tz).date().isoformat()

    def auth(credentials: HTTPBasicCredentials | None = Depends(_security)):
        if not settings.dash_password:
            return True
        # compare bytes: compare_digest raises on non-ASCII str, which would turn a typo into a 500
        ok = credentials is not None \
            and secrets.compare_digest(credentials.username.encode("utf-8"), settings.dash_user.encode("utf-8")) \
            and secrets.compare_digest(credentials.password.encode("utf-8"), settings.dash_password.encode("utf-8"))
        if not ok:
            raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": 'Basic realm="audit"'})
        return True

    def parse_date(value: str | None) -> str:
        if not value:
            return today()
        try:
            return dt.date.fromisoformat(value).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    @app.on_event("startup")
    async def _startup():
        if start_scheduler:
            from .scheduler import build_scheduler
            app.state.scheduler = build_scheduler(settings, lambda: connect(settings.db_path))
            app.state.scheduler.start()

    @app.on_event("shutdown")
    async def _shutdown():
        if app.state.scheduler:
            app.state.scheduler.shutdown(wait=False)

    @app.get("/healthz")
    async def healthz():
        conn = db()
        last = {r["kind"]: r["finished_at"] for r in conn.execute(
            "SELECT kind, MAX(finished_at) AS finished_at FROM runs GROUP BY kind")}
        return {"ok": True, "contracts": conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
                "last_runs": last, "mtproto": settings.mtproto_enabled, "alerts": settings.alerts_enabled, "tz": settings.tz}

    def page_context(request: Request, lang: str) -> dict:
        return {"lang": lang, "lang_names": LANG_NAMES, "langs": LANGS, "switch": switch_urls(request),
                "t": lambda key, **kw: _t(lang, key, **kw), "sl": lambda s: status_label(lang, s),
                "status_keys": STATUS_KEYS, "tz": settings.tz}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, date: str | None = None, status: str | None = None, _=Depends(auth)):
        conn = db()
        lang = lang_of(request)
        day = parse_date(date)
        rows = contracts_for_day(conn, day, status or None, lang, settings.tz)
        summary = build_summary(conn, day)
        counts = {k: getattr(summary, k) for k in ("ok", "waiting", "missed", "invalid", "pin_missing", "unverifiable", "dead", "paused", "manual")}
        bands = [{"key": b, "label": _t(lang, f"group.{b}"), "count": sum(counts[s] for s in BAND_STATUSES[b])} for b in BANDS]
        status_list = [{"key": k, "band": group_of(k), "count": counts[k],
                        "label": _t(lang, f"kpi.{k}") if f"kpi.{k}" in STRINGS else status_label(lang, k)} for k in STATUS_KEYS]
        cutoff = cutoff_info(day, now_local(settings.tz))
        if cutoff["state"] == "open":
            cutoff_text = _t(lang, "hero.cutoff_left", h=cutoff["hours"], m=cutoff["minutes"], tz=settings.tz)
        elif cutoff["state"] == "closed":
            cutoff_text = _t(lang, "hero.cutoff_closed", tz=settings.tz)
        else:
            cutoff_text = _t(lang, "hero.cutoff_future")
        n_contracts = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        last_collect = conn.execute("SELECT MAX(finished_at) FROM runs WHERE kind='collector'").fetchone()[0]
        ctx = page_context(request, lang)
        ctx.update({
            "day": day, "prev_day": (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat(),
            "next_day": (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat(), "today": today(),
            "rows": rows, "summary": summary, "counts": counts, "status": status or "",
            "n_contracts": n_contracts, "last_collect": last_collect, "hashtag": settings.hashtag,
            "mtproto": settings.mtproto_enabled, "bands": bands, "status_list": status_list,
            "n_action": bands[0]["count"], "cutoff": cutoff, "cutoff_text": cutoff_text})
        return _remember_lang(TEMPLATES.TemplateResponse(request, "index.html", ctx), request, lang)

    @app.get("/contracts/{contract_id}", response_class=HTMLResponse)
    async def contract_page(request: Request, contract_id: int, date: str | None = None, _=Depends(auth)):
        lang = lang_of(request)
        day = parse_date(date)
        d = contract_detail(db(), contract_id, day, lang, settings.tz)
        if not d:
            raise HTTPException(status_code=404, detail="contract not found")
        ctx = page_context(request, lang)
        ctx.update({"c": d, "day": day})
        return _remember_lang(TEMPLATES.TemplateResponse(request, "contract.html", ctx), request, lang)

    @app.get("/api/summary")
    async def api_summary(date: str | None = None, _=Depends(auth)):
        return build_summary(db(), parse_date(date)).as_dict()

    @app.get("/api/contracts")
    async def api_contracts(request: Request, date: str | None = None, status: str | None = None, _=Depends(auth)):
        rows = contracts_for_day(db(), parse_date(date), status or None, lang_of(request), settings.tz)
        for r in rows:
            r.pop("notes", None)
        return rows

    @app.get("/export.csv")
    async def export_csv(request: Request, _=Depends(auth)):
        q = request.query_params
        lang = lang_of(request)
        d_from, d_to = parse_date(q.get("from")), parse_date(q.get("to"))
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["local_date", "contract", "names", "section", "exclusivity", "pin_rule", "quota_posts_per_day", "amount_mmk",
                    "required", "qualified", "pin_ok", "status", "status_label", "notes"])
        for r in db().execute(
                """SELECT r.local_date, c.sheet_contract_id, c.names, c.section, c.exclusivity, c.pin_rule, c.quota_posts_per_day,
                          c.amount_mmk, r.required, r.qualified, r.pin_ok, r.status, r.notes
                   FROM daily_rollup r JOIN contracts c ON c.id=r.contract_id
                   WHERE r.local_date BETWEEN ? AND ? ORDER BY r.local_date, c.sheet_contract_id""", (d_from, d_to)):
            notes = ""
            try:
                notes = " | ".join(json.loads(r["notes"] or "{}").get("notes", []))
            except ValueError:
                pass
            w.writerow([r["local_date"], r["sheet_contract_id"], " / ".join(json.loads(r["names"] or "[]")), r["section"], r["exclusivity"],
                        r["pin_rule"], r["quota_posts_per_day"], r["amount_mmk"], r["required"], r["qualified"], r["pin_ok"],
                        r["status"], status_label(lang, r["status"]), notes])
        return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="audit_{d_from}_{d_to}.csv"'})

    @app.post("/admin/import")
    async def admin_import(seed: UploadFile = File(...), probe: UploadFile | None = File(None), _=Depends(auth)):
        try:
            seed_obj = json.loads((await seed.read()).decode("utf-8"))
            probe_obj = json.loads((await probe.read()).decode("utf-8")) if probe is not None else None
        except (ValueError, UnicodeDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"invalid JSON: {e}")
        if "contracts" not in seed_obj:
            raise HTTPException(status_code=400, detail="seed must contain 'contracts'")
        st = import_seed(db(), seed_obj, probe_obj)
        return st.as_dict()

    @app.post("/admin/run/{kind}")
    async def admin_run(kind: str, date: str | None = None, _=Depends(auth)):
        conn = db()
        if kind == "rollup":
            day = parse_date(date)
            return {"local_date": day, "rows": rollup_date(conn, day, settings)}
        if kind == "collector":
            from . import collector as _collector
            task = app.state.collector_task
            if _collector.is_running() or (task is not None and not task.done()):
                return JSONResponse({"started": False, "reason": "already running"}, status_code=409)

            async def _run():
                # the scheduler and request handlers each use their own connection; in-memory DBs (tests) share one
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
            return {"started": True}
        if kind == "mtproto":
            if not settings.mtproto_enabled:
                raise HTTPException(status_code=404, detail="MTProto collector not configured (TG_API_ID/TG_API_HASH/TG_SESSION)")
            from .mtproto import run_mtproto_collector
            st = await run_mtproto_collector(conn, settings)
            return st
        raise HTTPException(status_code=404, detail="unknown job")

    @app.get("/favicon.ico")
    async def favicon():
        return Response(content=FAVICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots():
        return "User-agent: *\nDisallow: /\n"

    return app
