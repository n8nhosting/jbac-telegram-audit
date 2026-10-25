"""Telegram web pages: URL builders, parsers for t.me/s/<u> (preview), t.me/<u> (profile) and t.me/+hash (invite),
and a polite async fetch. Parsers are shared with tools/probe_tme.py and tested against saved real pages in
tools/tests/fixtures/."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import quote

from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HASHTAG = "#platinumclubmm"
PREVIEW_RE = re.compile(r"^https?://t\.me/s/([^/?#]+)", re.I)
RETRY_STATUSES = {429, 500, 502, 503, 504}


# --------------------------------------------------------------------------- #
# urls
# --------------------------------------------------------------------------- #

def preview_url(username: str) -> str:
    return f"https://t.me/s/{username}"


def search_url(username: str, hashtag: str = HASHTAG) -> str:
    return f"https://t.me/s/{username}?q={quote(hashtag.lower(), safe='')}"


def profile_url(username: str) -> str:
    return f"https://t.me/{username}"


def invite_url(invite_hash: str) -> str:
    return f"https://t.me/+{invite_hash}"


# --------------------------------------------------------------------------- #
# parsers
# --------------------------------------------------------------------------- #

def parse_count(s) -> int | None:
    """'108K' -> 108000, '29 783 subscribers' -> 29783, '1.2M' -> 1200000"""
    if s is None:
        return None
    t = str(s).strip().lower().replace(" ", " ")
    m = re.search(r"(\d[\d ,]*(?:\.\d+)?)\s*([km])?", t)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(" ", "").replace(",", ""))
    except ValueError:
        return None
    return int(round(n * {"k": 1000, "m": 1_000_000}.get(m.group(2), 1)))


def extract_hashtags(text) -> list[str]:
    if not text:
        return []
    return [h.lower() for h in re.findall(r"#\w+", str(text))]


def is_preview_url(url: str) -> bool:
    return bool(PREVIEW_RE.match(url or ""))


def _txt(el, sep=" "):
    return el.get_text(sep, strip=True) if el is not None else None


def parse_post(m, hashtag: str = HASHTAG) -> dict:
    data_post = m.get("data-post") or ""
    tail = data_post.rsplit("/", 1)[-1]
    pid = int(tail) if tail.isdigit() else None
    time_el = m.select_one(".tgme_widget_message_date time") or m.select_one("time")
    txt_el = m.select_one(".tgme_widget_message_text")
    text = _txt(txt_el)
    views_el = m.select_one(".tgme_widget_message_views")
    classes = m.get("class", [])
    has_photo = m.select_one(".tgme_widget_message_photo_wrap") is not None
    has_video = m.select_one(".tgme_widget_message_video_player, .tgme_widget_message_video_wrap, "
                             ".tgme_widget_message_roundvideo_player") is not None
    has_sticker = (m.select_one(".tgme_widget_message_sticker_wrap, .tgme_widget_message_sticker") is not None
                   or "sticker_media" in classes)
    has_link_preview = m.select_one(".tgme_widget_message_link_preview") is not None
    links = [a.get("href") for a in (txt_el.select("a") if txt_el else []) if a.get("href")]
    tags = extract_hashtags(text)
    return {
        "post_id": pid,
        "permalink": f"https://t.me/{data_post}" if data_post else None,
        "datetime": time_el.get("datetime") if time_el is not None else None,
        "views": parse_count(_txt(views_el)) if views_el is not None else None,
        "text": text,
        "text_len": len(text or ""),
        "hashtags": tags,
        "has_target_hashtag": hashtag.lower() in tags,
        "has_photo": has_photo,
        "has_video": has_video,
        "has_sticker": has_sticker,
        "has_link_preview": has_link_preview,
        "links": links,
        "has_media": has_photo or has_video,
        "has_link": bool(links) or has_link_preview,
        "is_pinned": None,          # the public preview page does not expose pinned state
        "grouped": m.select_one(".tgme_widget_message_grouped_wrap") is not None,
    }


def summarize_posts(posts: list[dict]) -> dict:
    times = []
    for p in posts:
        if p.get("datetime"):
            try:
                times.append(dt.datetime.fromisoformat(p["datetime"]))
            except ValueError:
                pass
    s = {
        "posts_in_window": len(posts),
        "window_hours": None, "newest_post_at": None, "oldest_post_at": None, "posts_per_day_est": None,
        "posts_with_hashtag": sum(1 for p in posts if p["has_target_hashtag"]),
        "posts_with_media": sum(1 for p in posts if p["has_media"]),
        "posts_with_link": sum(1 for p in posts if p["has_link"]),
        "mentions_platinum": sum(1 for p in posts if p["text"] and "platinum" in p["text"].lower()),
        "views_median": None,
    }
    if times:
        span_h = (max(times) - min(times)).total_seconds() / 3600
        s.update(window_hours=round(span_h, 2), newest_post_at=max(times).isoformat(),
                 oldest_post_at=min(times).isoformat(),
                 posts_per_day_est=round(len(posts) / (span_h / 24), 1) if span_h >= 24 else None)
    views = sorted(p["views"] for p in posts if p["views"] is not None)
    if views:
        s["views_median"] = views[len(views) // 2]
    return s


def parse_preview(html: str, final_url: str, hashtag: str = HASHTAG) -> dict:
    res = {"readable": False, "reason": None, "final_url": final_url, "username": None, "title": None,
           "description": None, "counters": {}, "posts": [], "summary": {}, "before_cursor": None}
    m = PREVIEW_RE.match(final_url or "")
    if not m:
        res["reason"] = "redirected_no_preview"
        return res
    soup = BeautifulSoup(html or "", "lxml")
    if soup.select_one(".tgme_channel_info") is None:
        res["reason"] = "no_channel_info"
        return res
    res["readable"] = True
    res["title"] = _txt(soup.select_one(".tgme_channel_info_header_title"), "")
    u = _txt(soup.select_one(".tgme_channel_info_header_username"), "")
    res["username"] = (u.lstrip("@") if u else m.group(1)).lower()
    res["description"] = _txt(soup.select_one(".tgme_channel_info_description"))
    for c in soup.select(".tgme_channel_info_counter"):
        v, k = c.select_one(".counter_value"), c.select_one(".counter_type")
        if v is not None and k is not None:
            res["counters"][_txt(k).lower()] = parse_count(_txt(v))
    res["posts"] = [parse_post(x, hashtag) for x in soup.select(".tgme_widget_message")]
    res["summary"] = summarize_posts(res["posts"])
    more = soup.select_one("a.tme_messages_more")
    if more is not None:
        mm = re.search(r"before=(\d+)", more.get("href", ""))
        res["before_cursor"] = int(mm.group(1)) if mm else None
    return res


def parse_invite(html: str) -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    t = soup.select_one(".tgme_page_title")
    e = soup.select_one(".tgme_page_extra")
    d = soup.select_one(".tgme_page_description")
    a = soup.select_one(".tgme_action_button_new") or soup.select_one(".tgme_action_button")
    return {
        "visible": t is not None and e is not None,
        "title": _txt(t),
        "extra": _txt(e),
        "subscribers": parse_count(_txt(e)) if e is not None else None,
        "description": _txt(d),
        "action": _txt(a, ""),
    }


def parse_profile(html: str) -> dict:
    """t.me/<username> profile page, shown when /s/ has no preview: tells what the username actually is."""
    p = parse_invite(html)
    extra = (p.get("extra") or "").lower()
    action = (p.get("action") or "").lower()
    low = (html or "").lower()
    if "subscriber" in extra:
        kind = "channel_no_preview"
    elif "member" in extra:
        kind = "group"
    elif "send message" in action:
        kind = "user_or_bot"
    elif not p.get("title") and "view in telegram" in action and "view posts" in low:
        kind = "restricted_channel"  # channel exists, but web shows no title/counter (restricted content) → MTProto
    elif not p.get("title") and not action and "you can contact" in low:
        kind = "missing"            # nobody owns this username: dead link or typo in the sheet
    else:
        kind = "unknown"
    p["kind"] = kind
    return p


# --------------------------------------------------------------------------- #
# fetching (async, polite)
# --------------------------------------------------------------------------- #

@dataclass
class FetchResult:
    ok: bool
    status: int | None
    final_url: str
    html: str
    error: str | None = None


def default_headers() -> dict:
    return {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,th;q=0.8", "Accept": "text/html"}


async def fetch_text(client, url: str, retries: int = 3, timeout: float = 20.0,
                     sleep: Callable[[float], Awaitable[None]] | None = None) -> FetchResult:
    """GET with redirects; retry 429/5xx and network errors with backoff; any other non-200 returns ok=False."""
    import asyncio
    import httpx
    sleep = sleep or asyncio.sleep
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = await client.get(url, timeout=timeout, follow_redirects=True)
        except httpx.HTTPError as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                await sleep(3.0 * (attempt + 1))
                continue
            return FetchResult(False, None, url, "", last_err)
        status = int(r.status_code)
        if status in RETRY_STATUSES and attempt < retries:
            await sleep(10.0 * (attempt + 1))
            continue
        return FetchResult(status == 200, status, str(r.url), r.text if status == 200 else "",
                           None if status == 200 else f"http_{status}")
    return FetchResult(False, None, url, "", last_err or "exhausted")
