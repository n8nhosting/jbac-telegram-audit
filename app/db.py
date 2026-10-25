"""SQLite access: one connection per component, WAL on disk, migrations applied from app/migrations/*.sql."""
from __future__ import annotations

import datetime as dt
import pathlib
import sqlite3

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations in file-name order; returns the names applied this call."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    conn.commit()
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in done:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)", (f.name, now_utc()))
        conn.commit()
        applied.append(f.name)
    return applied


def one(conn: sqlite3.Connection, sql: str, params=()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def all_rows(conn: sqlite3.Connection, sql: str, params=()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()
