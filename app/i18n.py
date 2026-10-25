"""UI / alert strings in Thai (default), English and Burmese. Keys are stable; add a language by adding a column."""
from __future__ import annotations

LANGS = ("th", "en", "my")
DEFAULT_LANG = "th"
LANG_NAMES = {"th": "ไทย", "en": "English", "my": "မြန်မာ"}

STRINGS: dict[str, dict[str, str]] = {
    # ---- chrome ----
    "app.subtitle": {"th": "ตรวจโพสต์ Telegram", "en": "Telegram post audit", "my": "Telegram ပိုစ့်စစ်ဆေးမှု"},
    "nav.prev": {"th": "← ก่อนหน้า", "en": "← Previous", "my": "← ယခင်နေ့"},
    "nav.next": {"th": "ถัดไป →", "en": "Next →", "my": "နောက်နေ့ →"},
    "nav.today": {"th": "วันนี้", "en": "Today", "my": "ယနေ့"},
    "nav.view": {"th": "ดู", "en": "View", "my": "ကြည့်"},
    "nav.all_status": {"th": "ทุกสถานะ", "en": "All statuses", "my": "အခြေအနေအားလုံး"},
    "nav.csv": {"th": "CSV วันที่เลือก", "en": "CSV for this day", "my": "ဤနေ့ CSV"},
    "nav.back": {"th": "← กลับหน้ารวม", "en": "← Back to overview", "my": "← ပင်မစာမျက်နှာ"},
    "meta.contracts": {"th": "สัญญา {n}", "en": "{n} contracts", "my": "စာချုပ် {n} ခု"},
    "meta.last_collect": {"th": "เก็บข้อมูลล่าสุด {t}", "en": "last collected {t}", "my": "နောက်ဆုံးစုဆောင်း {t}"},
    "meta.never": {"th": "ยังไม่เคย", "en": "never", "my": "မရှိသေး"},
    "meta.hashtag": {"th": "แฮชแท็ก", "en": "hashtag", "my": "hashtag"},
    "meta.mtproto_off": {"th": "MTProto ปิดอยู่ (ช่องส่วนตัวยังตรวจไม่ได้)", "en": "MTProto off (private channels not readable yet)",
                         "my": "MTProto ပိတ်ထား (private ချန်နယ်များ မစစ်နိုင်သေး)"},
    "empty.no_data": {
        "th": "ยังไม่มีข้อมูล — นำเข้าสัญญาด้วย POST /admin/import (ไฟล์ channels.seed.json จาก tools/extract_channels.py)",
        "en": "No data yet — import contracts with POST /admin/import (channels.seed.json from tools/extract_channels.py)",
        "my": "ဒေတာမရှိသေးပါ — POST /admin/import ဖြင့် စာချုပ်များ (channels.seed.json) ကို ထည့်သွင်းပါ"},
    # ---- KPI tiles ----
    "kpi.missed": {"th": "ขาด (เลย cutoff)", "en": "Missed (past cutoff)", "my": "ပျက်ကွက် (cutoff ကျော်)"},
    "kpi.invalid": {"th": "โพสต์แต่ไม่ผ่านเงื่อนไข", "en": "Posted but not qualifying", "my": "ပိုစ့်တင်သော်လည်း စည်းကမ်းမကိုက်"},
    "kpi.pin_missing": {"th": "ไม่ pin", "en": "Not pinned", "my": "Pin မလုပ်"},
    "kpi.unverifiable": {"th": "ตรวจไม่ได้", "en": "Unverifiable", "my": "စစ်ဆေး၍မရ"},
    "kpi.waiting": {"th": "รอ (ยังไม่ถึง cutoff)", "en": "Waiting (before cutoff)", "my": "စောင့်ဆိုင်း (cutoff မရောက်သေး)"},
    "kpi.ok": {"th": "ครบ", "en": "Complete", "my": "ပြည့်"},
    "kpi.dead": {"th": "ช่องตาย", "en": "Dead channels", "my": "ချန်နယ်ပျက်"},
    "kpi.posts": {"th": "โพสต์ผ่านเกณฑ์ ({d})", "en": "Qualifying posts ({d})", "my": "စံကိုက်ပိုစ့် ({d})"},
    # ---- table ----
    "th.status": {"th": "สถานะ", "en": "Status", "my": "အခြေအနေ"},
    "th.channel_contract": {"th": "ช่อง / สัญญา", "en": "Channel / contract", "my": "ချန်နယ် / စာချုပ်"},
    "th.terms": {"th": "เงื่อนไข", "en": "Terms", "my": "စည်းကမ်း"},
    "th.passed_required": {"th": "ผ่าน/ต้อง", "en": "Passed/required", "my": "ကိုက်/လိုအပ်"},
    "th.pin": {"th": "pin", "en": "pin", "my": "pin"},
    "th.missed_30d": {"th": "ขาด/30 วัน", "en": "Missed/30 d", "my": "ပျက်/၃၀ ရက်"},
    "th.last_post": {"th": "โพสต์ล่าสุด (UTC)", "en": "Last post (UTC)", "my": "နောက်ဆုံးပိုစ့် (UTC)"},
    "th.fee": {"th": "ค่าจ้าง", "en": "Fee", "my": "ကြေးငွေ"},
    "th.last_reg": {"th": "reg ล่าสุด", "en": "Latest reg", "my": "နောက်ဆုံး reg"},
    "th.evidence": {"th": "หลักฐาน", "en": "Evidence", "my": "အထောက်အထား"},
    "row.channels": {"th": "{n} ช่อง", "en": "{n} channels", "my": "ချန်နယ် {n} ခု"},
    "row.posts_per_day": {"th": "{n} โพสต์/วัน/ช่อง", "en": "{n} post(s)/day/channel", "my": "တစ်ရက် {n} ပိုစ့်/ချန်နယ်"},
    "row.custom": {"th": "เงื่อนไขพิเศษ", "en": "Custom terms", "my": "အထူးစည်းကမ်း"},
    "row.none_in_status": {"th": "ไม่มีสัญญาในสถานะนี้", "en": "No contracts in this status", "my": "ဤအခြေအနေတွင် စာချုပ်မရှိ"},
    "footer.note": {
        "th": "สถานะคำนวณจากกติกา SPEC §6 ตาม {tz} · \"ตรวจไม่ได้\" = ช่องส่วนตัว/ปิด preview ที่ยังไม่มีบัญชีสมาชิกอ่าน ไม่ใช่ \"ไม่ได้โพสต์\" · ค่าจ้างเป็น MMK/เดือน",
        "en": "Statuses follow SPEC §6 in {tz} · \"Unverifiable\" = private / no-preview channels the member account cannot read yet, not \"did not post\" · fees in MMK/month",
        "my": "အခြေအနေများကို SPEC §6 စည်းမျဉ်းအတိုင်း {tz} ဖြင့် တွက်ချက်သည် · \"စစ်ဆေး၍မရ\" ဆိုသည်မှာ အကောင့်မရှိသေး၍ ဖတ်မရသော private/preview ပိတ်ထားသော ချန်နယ်ဖြစ်ပြီး \"မတင်\" ဟု မဆိုလိုပါ · ကြေးငွေမှာ MMK/လ"},
    # ---- statuses ----
    "status.ok": {"th": "ครบ", "en": "Complete", "my": "ပြည့်"},
    "status.waiting": {"th": "รอ", "en": "Waiting", "my": "စောင့်ဆိုင်း"},
    "status.missed": {"th": "ขาด", "en": "Missed", "my": "ပျက်ကွက်"},
    "status.invalid": {"th": "ไม่ผ่านเงื่อนไข", "en": "Not qualifying", "my": "စည်းကမ်းမကိုက်"},
    "status.pin_missing": {"th": "ไม่ pin", "en": "Not pinned", "my": "Pin မလုပ်"},
    "status.unverifiable": {"th": "ตรวจไม่ได้", "en": "Unverifiable", "my": "စစ်ဆေး၍မရ"},
    "status.dead": {"th": "ช่องตาย", "en": "Dead channel", "my": "ချန်နယ်ပျက်"},
    "status.paused": {"th": "นอกสัญญา", "en": "Outside contract", "my": "စာချုပ်ပြင်ပ"},
    "status.manual": {"th": "ตรวจมือ", "en": "Manual check", "my": "လက်ဖြင့်စစ်"},
    "status.none": {"th": "ยังไม่ประมวลผล", "en": "Not computed yet", "my": "မတွက်ရသေး"},
    # ---- pin rules ----
    "pin.none": {"th": "ไม่มี pin", "en": "no pin", "my": "pin မရှိ"},
    "pin.daily": {"th": "pin ทุกวัน", "en": "pin daily", "my": "နေ့တိုင်း pin"},
    "pin.per_month": {"th": "pin {n} ครั้ง/เดือน", "en": "pin {n}×/month", "my": "တစ်လ {n} ကြိမ် pin"},
    "pin.every_days": {"th": "pin ทุก {n} วัน", "en": "pin every {n} days", "my": "{n} ရက်တစ်ကြိမ် pin"},
    # ---- contract page ----
    "c.advertisers": {"th": "ผู้ลงโฆษณา {n} ราย", "en": "{n} advertisers", "my": "ကြော်ငြာရှင် {n} ဦး"},
    "c.per_month": {"th": "MMK/เดือน", "en": "MMK/month", "my": "MMK/လ"},
    "c.unspecified": {"th": "ไม่ระบุ", "en": "unspecified", "my": "မသတ်မှတ်"},
    "c.status_on": {"th": "สถานะ {d}", "en": "Status {d}", "my": "{d} အခြေအနေ"},
    "c.passed_required": {"th": "โพสต์ผ่าน/ต้องมี", "en": "Passed/required", "my": "ကိုက်/လိုအပ်"},
    "c.not_computed": {"th": "ยังไม่ประมวลผลวัน {d}", "en": "Not computed for {d}", "my": "{d} မတွက်ရသေး"},
    "c.channels": {"th": "ช่องในสัญญา", "en": "Channels in contract", "my": "စာချုပ်ပါ ချန်နယ်များ"},
    "c.channel": {"th": "ช่อง", "en": "Channel", "my": "ချန်နယ်"},
    "c.type": {"th": "ประเภท", "en": "Type", "my": "အမျိုးအစား"},
    "c.subscribers": {"th": "สมาชิก", "en": "Subscribers", "my": "အသင်းဝင်"},
    "c.last_checked": {"th": "ตรวจล่าสุด", "en": "Last checked", "my": "နောက်ဆုံးစစ်"},
    "c.sheet": {"th": "ชีต", "en": "sheet", "my": "ဇယား"},
    "c.dead_since": {"th": "ตาย {d}", "en": "dead {d}", "my": "ပျက် {d}"},
    "c.last30": {"th": "30 วันล่าสุด", "en": "Last 30 days", "my": "နောက်ဆုံး ၃၀ ရက်"},
    "c.no_rollup": {"th": "ยังไม่มีผลประมวล", "en": "No results yet", "my": "ရလဒ်မရှိသေး"},
    "c.regs": {"th": "ผู้สมัคร (Reg) จากชีต", "en": "Registrations (Reg) from the sheet", "my": "ဇယားမှ Reg"},
    "c.aliases": {"th": "ชื่อ/ลิงก์เดิม", "en": "Previous names/links", "my": "ယခင်အမည်/လင့်"},
    "c.events": {"th": "เหตุการณ์", "en": "Events", "my": "ဖြစ်ရပ်များ"},
    "c.evidence_title": {"th": "หลักฐานโพสต์ 7 วันล่าสุด ({n})", "en": "Post evidence, last 7 days ({n})", "my": "နောက်ဆုံး ၇ ရက် ပိုစ့်အထောက်အထား ({n})"},
    "c.day": {"th": "วัน ({tz})", "en": "Day ({tz})", "my": "နေ့ ({tz})"},
    "c.time_utc": {"th": "เวลา (UTC)", "en": "Time (UTC)", "my": "အချိန် (UTC)"},
    "c.passed": {"th": "ผ่าน", "en": "Passed", "my": "ကိုက်"},
    "c.media_link": {"th": "สื่อ/ลิงก์", "en": "Media/link", "my": "မီဒီယာ/လင့်"},
    "c.views": {"th": "views", "en": "views", "my": "views"},
    "c.text": {"th": "ข้อความ", "en": "Text", "my": "စာသား"},
    "c.link": {"th": "ลิงก์", "en": "Link", "my": "လင့်"},
    "c.open": {"th": "เปิด", "en": "open", "my": "ဖွင့်"},
    "c.media": {"th": "สื่อ", "en": "media", "my": "မီဒီယာ"},
    "c.sticker": {"th": "สติกเกอร์", "en": "sticker", "my": "စတစ်ကာ"},
    "c.no_posts": {"th": "ยังไม่พบโพสต์ในช่วงนี้", "en": "No posts found in this window", "my": "ဤကာလတွင် ပိုစ့်မတွေ့ပါ"},
    "c.needs_mtproto": {"th": " — ช่องนี้ต้องใช้บัญชี MTProto จึงจะอ่านโพสต์ได้", "en": " — this channel needs the MTProto account to read posts",
                        "my": " — ဤချန်နယ်ကို MTProto အကောင့်ဖြင့်သာ ဖတ်နိုင်သည်"},
    "c.remark": {"th": "Remark", "en": "Remark", "my": "Remark"},
    # ---- alerts ----
    "a.head_warn": {"th": "⏰ เตือน 18:00 — {d}", "en": "⏰ 18:00 reminder — {d}", "my": "⏰ ၁၈:၀၀ သတိပေးချက် — {d}"},
    "a.head_summary": {"th": "📊 สรุปวัน {d} (23:50, ก่อน cutoff)", "en": "📊 Daily summary {d} (23:50, before cutoff)",
                       "my": "📊 {d} နေ့စဉ်အနှစ်ချုပ် (၂၃:၅၀, cutoff မတိုင်မီ)"},
    "a.head_final": {"th": "✅ สรุปสุดท้าย {d}", "en": "✅ Final summary {d}", "my": "✅ {d} နောက်ဆုံးအနှစ်ချုပ်"},
    "a.head_other": {"th": "📊 {d}", "en": "📊 {d}", "my": "📊 {d}"},
    "a.warn_line": {"th": "ยังขาด {n} สัญญาที่ยังไม่ครบโควตาวันนี้ (cutoff 23:59 {tz})",
                    "en": "{n} contracts still short of today's quota (cutoff 23:59 {tz})",
                    "my": "ယနေ့ quota မပြည့်သေးသော စာချုပ် {n} ခု (cutoff ၂၃:၅၉ {tz})"},
    "a.line1": {"th": "ครบ {ok} · รอ {waiting} · ขาด {missed} · ไม่ผ่านเงื่อนไข {invalid} · ไม่ pin {pin}",
                "en": "Complete {ok} · Waiting {waiting} · Missed {missed} · Not qualifying {invalid} · Not pinned {pin}",
                "my": "ပြည့် {ok} · စောင့် {waiting} · ပျက်ကွက် {missed} · စည်းကမ်းမကိုက် {invalid} · Pin မလုပ် {pin}"},
    "a.line2": {"th": "ตรวจไม่ได้ {u} · ช่องตาย {dead} · นอกสัญญา {paused} · ตรวจมือ {manual}",
                "en": "Unverifiable {u} · Dead {dead} · Outside contract {paused} · Manual {manual}",
                "my": "စစ်ဆေး၍မရ {u} · ချန်နယ်ပျက် {dead} · စာချုပ်ပြင်ပ {paused} · လက်ဖြင့်စစ် {manual}"},
    "a.line3": {"th": "สัญญาทั้งหมด {total} · โพสต์ผ่านเกณฑ์ {posts}", "en": "Contracts {total} · qualifying posts {posts}",
                "my": "စာချုပ် {total} ခု · စံကိုက်ပိုစ့် {posts}"},
}


def t(lang: str, key: str, **kw) -> str:
    entry = STRINGS.get(key)
    if not entry:
        return key
    s = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return s.format(**kw) if kw else s


def status_label(lang: str, status: str | None) -> str:
    key = f"status.{status or 'none'}"
    return t(lang, key) if key in STRINGS else str(status)


def pin_label(lang: str, rule: str | None) -> str:
    if not rule or rule == "none":
        return t(lang, "pin.none")
    if rule == "daily":
        return t(lang, "pin.daily")
    if rule.startswith("per_month:"):
        return t(lang, "pin.per_month", n=rule.split(":", 1)[1])
    if rule.startswith("every_days:"):
        return t(lang, "pin.every_days", n=rule.split(":", 1)[1])
    return rule


def _norm(v) -> str | None:
    v = (v or "").strip().lower()
    return v if v in LANGS else None


def resolve_lang(query: str | None, cookie: str | None, accept_language: str | None) -> str:
    for v in (query, cookie):
        n = _norm(v)
        if n:
            return n
    for part in (accept_language or "").split(","):
        tag = part.split(";")[0].strip().lower()
        primary = tag.split("-")[0]
        if primary in LANGS:
            return primary
    return DEFAULT_LANG
