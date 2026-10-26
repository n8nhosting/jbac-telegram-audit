"""CSRF double-submit, flash cookie and admin log helpers used by the HTML management pages."""
import unittest

from fastapi import HTTPException
from fastapi.responses import Response
from starlette.requests import Request

from app.db import connect, migrate, one
from app.forms import (check_csrf, csrf_token, ensure_csrf_cookie, log_admin, pop_flash, require_form_post,
                       same_origin, set_flash)


def _request(headers: dict | None = None, host: str = "audit.jbacteam.com") -> Request:
    raw = [(b"host", host.encode())] + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "POST", "path": "/manage/x", "query_string": b"", "headers": raw,
                    "scheme": "https", "server": (host, 443)})


class TestCsrf(unittest.TestCase):
    def test_token_is_minted_once_and_set_as_cookie(self):
        req = _request()
        tok = csrf_token(req)
        self.assertGreaterEqual(len(tok), 32)
        self.assertEqual(csrf_token(req), tok)
        resp = Response("ok")
        ensure_csrf_cookie(resp, req)
        self.assertIn(f"csrf={tok}", resp.headers["set-cookie"])

    def test_existing_cookie_is_reused_and_not_reset(self):
        req = _request({"cookie": "csrf=abc123"})
        self.assertEqual(csrf_token(req), "abc123")
        resp = Response("ok")
        ensure_csrf_cookie(resp, req)
        self.assertNotIn("set-cookie", resp.headers)

    def test_check_csrf_compares_cookie_and_form_value(self):
        req = _request({"cookie": "csrf=abc123"})
        self.assertTrue(check_csrf(req, "abc123"))
        self.assertFalse(check_csrf(req, "zzz"))
        self.assertFalse(check_csrf(req, None))
        self.assertFalse(check_csrf(_request(), "abc123"))

    def test_same_origin_accepts_missing_or_matching_origin_only(self):
        self.assertTrue(same_origin(_request()))
        self.assertTrue(same_origin(_request({"origin": "https://audit.jbacteam.com"})))
        self.assertFalse(same_origin(_request({"origin": "https://evil.example"})))

    def test_require_form_post_raises_403(self):
        with self.assertRaises(HTTPException) as cm:
            require_form_post(_request({"cookie": "csrf=abc123"}), "wrong")
        self.assertEqual(cm.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            require_form_post(_request({"cookie": "csrf=abc123", "origin": "https://evil.example"}), "abc123")
        require_form_post(_request({"cookie": "csrf=abc123", "origin": "https://audit.jbacteam.com"}), "abc123")


class TestFlash(unittest.TestCase):
    def test_flash_roundtrip_through_cookie(self):
        resp = Response("ok")
        set_flash(resp, "บันทึกแล้ว ✓", "ok")
        cookie = resp.headers["set-cookie"].split(";")[0]          # flash=<value>
        req = _request({"cookie": cookie})
        self.assertEqual(pop_flash(req), {"text": "บันทึกแล้ว ✓", "kind": "ok"})
        self.assertIsNone(pop_flash(_request()))
        self.assertIsNone(pop_flash(_request({"cookie": "flash=garbage"})))


class TestAdminLog(unittest.TestCase):
    def test_log_admin_writes_a_row(self):
        conn = connect(":memory:")
        migrate(conn)
        log_admin(conn, "admin", "contract.update", "2026-10-r005", {"amount_mmk": 450000})
        row = one(conn, "SELECT * FROM admin_log ORDER BY id DESC LIMIT 1")
        self.assertEqual((row["user"], row["action"], row["target"]), ("admin", "contract.update", "2026-10-r005"))
        self.assertIn("450000", row["detail"])


if __name__ == "__main__":
    unittest.main()
