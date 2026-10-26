"""Helpers for the HTML management pages: CSRF double-submit cookie, one-shot flash cookie, admin change log.

HTTP Basic credentials are attached by the browser to every request, so a cross-site form could POST here.
Two guards: the `Origin` header (sent by browsers on cross-site POSTs) must match our host when present, and
every form carries the value of the `csrf` cookie, which another site cannot read.
"""
from __future__ import annotations

import base64
import json
import secrets
import sqlite3
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from .db import now_utc

CSRF_COOKIE = "csrf"
FLASH_COOKIE = "flash"


def csrf_token(request: Request) -> str:
    """Token for this browser: the existing cookie, or one minted now (set on the response by ensure_csrf_cookie)."""
    tok = request.cookies.get(CSRF_COOKIE)
    if tok:
        return tok
    if not getattr(request.state, "new_csrf", None):
        request.state.new_csrf = secrets.token_hex(16)
    return request.state.new_csrf


def ensure_csrf_cookie(resp, request: Request) -> None:
    tok = getattr(request.state, "new_csrf", None)
    if tok and not request.cookies.get(CSRF_COOKIE):
        resp.set_cookie(CSRF_COOKIE, tok, max_age=365 * 24 * 3600, samesite="lax", httponly=True)


def check_csrf(request: Request, form_token: str | None) -> bool:
    cookie = request.cookies.get(CSRF_COOKIE)
    return bool(cookie and form_token and secrets.compare_digest(cookie, str(form_token)))


def same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = (request.headers.get("host") or "").lower()
    return urlsplit(origin).netloc.lower() == host


def require_form_post(request: Request, form_token: str | None) -> None:
    if not same_origin(request):
        raise HTTPException(status_code=403, detail="cross-site request blocked")
    if not check_csrf(request, form_token):
        raise HTTPException(status_code=403, detail="invalid or missing csrf token")


def set_flash(resp, text: str, kind: str = "ok") -> None:
    raw = json.dumps({"text": text, "kind": kind}, ensure_ascii=False).encode("utf-8")
    resp.set_cookie(FLASH_COOKIE, base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="), max_age=120, samesite="lax", httponly=True)


def pop_flash(request: Request) -> dict | None:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    try:
        obj = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
        return {"text": str(obj.get("text", "")), "kind": "bad" if obj.get("kind") == "bad" else "ok"}
    except (ValueError, UnicodeDecodeError):
        return None


def log_admin(conn: sqlite3.Connection, user: str | None, action: str, target: str | None = None, detail=None) -> None:
    conn.execute("INSERT INTO admin_log(at, user, action, target, detail) VALUES(?,?,?,?,?)",
                 (now_utc(), user, action, target, json.dumps(detail, ensure_ascii=False) if detail is not None else None))
    conn.commit()
