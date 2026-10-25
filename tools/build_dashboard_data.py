#!/usr/bin/env python
"""Shape data/* (from extract_channels.py) into the small CSVs the Platinum Marketing Plan dashboard reads.

Outputs (dashboard/data/):
  roster_contracts.csv  one row per contract in the current roster sheet, with reg totals and cost per reg
  monthly_spend.csv     one row per monthly plan sheet: active contracts, spend, public/private channel counts
  reg_sources.csv       registrations per month by source group (from the Reg List sheet)

Run: C:/Users/ADMIN/scoop/apps/python313/current/python -I tools/build_dashboard_data.py
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib


def exclusivity_label(n) -> str:
    if n is None:
        return "custom"
    return "only us" if int(n) == 1 else f"{int(n)} ads"


def roster_rows(contracts: list[dict]) -> list[dict]:
    rows = []
    for c in contracts:
        hist = c.get("reg_history") or []
        regs = [e["reg"] for e in hist]
        reg_sum, reg_months = sum(regs), len(regs)
        amount = c.get("amount_mmk") or 0
        links = c.get("links") or []
        rows.append({
            "contract_id": c["contract_id"],
            "row": c.get("row"),
            "name": " / ".join(c.get("names") or []),
            "section": c.get("section"),
            "exclusivity": c.get("exclusivity"),
            "exclusivity_label": exclusivity_label(c.get("exclusivity")),
            "quota_type": c.get("quota_type"),
            "quota_posts_per_day": c.get("quota_posts_per_day"),
            "pin_rule": c.get("pin_rule"),
            "amount_mmk": amount,
            "streak_months": c.get("streak_months"),
            "admins": " ".join(c.get("admin_accounts") or []),
            "public_links": sum(1 for l in links if l.get("kind") == "public"),
            "private_links": sum(1 for l in links if l.get("kind") == "private"),
            "reg_sum": reg_sum,
            "reg_months": reg_months,
            "reg_detail": " ".join(f"{e['month']}:{e['reg']}" for e in hist),
            "cost_per_reg_mmk": round(amount * reg_months / reg_sum) if (reg_sum > 0 and amount) else None,
            "zero_reg": reg_months >= 3 and reg_sum == 0,
            "renamed": bool(c.get("old_name") or c.get("old_links")),
            "status": c.get("status_sheet"),
            "period_from": c.get("period_from"),
            "period_to": c.get("period_to"),
        })
    return rows


def _int(v) -> int:
    return int(float(v)) if v not in (None, "") else 0


def monthly_rows(summary: list[dict]) -> list[dict]:
    return [{
        "month": r["month"],
        "era": r["era"],
        "contracts": _int(r["active_contracts"]),
        "amount_mmk": _int(r["amount_active_sum"]),
        "public_channels": _int(r["public_channels"]),
        "private_channels": _int(r["private_channels"]),
        "renamed_rows": _int(r["renamed_rows"]),
    } for r in summary]


def reg_source_rows(rows: list[dict]) -> list[dict]:
    by_month: dict[str, dict] = {}
    for r in rows:
        m = r["month"]
        d = by_month.setdefault(m, {"month": m, "total": None, "telegram_channel": 0, "friend": 0})
        src = " ".join(str(r["source"]).lower().split())
        is_total = r.get("is_total") in (True, "True", "true", "1")
        if is_total:
            d["total"] = _int(r["reg"])
        elif "telegram" in src:
            d["telegram_channel"] += _int(r["reg"])
        elif src == "friend":
            d["friend"] += _int(r["reg"])
    out = []
    for m in sorted(by_month):
        d = by_month[m]
        if not d["total"]:
            continue
        d["other"] = d["total"] - d["telegram_channel"] - d["friend"]
        out.append(d)
    return out


def _write_csv(path: pathlib.Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="dashboard/data")
    a = ap.parse_args(argv)
    data, out = pathlib.Path(a.data), pathlib.Path(a.out)
    seed = json.loads((data / "channels.seed.json").read_text(encoding="utf-8"))
    with (data / "monthly_summary.csv").open(encoding="utf-8-sig", newline="") as f:
        summary = list(csv.DictReader(f))
    with (data / "reg_list_monthly.csv").open(encoding="utf-8-sig", newline="") as f:
        reg_list = list(csv.DictReader(f))
    roster, monthly, regs = roster_rows(seed["contracts"]), monthly_rows(summary), reg_source_rows(reg_list)
    _write_csv(out / "roster_contracts.csv", roster)
    _write_csv(out / "monthly_spend.csv", monthly)
    _write_csv(out / "reg_sources.csv", regs)
    print(f"roster={len(roster)} rows, spend sum={sum(r['amount_mmk'] for r in roster):,}; "
          f"monthly={len(monthly)} rows; reg_sources={len(regs)} rows; zero_reg={sum(r['zero_reg'] for r in roster)}")


if __name__ == "__main__":
    main()
