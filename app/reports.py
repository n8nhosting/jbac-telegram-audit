"""Monthly report: summary numbers for a calendar month and the contract × day status grid."""
from __future__ import annotations

import calendar
import json
import sqlite3


def month_days(month: str) -> list[str]:
    y, m = int(month[:4]), int(month[5:7])
    return [f"{month}-{d:02d}" for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def month_summary(conn: sqlite3.Connection, month: str) -> dict:
    days = month_days(month)
    first, last = days[0], days[-1]
    contracts = conn.execute("SELECT COUNT(*) FROM contracts WHERE month=?", (month,)).fetchone()[0]
    fee_total = conn.execute("SELECT COALESCE(SUM(amount_mmk),0) FROM contracts WHERE month=? AND status IN ('active','paused')", (month,)).fetchone()[0]
    reg_total = conn.execute("SELECT COALESCE(SUM(reg),0) FROM reg_monthly WHERE month=?", (month,)).fetchone()[0]
    kinds = {r["kind"]: r["n"] for r in conn.execute(
        """SELECT ch.kind, COUNT(DISTINCT ch.id) AS n FROM channels ch JOIN contract_channels cc ON cc.channel_id=ch.id
           JOIN contracts c ON c.id=cc.contract_id WHERE c.month=? GROUP BY ch.kind""", (month,))}
    counts = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM daily_rollup WHERE local_date BETWEEN ? AND ? GROUP BY status", (first, last))}
    days_computed = conn.execute("SELECT COUNT(DISTINCT local_date) FROM daily_rollup WHERE local_date BETWEEN ? AND ?", (first, last)).fetchone()[0]
    ok = counts.get("ok", 0)
    bad = counts.get("missed", 0) + counts.get("invalid", 0) + counts.get("pin_missing", 0)
    return {
        "month": month, "contracts": contracts, "fee_total": fee_total, "reg_total": reg_total,
        "channels_public": kinds.get("public_preview", 0) + kinds.get("public_no_preview", 0),
        "channels_private": kinds.get("private", 0),
        "days_computed": days_computed, "ok_days": ok, "missed_days": counts.get("missed", 0), "action_days": bad,
        "unverifiable_days": counts.get("unverifiable", 0),
        "ok_rate": round(100 * ok / (ok + bad)) if (ok + bad) else None,
        "status_counts": counts,
    }


def month_grid(conn: sqlite3.Connection, month: str) -> list[dict]:
    """One row per contract of the month (or with results in it); one cell per calendar day."""
    days = month_days(month)
    first, last = days[0], days[-1]
    cells: dict[tuple[int, str], sqlite3.Row] = {}
    for r in conn.execute("SELECT contract_id, local_date, status, qualified, required FROM daily_rollup WHERE local_date BETWEEN ? AND ?", (first, last)):
        cells[(r["contract_id"], r["local_date"])] = r
    rows = []
    for c in conn.execute(
            """SELECT id, sheet_contract_id, names, amount_mmk, status FROM contracts
               WHERE month=? OR id IN (SELECT DISTINCT contract_id FROM daily_rollup WHERE local_date BETWEEN ? AND ?)
               ORDER BY amount_mmk DESC, sheet_contract_id""", (month, first, last)):
        row_cells, ok, missed, action = [], 0, 0, 0
        for d in days:
            r = cells.get((c["id"], d))
            st = r["status"] if r else None
            row_cells.append({"date": d, "status": st, "day": int(d[8:]),
                              "label": f"{r['qualified']}/{r['required']}" if r and r["required"] is not None else ""})
            ok += st == "ok"
            missed += st == "missed"
            action += st in ("missed", "invalid", "pin_missing", "dead")
        rows.append({"id": c["id"], "sheet_contract_id": c["sheet_contract_id"], "names_list": json.loads(c["names"] or "[]"),
                     "amount_mmk": c["amount_mmk"], "contract_status": c["status"], "cells": row_cells, "ok": ok, "missed": missed, "action": action})
    return rows
