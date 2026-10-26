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
    "th.last_post": {"th": "โพสต์ล่าสุด ({tz})", "en": "Last post ({tz})", "my": "နောက်ဆုံးပိုစ့် ({tz})"},
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
    "c.note": {"th": "หมายเหตุ", "en": "Note", "my": "မှတ်ချက်"},
    "c.time_local": {"th": "เวลา ({tz})", "en": "Time ({tz})", "my": "အချိန် ({tz})"},
    "c.contract_id": {"th": "รหัสในชีต", "en": "Sheet id", "my": "ဇယား id"},
    "c.quota": {"th": "โควตา", "en": "Quota", "my": "Quota"},
    "c.fee": {"th": "ค่าจ้าง", "en": "Fee", "my": "ကြေးငွေ"},
    "c.period": {"th": "ช่วงสัญญา", "en": "Contract period", "my": "စာချုပ်ကာလ"},
    "c.admins": {"th": "แอดมินช่อง", "en": "Channel admins", "my": "ချန်နယ်အက်ဒမင်"},
    "c.exclusivity": {"th": "ผู้ลงโฆษณาสูงสุด", "en": "Max advertisers", "my": "ကြော်ငြာရှင် အများဆုံး"},
    "c.pin_today": {"th": "pin วันนี้", "en": "Pinned today", "my": "ယနေ့ pin"},
    "c.not_passed": {"th": "ไม่ผ่าน", "en": "Not passed", "my": "မကိုက်"},
    "c.legacy": {"th": "ผ่านแบบเก่า (คำว่า platinum)", "en": "legacy match (word platinum)", "my": "ယခင်စည်းမျဉ်း (platinum စကားလုံး)"},
    "c.strip_hint": {"th": "กดวันเพื่อดูหลักฐานของวันนั้น", "en": "Choose a day to see its evidence", "my": "ထိုနေ့၏ အထောက်အထားကြည့်ရန် ရက်ကိုရွေးပါ"},
    # ---- overview hero / severity bands ----
    "hero.needs_action": {"th": "ต้องจัดการ", "en": "Needs action", "my": "ဆောင်ရွက်ရန်"},
    "hero.of_total": {"th": "จาก {n} สัญญา", "en": "of {n} contracts", "my": "စာချုပ် {n} ခုအနက်"},
    "hero.cutoff_left": {"th": "เหลือ {h} ชม. {m} นาที ถึง cutoff 23:59 {tz}", "en": "{h} h {m} min to cutoff 23:59 {tz}",
                         "my": "cutoff ၂၃:၅၉ {tz} အထိ {h} နာရီ {m} မိနစ် ကျန်"},
    "hero.cutoff_closed": {"th": "ปิดรอบแล้ว (cutoff 23:59 {tz})", "en": "Day closed (cutoff 23:59 {tz})", "my": "ရက်ပိတ်ပြီး (cutoff ၂၃:၅၉ {tz})"},
    "hero.cutoff_future": {"th": "ยังไม่ถึงวันนี้", "en": "This day has not started yet", "my": "ဤနေ့ မရောက်သေးပါ"},
    "hero.posts": {"th": "โพสต์ผ่านเกณฑ์ {n}", "en": "{n} qualifying posts", "my": "စံကိုက်ပိုစ့် {n}"},
    "hero.bar_label": {"th": "สัดส่วนสถานะของสัญญาทั้งหมด", "en": "Share of contracts by status", "my": "စာချုပ်အခြေအနေ အချိုး"},
    "group.action": {"th": "ต้องจัดการ", "en": "Needs action", "my": "ဆောင်ရွက်ရန်"},
    "group.unverifiable": {"th": "ตรวจไม่ได้", "en": "Unverifiable", "my": "စစ်ဆေး၍မရ"},
    "group.waiting": {"th": "รอถึง cutoff", "en": "Waiting for cutoff", "my": "cutoff စောင့်ဆိုင်း"},
    "group.other": {"th": "นอกสัญญา / ตรวจมือ", "en": "Outside contract / manual", "my": "စာချုပ်ပြင်ပ / လက်ဖြင့်စစ်"},
    "group.ok": {"th": "ครบตามสัญญา", "en": "Complete", "my": "ပြည့်"},
    "row.view": {"th": "ดูหลักฐาน", "en": "View evidence", "my": "အထောက်အထားကြည့်"},
    "row.unreadable": {"th": "{n} ช่องยังอ่านไม่ได้ (รอบัญชีสมาชิก)", "en": "{n} channels not readable yet", "my": "ချန်နယ် {n} ခု ဖတ်မရသေး"},
    "nav.date": {"th": "วันที่", "en": "Date", "my": "ရက်စွဲ"},
    "nav.filter": {"th": "กรองสถานะ", "en": "Filter by status", "my": "အခြေအနေဖြင့် စစ်ထုတ်"},
    "nav.lang": {"th": "ภาษา", "en": "Language", "my": "ဘာသာစကား"},
    # ---- app shell ----
    "nav.menu": {"th": "เมนูหลัก", "en": "Main menu", "my": "ပင်မမီနူး"},
    "nav.group_main": {"th": "งานหลัก", "en": "Daily work", "my": "နေ့စဉ်လုပ်ငန်း"},
    "nav.group_manage": {"th": "จัดการข้อมูล", "en": "Manage", "my": "စီမံခန့်ခွဲ"},
    "nav.group_system": {"th": "ระบบ", "en": "System", "my": "စနစ်"},
    "nav.dashboard": {"th": "ตรวจวันนี้", "en": "Today's audit", "my": "ယနေ့စစ်ဆေးမှု"},
    "nav.reports": {"th": "รายงานรายเดือน", "en": "Monthly report", "my": "လစဉ်အစီရင်ခံစာ"},
    "nav.contracts": {"th": "สัญญา", "en": "Contracts", "my": "စာချုပ်များ"},
    "nav.channels": {"th": "ช่อง", "en": "Channels", "my": "ချန်နယ်များ"},
    "nav.regs": {"th": "Reg รายเดือน", "en": "Monthly reg", "my": "လစဉ် Reg"},
    "nav.lists": {"th": "หยุด / คืนเงิน / ติดตาม", "en": "Stop / refund / follow-up", "my": "ရပ် / ပြန်အမ်း / စောင့်ကြည့်"},
    "nav.data": {"th": "นำเข้า / ส่งออก", "en": "Import / export", "my": "ထည့်သွင်း / ထုတ်ယူ"},
    "nav.settings": {"th": "ตั้งค่าและสถานะ", "en": "Settings & status", "my": "ဆက်တင်နှင့် အခြေအနေ"},
    "nav.theme_light": {"th": "Light", "en": "Light", "my": "Light"},
    "nav.theme_dark": {"th": "Dark", "en": "Dark", "my": "Dark"},
    "nav.who": {"th": "Admin · {u}", "en": "Admin · {u}", "my": "Admin · {u}"},
    "nav.logout": {"th": "ออกจากระบบ", "en": "Log out", "my": "ထွက်ရန်"},
    # ---- manage pages ----
    "mg.search_contracts": {"th": "ค้นหาชื่อ / รหัส / แอดมิน", "en": "Search name / id / admin", "my": "အမည် / id / အက်ဒမင် ရှာရန်"},
    "mg.filter": {"th": "กรอง", "en": "Filter", "my": "စစ်ထုတ်"},
    "mg.month": {"th": "เดือน", "en": "Month", "my": "လ"},
    "mg.status": {"th": "สถานะสัญญา", "en": "Contract status", "my": "စာချုပ်အခြေအနေ"},
    "mg.new_contract": {"th": "เพิ่มสัญญา", "en": "New contract", "my": "စာချုပ်အသစ်"},
    "mg.edit_contract": {"th": "แก้ไขสัญญา {id}", "en": "Edit contract {id}", "my": "စာချုပ် {id} ပြင်ဆင်"},
    "mg.count": {"th": "{n} รายการ", "en": "{n} rows", "my": "{n} ခု"},
    "mg.id": {"th": "รหัส", "en": "Id", "my": "Id"},
    "mg.section": {"th": "กลุ่ม", "en": "Section", "my": "အုပ်စု"},
    "mg.channels_n": {"th": "ช่อง", "en": "Channels", "my": "ချန်နယ်"},
    "mg.edit": {"th": "แก้ไข", "en": "Edit", "my": "ပြင်"},
    "mg.none": {"th": "ไม่พบรายการ", "en": "Nothing found", "my": "မတွေ့ပါ"},
    "mg.locked": {"th": "แก้ด้วยมือ", "en": "Edited by hand", "my": "လက်ဖြင့်ပြင်ထား"},
    "mg.locked_hint": {"th": "🔒 = แก้จากหน้าเว็บแล้ว การ import ชีตครั้งต่อไปจะไม่ทับข้อมูลรายการนี้",
                       "en": "🔒 = edited here; the next sheet import will not overwrite this row",
                       "my": "🔒 = ဤနေရာမှ ပြင်ထားသည်; နောက် sheet import တွင် မထပ်ရေးပါ"},
    "mg.view_detail": {"th": "ดูหน้าหลักฐาน", "en": "View evidence page", "my": "အထောက်အထားစာမျက်နှာ"},
    "mg.names": {"th": "ชื่อช่อง (บรรทัดละชื่อ)", "en": "Channel names (one per line)", "my": "ချန်နယ်အမည် (တစ်ကြောင်းတစ်ခု)"},
    "mg.names_help": {"th": "ตามที่พิมพ์ในชีต Cele Name; สัญญาเดียวคุมหลายช่องได้", "en": "As typed in the sheet's Cele Name column; one contract may cover several channels",
                      "my": "ဇယား Cele Name အတိုင်း; စာချုပ်တစ်ခုတွင် ချန်နယ်များစွာ ပါနိုင်သည်"},
    "mg.posts_per_day": {"th": "โพสต์ต่อวันต่อช่อง", "en": "Posts per day per channel", "my": "တစ်ရက် ပိုစ့်/ချန်နယ်"},
    "mg.pin_rule": {"th": "กติกา pin", "en": "Pin rule", "my": "Pin စည်းမျဉ်း"},
    "mg.pin_n": {"th": "จำนวน (N)", "en": "Count (N)", "my": "အရေအတွက် (N)"},
    "mg.pin_n_help": {"th": "ใช้กับ pin N ครั้ง/เดือน และ pin ทุก N วัน", "en": "Used by pin N×/month and pin every N days", "my": "တစ်လ N ကြိမ် / N ရက်တစ်ကြိမ် အတွက်"},
    "mg.period_from": {"th": "เริ่มสัญญา", "en": "Period from", "my": "စာချုပ်စ"},
    "mg.period_to": {"th": "สิ้นสุดสัญญา", "en": "Period to", "my": "စာချုပ်ဆုံး"},
    "mg.save": {"th": "บันทึก", "en": "Save", "my": "သိမ်း"},
    "mg.cancel": {"th": "ยกเลิก", "en": "Cancel", "my": "ပယ်ဖျက်"},
    "mg.saved": {"th": "บันทึกแล้ว", "en": "Saved", "my": "သိမ်းပြီး"},
    "mg.saved_add_channels": {"th": "สร้างสัญญาแล้ว — เพิ่มช่องด้านล่างได้เลย", "en": "Contract created — add its channels below",
                              "my": "စာချုပ်ဖန်တီးပြီး — အောက်တွင် ချန်နယ်ထည့်ပါ"},
    "mg.save_first": {"th": "บันทึกสัญญาก่อน แล้วจึงเพิ่มช่องได้", "en": "Save the contract first, then add channels", "my": "စာချုပ်သိမ်းပြီးမှ ချန်နယ်ထည့်နိုင်သည်"},
    "mg.no_channels": {"th": "ยังไม่มีช่องในสัญญานี้", "en": "No channels attached yet", "my": "ချန်နယ် မရှိသေးပါ"},
    "mg.add_channel_url": {"th": "ลิงก์ช่อง", "en": "Channel link", "my": "ချန်နယ်လင့်"},
    "mg.add_channel": {"th": "เพิ่มช่อง", "en": "Add channel", "my": "ချန်နယ်ထည့်"},
    "mg.add_channel_help": {"th": "รับ t.me/+hash (ส่วนตัว), t.me/username, t.me/s/username, @username · ถ้ามีช่องนี้อยู่แล้วจะผูกช่องเดิม ไม่สร้างซ้ำ",
                            "en": "Accepts t.me/+hash (private), t.me/username, t.me/s/username, @username · an existing channel is attached, not duplicated",
                            "my": "t.me/+hash, t.me/username, t.me/s/username, @username လက်ခံသည် · ရှိပြီးသား ချန်နယ်ကို ချိတ်ပေးမည်"},
    "mg.channel_title": {"th": "ชื่อช่อง (ถ้ามี)", "en": "Channel title (optional)", "my": "ချန်နယ်အမည် (ရွေးချယ်)"},
    "mg.channel_title_help": {"th": "ปล่อยว่างได้ ระบบจะอ่านชื่อจริงจาก Telegram", "en": "Leave blank to let the collector read it from Telegram", "my": "ဗလာထားနိုင်သည်"},
    "mg.channel_added": {"th": "เพิ่มช่องใหม่และผูกกับสัญญาแล้ว", "en": "Channel created and attached", "my": "ချန်နယ်အသစ် ထည့်ပြီး ချိတ်ပြီး"},
    "mg.channel_attached": {"th": "ผูกช่องที่มีอยู่แล้วกับสัญญานี้", "en": "Existing channel attached", "my": "ရှိပြီးသား ချန်နယ်ကို ချိတ်ပြီး"},
    "mg.channel_detached": {"th": "ถอดช่องออกจากสัญญาแล้ว (ตัวช่องยังอยู่)", "en": "Channel detached (the channel itself is kept)", "my": "ချန်နယ်ဖြုတ်ပြီး (ချန်နယ်ကို မဖျက်ပါ)"},
    "mg.bad_link": {"th": "ลิงก์ไม่ใช่ช่อง Telegram ที่ระบบตรวจได้ (ต้องเป็น t.me/+hash หรือ t.me/username)",
                    "en": "Not a Telegram channel link the collector can read (needs t.me/+hash or t.me/username)",
                    "my": "စစ်ဆေးနိုင်သော Telegram ချန်နယ်လင့် မဟုတ်ပါ (t.me/+hash သို့ t.me/username)"},
    "mg.detach": {"th": "ถอดออก", "en": "Detach", "my": "ဖြုတ်"},
    "mg.confirm_detach": {"th": "ถอดช่องนี้ออกจากสัญญา?", "en": "Detach this channel from the contract?", "my": "ဤချန်နယ်ကို စာချုပ်မှ ဖြုတ်မလား?"},
    "mg.search_channels": {"th": "ค้นหาชื่อ / username / key", "en": "Search title / username / key", "my": "အမည် / username / key ရှာရန်"},
    "mg.new_channel": {"th": "เพิ่มช่อง", "en": "New channel", "my": "ချန်နယ်အသစ်"},
    "mg.edit_channel": {"th": "แก้ไขช่อง {id}", "en": "Edit channel {id}", "my": "ချန်နယ် {id} ပြင်ဆင်"},
    "mg.kind": {"th": "ประเภท", "en": "Kind", "my": "အမျိုးအစား"},
    "mg.all_kinds": {"th": "ทุกประเภท", "en": "All kinds", "my": "အမျိုးအစားအားလုံး"},
    "mg.collector": {"th": "วิธีเก็บ", "en": "Collector", "my": "စုဆောင်းနည်း"},
    "mg.dead_only": {"th": "เฉพาะช่องตาย", "en": "Dead only", "my": "ပျက်သောချန်နယ်သာ"},
    "mg.linked_contracts": {"th": "สัญญาที่ผูก", "en": "Linked contracts", "my": "ချိတ်ထားသော စာချုပ်"},
    "mg.not_linked": {"th": "ยังไม่ผูกกับสัญญาใด", "en": "Not linked to any contract", "my": "စာချုပ်နှင့် မချိတ်ရသေး"},
    "mg.detach_hint": {"th": "ถอดช่องออกจากสัญญาได้ที่หน้าแก้ไขสัญญา", "en": "Detach from a contract on that contract's edit page", "my": "စာချုပ်ပြင်ဆင်စာမျက်နှာမှ ဖြုတ်နိုင်သည်"},
    "mg.attach_to": {"th": "ผูกกับสัญญา", "en": "Attach to contract", "my": "စာချုပ်နှင့် ချိတ်"},
    "mg.none_attach": {"th": "— ไม่ผูก —", "en": "— none —", "my": "— မချိတ် —"},
    "mg.channel_url_help": {"th": "เปลี่ยนลิงก์ = ย้ายช่อง: ระบบจะจำลิงก์เดิมไว้ใน \"ชื่อ/ลิงก์เดิม\" และเริ่มนับโพสต์ใหม่",
                            "en": "Changing the link moves the channel: the old link is kept under previous names/links and post history restarts",
                            "my": "လင့်ပြောင်းလျှင် ချန်နယ်ရွှေ့သည်: လင့်ဟောင်းကို မှတ်ထားပြီး ပိုစ့်မှတ်တမ်း အသစ်စသည်"},
    "mg.link_taken": {"th": "ลิงก์นี้เป็นของช่องอื่นอยู่แล้ว", "en": "Another channel already has this link", "my": "ဤလင့်ကို အခြားချန်နယ် သုံးပြီး"},
    "mg.state": {"th": "สถานะช่อง", "en": "Channel state", "my": "ချန်နယ်အခြေအနေ"},
    "mg.alive": {"th": "ปกติ", "en": "Alive", "my": "ပုံမှန်"},
    "mg.observed_title": {"th": "ชื่อที่เห็นบน Telegram", "en": "Title seen on Telegram", "my": "Telegram တွင် မြင်ရသောအမည်"},
    "mg.last_error": {"th": "ข้อผิดพลาดล่าสุด", "en": "Last error", "my": "နောက်ဆုံး အမှား"},
    "mg.dead_misses": {"th": "ครั้งที่ไม่พบติดกัน", "en": "Consecutive misses", "my": "ဆက်တိုက် မတွေ့သည့်အကြိမ်"},
    "mg.revive": {"th": "ฟื้นสถานะ (ไม่ตาย)", "en": "Revive (not dead)", "my": "ပြန်လည်ဖွင့် (မပျက်)"},
    "mg.revive_help": {"th": "ล้างสถานะตายและข้อผิดพลาด แล้วให้ระบบตรวจใหม่รอบถัดไป", "en": "Clears dead/error state so the next run checks it again", "my": "ပျက်/အမှား အခြေအနေကို ရှင်းပြီး နောက်အကြိမ် ပြန်စစ်မည်"},
    "mg.confirm_revive": {"th": "ล้างสถานะตายของช่องนี้?", "en": "Clear the dead state of this channel?", "my": "ဤချန်နယ်၏ ပျက်အခြေအနေကို ရှင်းမလား?"},
    "mg.revived": {"th": "ล้างสถานะตายแล้ว รอบตรวจถัดไปจะเช็คใหม่", "en": "Dead state cleared; the next run will check it again", "my": "ပျက်အခြေအနေ ရှင်းပြီး; နောက်အကြိမ် ပြန်စစ်မည်"},
    "ck.public_preview": {"th": "สาธารณะ (อ่าน preview ได้)", "en": "Public (preview readable)", "my": "အများပြည်သူ (preview ဖတ်နိုင်)"},
    "ck.public_no_preview": {"th": "สาธารณะ (ปิด preview)", "en": "Public (no preview)", "my": "အများပြည်သူ (preview ပိတ်)"},
    "ck.private": {"th": "ส่วนตัว (ลิงก์เชิญ)", "en": "Private (invite link)", "my": "Private (ဖိတ်ခေါ်လင့်)"},
    "ck.group": {"th": "กลุ่ม", "en": "Group", "my": "အုပ်စု"},
    "ck.not_channel": {"th": "ไม่ใช่ช่อง (ผู้ใช้/บอท)", "en": "Not a channel (user/bot)", "my": "ချန်နယ်မဟုတ် (user/bot)"},
    "ck.unknown": {"th": "ไม่ทราบ", "en": "Unknown", "my": "မသိ"},
    "cl.preview": {"th": "หน้า t.me/s", "en": "t.me/s preview", "my": "t.me/s preview"},
    "cl.profile": {"th": "หน้าโปรไฟล์ (ไม่เห็นโพสต์)", "en": "profile page (no posts)", "my": "ပရိုဖိုင် (ပိုစ့်မမြင်)"},
    "cl.invite": {"th": "หน้าลิงก์เชิญ (ไม่เห็นโพสต์)", "en": "invite page (no posts)", "my": "ဖိတ်ခေါ်စာမျက်နှာ (ပိုစ့်မမြင်)"},
    "cl.mtproto": {"th": "บัญชีสมาชิก (MTProto)", "en": "member account (MTProto)", "my": "အသင်းဝင်အကောင့် (MTProto)"},
    "cl.none": {"th": "ไม่เก็บ", "en": "not collected", "my": "မစုဆောင်း"},
    "cs.active": {"th": "ใช้งาน", "en": "Active", "my": "အသုံးပြုနေ"},
    "cs.paused": {"th": "พัก", "en": "Paused", "my": "ရပ်နား"},
    "cs.stopped": {"th": "หยุดแล้ว", "en": "Stopped", "my": "ရပ်ပြီး"},
    "cs.refund": {"th": "คืนเงิน", "en": "Refund", "my": "ပြန်အမ်း"},
    "qt.daily_post": {"th": "โพสต์รายวัน", "en": "Daily posts", "my": "နေ့စဉ်ပိုစ့်"},
    "qt.custom": {"th": "เงื่อนไขพิเศษ (ตรวจมือ)", "en": "Custom (manual check)", "my": "အထူး (လက်ဖြင့်စစ်)"},
    "pk.none": {"th": "ไม่มี pin", "en": "No pin", "my": "pin မရှိ"},
    "pk.daily": {"th": "pin ทุกวัน", "en": "Pin daily", "my": "နေ့တိုင်း pin"},
    "pk.per_month": {"th": "pin N ครั้ง/เดือน", "en": "Pin N×/month", "my": "တစ်လ N ကြိမ် pin"},
    "pk.every_days": {"th": "pin ทุก N วัน", "en": "Pin every N days", "my": "N ရက်တစ်ကြိမ် pin"},
    "sec.only_us": {"th": "เฉพาะเรา", "en": "Only us", "my": "ကျွန်ုပ်တို့သာ"},
    "sec.only_two": {"th": "2 ราย", "en": "Only two", "my": "၂ ဦးသာ"},
    "sec.only_three": {"th": "3 ราย", "en": "Only three", "my": "၃ ဦးသာ"},
    "sec.only_four": {"th": "4 ราย", "en": "Only four", "my": "၄ ဦးသာ"},
    "sec.only_five": {"th": "5 ราย", "en": "Only five", "my": "၅ ဦးသာ"},
    "sec.influencer": {"th": "อินฟลูเอนเซอร์", "en": "Influencer", "my": "အင်ဖလူအင်ဆာ"},
    "sec.unknown": {"th": "ไม่ระบุ", "en": "Unspecified", "my": "မသတ်မှတ်"},
    "err.required": {"th": "ต้องกรอก", "en": "Required", "my": "ဖြည့်ရန် လိုအပ်"},
    "err.month": {"th": "รูปแบบเดือนต้องเป็น YYYY-MM", "en": "Month must be YYYY-MM", "my": "လကို YYYY-MM ပုံစံ"},
    "err.date": {"th": "วันที่ไม่ถูกต้อง", "en": "Invalid date", "my": "ရက်စွဲ မမှန်"},
    "err.number": {"th": "ต้องเป็นตัวเลข", "en": "Must be a number", "my": "ကိန်းဂဏန်း ဖြစ်ရမည်"},
    "kpi.total": {"th": "สัญญาทั้งหมด", "en": "All contracts", "my": "စာချုပ်အားလုံး"},
    "kpi.fee_month": {"th": "ค่าจ้างเดือนนี้", "en": "Fees this month", "my": "ဤလ ကြေးငွေ"},
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
