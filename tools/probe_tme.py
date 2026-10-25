#!/usr/bin/env python
"""Coverage probe: which public channels in data/channels.seed.json can be read via https://t.me/s/<username>?

Read-only GETs, sequential, 1.5-2.5 s apart, browser User-Agent, never joins anything.
Also peeks at a few private invite pages (https://t.me/+hash, no /s/) to see whether title and
subscriber count are visible without joining, and checks that the ?q=#hashtag search works.

Outputs:
  data/probe/raw/<username>.html   raw pages (git-ignored)
  data/probe_report.json           per-channel results (+ invites, hashtag checks, summary)
  data/probe_report.md             human-readable coverage report (Thai)

Run:  C:/Users/ADMIN/scoop/apps/python313/current/python -I tools/probe_tme.py [--limit 5]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import random
import re
import sys
import time

from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HASHTAG = "#platinumclubmm"
PREVIEW_RE = re.compile(r"^https?://t\.me/s/([^/?#]+)", re.I)


# --------------------------------------------------------------------------- #
# parsers live in app/tgweb.py (shared with the service); re-exported here so tests and callers keep working
# --------------------------------------------------------------------------- #
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.tgweb import (parse_count, extract_hashtags, is_preview_url, _txt, parse_post, summarize_posts,  # noqa: E402,F401
                       parse_preview, parse_invite, parse_profile)

def sync_with_seed(report: dict, seed: dict) -> dict:
    """Drop probed usernames that the current seed no longer lists as a current public channel (e.g. a stale
    hyperlink that a later extractor fix re-filed under Old Link); keep their names for the record."""
    current = {ch["username"] for ch in seed.get("channels", [])
               if ch.get("kind") == "public" and not ch.get("is_old_link")}
    keep = [r for r in report["channels"] if r["username"] in current]
    report["dropped_old_link_usernames"] = [r["username"] for r in report["channels"] if r["username"] not in current]
    report["channels"] = keep
    report["summary"] = build_summary(keep, report.get("invites", []), report.get("hashtag_checks", []))
    return report


def _link_key(l: dict) -> str | None:
    if l.get("kind") == "public" and l.get("username"):
        return f"pub:{l['username']}"
    if l.get("kind") == "private" and l.get("invite_hash"):
        return f"prv:{l['invite_hash']}"
    return None


def sheet_subs_for(contract: dict, channel_key: str) -> int | None:
    """The hand-typed subscriber figure that belongs to this channel: the sheet lists one value per t.me link,
    in link order ('sub -23K/19K'); when the counts don't line up the pairing is unknown."""
    tme = [l for l in (contract.get("links") or []) if l.get("kind") in ("public", "private")]
    subs = ((contract.get("sub_view") or {}).get("subs")) or []
    keys = [_link_key(l) for l in tme]
    if channel_key not in keys or not subs:
        return None
    if len(subs) == len(tme):
        return subs[keys.index(channel_key)]
    if len(tme) == 1:
        return subs[0]
    return None


def repair_sheet_subs(report: dict, seed: dict) -> dict:
    """Re-pair every probed channel with its own sheet subscriber value (used by --rerender)."""
    contracts = {c["contract_id"]: c for c in seed.get("contracts", [])}
    for r in report["channels"]:
        c = contracts.get(r.get("contract_id"))
        v = sheet_subs_for(c, r["channel_id"]) if c else None
        r["sheet_subs"] = [v] if v is not None else []
    report["summary"] = build_summary(report["channels"], report.get("invites", []), report.get("hashtag_checks", []))
    return report


def enrich_profiles(report: dict, raw_dir: pathlib.Path) -> dict:
    """For channels whose /s/ page redirected, read the saved profile page (no re-fetch) and record what it is."""
    kinds = collections.Counter()
    for r in report["channels"]:
        if r.get("readable"):
            continue
        f = pathlib.Path(raw_dir) / f"{r['username']}.html"
        if not f.exists():
            continue
        p = parse_profile(f.read_text(encoding="utf-8"))
        r["profile_kind"] = p["kind"]
        r["profile_title"] = p["title"]
        r["profile_action"] = p["action"]
        if p["subscribers"] is not None:
            r["live_subscribers"] = p["subscribers"]
        if p["title"] and not r.get("title"):
            r["title"] = p["title"]
            r["title_matches_sheet"] = _title_matches(r.get("sheet_name"), p["title"])
        kinds[p["kind"]] += 1
    report["summary"] = build_summary(report["channels"], report.get("invites", []), report.get("hashtag_checks", []))
    report["summary"]["public_unreadable_by_kind"] = dict(kinds)
    return report


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #

def make_session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,th;q=0.8", "Accept": "text/html"})
    return s


def fetch(session, url: str, timeout: int = 20, retries: int = 3) -> dict:
    import requests
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException as e:
            if attempt == retries:
                return {"ok": False, "status": None, "final_url": url, "html": "", "error": str(e)}
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(10 * (attempt + 1))
            continue
        return {"ok": r.status_code == 200, "status": r.status_code, "final_url": r.url, "html": r.text,
                "error": None if r.status_code == 200 else f"http_{r.status_code}"}
    return {"ok": False, "status": None, "final_url": url, "html": "", "error": "exhausted"}


def _title_matches(sheet_name, title) -> bool | None:
    if not sheet_name or not title:
        return None
    a = re.sub(r"\s+", "", sheet_name).lower()
    b = re.sub(r"\s+", "", title).lower()
    return a in b or b in a


def run_probe(seed_path: pathlib.Path, out_dir: pathlib.Path, limit=None, delay=(1.5, 2.5),
              invites=5, hashtag_checks=3, include_old=False, log=print) -> dict:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    contracts = {c["contract_id"]: c for c in seed["contracts"]}
    by_user = collections.OrderedDict()
    for ch in seed["channels"]:
        if ch["kind"] == "public" and (include_old or not ch["is_old_link"]):
            by_user.setdefault(ch["username"], ch)
    usernames = list(by_user)[:limit] if limit else list(by_user)
    raw_dir = out_dir / "probe" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = make_session()
    started = dt.datetime.now().isoformat(timespec="seconds")

    results = []
    for i, u in enumerate(usernames, 1):
        url = f"https://t.me/s/{u}"
        f = fetch(session, url)
        (raw_dir / f"{u}.html").write_text(f["html"], encoding="utf-8")
        if f["ok"]:
            p = parse_preview(f["html"], f["final_url"])
        else:
            p = {"readable": False, "reason": f["error"] or "fetch_failed", "title": None, "counters": {},
                 "summary": {}, "before_cursor": None, "posts": [], "description": None}
        ch = by_user[u]
        con = contracts.get(ch["contract_id"], {})
        v = sheet_subs_for(con, ch["channel_id"])
        sheet_subs = [v] if v is not None else []
        live_subs = (p.get("counters") or {}).get("subscribers") or (p.get("counters") or {}).get("members")
        results.append({
            "username": u, "channel_id": ch["channel_id"], "contract_id": ch["contract_id"],
            "sheet_name": ch["name"], "section": ch["section"], "pin_rule": ch["pin_rule"],
            "sheet_subs": sheet_subs, "http_status": f["status"], "final_url": f["final_url"],
            "readable": p["readable"], "reason": p.get("reason"), "title": p.get("title"),
            "title_matches_sheet": _title_matches(ch["name"], p.get("title")),
            "description": p.get("description"), "counters": p.get("counters"), "live_subscribers": live_subs,
            "summary": p.get("summary"), "before_cursor": p.get("before_cursor"), "posts": p.get("posts", []),
        })
        s = p.get("summary") or {}
        log(f"[{i}/{len(usernames)}] {u}: {f['status']} readable={p['readable']} reason={p.get('reason')} "
            f"subs={live_subs} posts={s.get('posts_in_window')} window_h={s.get('window_hours')} "
            f"platinum={s.get('mentions_platinum')}")
        time.sleep(random.uniform(*delay))

    invite_results = []
    seen = set()
    for ch in seed["channels"]:
        if len(invite_results) >= invites:
            break
        if ch["kind"] != "private" or not ch["invite_hash"] or ch["is_old_link"] or ch["invite_hash"] in seen:
            continue
        seen.add(ch["invite_hash"])
        url = f"https://t.me/+{ch['invite_hash']}"
        f = fetch(session, url)
        (raw_dir / f"invite_{ch['invite_hash']}.html").write_text(f["html"], encoding="utf-8")
        inv = parse_invite(f["html"]) if f["ok"] else {"visible": False, "title": None, "subscribers": None,
                                                      "description": None, "action": None, "extra": None}
        invite_results.append({"invite_hash": ch["invite_hash"], "channel_id": ch["channel_id"],
                               "contract_id": ch["contract_id"], "sheet_name": ch["name"], "http_status": f["status"],
                               "final_url": f["final_url"], **inv,
                               "title_matches_sheet": _title_matches(ch["name"], inv.get("title"))})
        log(f"[invite] {ch['invite_hash']}: {f['status']} visible={inv.get('visible')} title={inv.get('title')!r} "
            f"subs={inv.get('subscribers')} action={inv.get('action')!r}")
        time.sleep(random.uniform(*delay))

    hashtag_results = []
    for r in [x for x in results if x["readable"]][:hashtag_checks]:
        url = f"https://t.me/s/{r['username']}?q=%23platinumclubmm"
        f = fetch(session, url)
        p = parse_preview(f["html"], f["final_url"]) if f["ok"] else {"readable": False, "reason": f["error"], "posts": []}
        hashtag_results.append({"username": r["username"], "http_status": f["status"], "final_url": f["final_url"],
                                "search_page_readable": p["readable"], "reason": p.get("reason"),
                                "matching_posts": len(p.get("posts", []))})
        log(f"[hashtag] {r['username']}: {f['status']} readable={p['readable']} matches={len(p.get('posts', []))}")
        time.sleep(random.uniform(*delay))

    report = {
        "generated_at": started, "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_seed": str(seed_path), "hashtag": HASHTAG,
        "public_probed": len(results), "invites_probed": len(invite_results),
        "summary": build_summary(results, invite_results, hashtag_results),
        "channels": results, "invites": invite_results, "hashtag_checks": hashtag_results,
    }
    (out_dir / "probe_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "probe_report.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def build_summary(results, invites, hashtag_checks) -> dict:
    readable = [r for r in results if r.get("readable")]
    reasons = collections.Counter(r.get("reason") for r in results if not r.get("readable"))
    windows = [(r.get("summary") or {}).get("window_hours") for r in readable]
    windows = [w for w in windows if w is not None]
    ratio = []
    for r in results:
        if r.get("live_subscribers") and r.get("sheet_subs"):
            ratio.append(r["live_subscribers"] / r["sheet_subs"][0])
    return {
        "public_total": len(results),
        "public_readable": len(readable),
        "public_unreadable_by_reason": dict(reasons),
        "title_matches": sum(1 for r in results if r.get("title_matches_sheet")),
        "title_mismatch": sum(1 for r in results if r.get("title_matches_sheet") is False),
        "channels_window_under_24h": sum(1 for w in windows if w < 24),
        "channels_window_24h_or_more": sum(1 for w in windows if w >= 24),
        "channels_mentioning_platinum": sum(1 for r in readable if (r.get("summary") or {}).get("mentions_platinum")),
        "channels_with_target_hashtag": sum(1 for r in readable if (r.get("summary") or {}).get("posts_with_hashtag")),
        "subs_live_vs_sheet_median_ratio": round(sorted(ratio)[len(ratio) // 2], 3) if ratio else None,
        "invites_visible": sum(1 for i in invites if i["visible"]),
        "invites_total": len(invites),
        "hashtag_search_pages_readable": sum(1 for h in hashtag_checks if h["search_page_readable"]),
        "hashtag_checks_total": len(hashtag_checks),
    }


def render_markdown(rep: dict) -> str:
    s = rep["summary"]
    L = [f"# Coverage probe — `t.me/s/<username>` ({rep['generated_at'][:16]})", "",
         f"ที่มา: `{rep['source_seed']}` · ยิง GET อย่างเดียว ไม่ join · แฮชแท็กเป้าหมาย `{rep['hashtag']}`", "",
         "## สรุป", "",
         f"- ช่องสาธารณะที่ตรวจ: **{s['public_total']}** → อ่าน preview ได้ **{s['public_readable']}** "
         f"({(100 * s['public_readable'] / s['public_total']) if s['public_total'] else 0:.0f}%)",
         f"- อ่านไม่ได้ แยกตามสาเหตุ: {s['public_unreadable_by_reason'] or 'ไม่มี'}",
         f"- อ่านไม่ได้ แยกตามหน้าโปรไฟล์ที่ได้แทน: {s.get('public_unreadable_by_kind') or 'ยังไม่ได้ตรวจ'} "
         "(`channel_no_preview` = ช่องจริงแต่ปิด preview → ต้องใช้ MTProto; `user_or_bot` = ลิงก์ในชีตเป็นบัญชีคน/บอท ไม่ใช่ช่อง; "
         "`restricted_channel` = ช่องมีอยู่แต่เว็บซ่อนชื่อ/ยอด (เนื้อหาจำกัด) → MTProto; "
         "`missing` = ไม่มีใครใช้ username นี้ = ลิงก์ตาย/พิมพ์ผิด)"
         + (f"\n- username ที่ไม่อยู่ใน seed ปัจจุบันแล้ว (ย้ายเป็น Old Link): {len(rep.get('dropped_old_link_usernames') or [])} → "
            f"{', '.join(rep.get('dropped_old_link_usernames') or [])}" if rep.get("dropped_old_link_usernames") else ""),
         f"- ชื่อตรงกับชีต (รวมช่องที่อ่านได้จากหน้าโปรไฟล์): {s['title_matches']} · ไม่ตรง (เปลี่ยนชื่อ/พิมพ์ต่าง): {s['title_mismatch']}",
         f"- ช่องที่ 20 โพสต์ล่าสุดกินเวลาน้อยกว่า 24 ชม. (โพสต์ถี่ ต้องใช้ `?q=` หรือ `?before=` ตาม): **{s['channels_window_under_24h']}** · "
         f"24 ชม.ขึ้นไป: {s['channels_window_24h_or_more']}",
         f"- ช่องที่โพสต์ล่าสุดมีคำว่า platinum: {s['channels_mentioning_platinum']} · มี `{rep['hashtag']}`: {s['channels_with_target_hashtag']}",
         f"- ยอด subscriber จริง ÷ ที่พิมพ์ในชีต (median): {s['subs_live_vs_sheet_median_ratio']}",
         f"- หน้า invite ส่วนตัว (ไม่ join) เห็นชื่อ+จำนวนสมาชิก: **{s['invites_visible']}/{s['invites_total']}**",
         f"- หน้าค้นหาแฮชแท็ก `?q=%23platinumclubmm` ใช้ได้: {s['hashtag_search_pages_readable']}/{s['hashtag_checks_total']}",
         "", "## ข้อจำกัดที่ยืนยันแล้ว", "",
         "- หน้า preview **ไม่บอกสถานะ pin** ของโพสต์ → เงื่อนไข `pin daily` ตรวจผ่าน `t.me/s/` ไม่ได้ ต้องใช้ MTProto",
         "- หน้า preview แสดงประมาณ 20 โพสต์ล่าสุดต่อหน้า; ย้อนหลังด้วย `?before=<id>` ได้ แต่ต้องยิงเพิ่ม",
         "- ช่องส่วนตัว (`t.me/+hash`) เห็นเฉพาะชื่อ/จำนวนสมาชิก/คำอธิบาย ไม่เห็นโพสต์",
         "", "## รายช่อง", "",
         "| # | username | ชื่อในชีต | HTTP | อ่านได้ | สาเหตุ | หน้าโปรไฟล์ | ชื่อตรง | subs ชีต | subs จริง | โพสต์ | ช่วง (ชม.) | โพสต์/วัน | มีสื่อ | มีลิงก์ | platinum | pin rule |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rep["channels"], 1):
        sm = r.get("summary") or {}
        L.append("| {} | `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, r["username"], (r.get("sheet_name") or "")[:28].replace("|", "/"), r.get("http_status"),
            "✅" if r.get("readable") else "❌", r.get("reason") or "", r.get("profile_kind") or "",
            {True: "✅", False: "❌", None: ""}[r.get("title_matches_sheet")],
            r["sheet_subs"][0] if r.get("sheet_subs") else "", r.get("live_subscribers") or "",
            sm.get("posts_in_window", ""), sm.get("window_hours", ""), sm.get("posts_per_day_est") or "",
            sm.get("posts_with_media", ""), sm.get("posts_with_link", ""), sm.get("mentions_platinum", ""), r["pin_rule"]))
    L += ["", "## หน้า invite ส่วนตัว (ตัวอย่าง)", "",
          "| hash | ชื่อในชีต | HTTP | เห็นข้อมูล | ชื่อจริง | subs | ปุ่ม |", "|---|---|---|---|---|---|---|"]
    for i in rep["invites"]:
        L.append(f"| `{i['invite_hash']}` | {(i['sheet_name'] or '')[:28]} | {i['http_status']} | {'✅' if i['visible'] else '❌'} | "
                 f"{(i['title'] or '')[:30]} | {i['subscribers'] or ''} | {i['action'] or ''} |")
    L += ["", "## ตรวจหน้าค้นหาแฮชแท็ก", ""]
    for h in rep["hashtag_checks"]:
        L.append(f"- `{h['username']}` → HTTP {h['http_status']}, readable={h['search_page_readable']}, โพสต์ที่ตรง={h['matching_posts']}")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", default="data/channels.seed.json")
    ap.add_argument("--out", default="data")
    ap.add_argument("--limit", type=int, default=None, help="probe only the first N public usernames")
    ap.add_argument("--invites", type=int, default=5)
    ap.add_argument("--hashtag-checks", type=int, default=3)
    ap.add_argument("--delay-min", type=float, default=1.5)
    ap.add_argument("--delay-max", type=float, default=2.5)
    ap.add_argument("--include-old", action="store_true")
    ap.add_argument("--rerender", action="store_true",
                    help="no fetching: re-read data/probe_report.json + saved raw pages, enrich profiles, rewrite report")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    out = pathlib.Path(a.out)
    if a.rerender:
        rep = json.loads((out / "probe_report.json").read_text(encoding="utf-8"))
        seed_path = pathlib.Path(a.seed)
        if seed_path.exists():
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            rep = sync_with_seed(rep, seed)
            rep = repair_sheet_subs(rep, seed)
    else:
        rep = run_probe(pathlib.Path(a.seed), out, a.limit, (a.delay_min, a.delay_max),
                        a.invites, a.hashtag_checks, a.include_old, log=lambda s: print(s, flush=True))
    rep = enrich_profiles(rep, out / "probe" / "raw")
    rep["enriched_at"] = dt.datetime.now().isoformat(timespec="seconds")
    (out / "probe_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "probe_report.md").write_text(render_markdown(rep), encoding="utf-8")
    print(json.dumps(rep["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
