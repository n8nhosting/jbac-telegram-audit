# Deploy บน Coolify (ADR-002)

ระบบเป็น container เดียว (Dockerfile ที่ root) เก็บ SQLite ที่ `/data/audit.db` ต้องมี volume ถาวร

## สิ่งที่ต้องเตรียมครั้งเดียว
1. **Git repo** ให้ Coolify ดึง — แนะนำ **repo ส่วนตัว + deploy key** เพราะโฟลเดอร์นี้มีเอกสารธุรกิจ (SPEC, handoff, แผน) แม้ `.gitignore` จะกัน `data/`, `dashboard/data/`, `*.xlsx`, `*.db`, `*.session` ไว้แล้ว
   - สร้าง private repo เช่น `n8nhosting/jbac-telegram-audit` แล้ว push โฟลเดอร์นี้ทั้งก้อน
   - ใน Coolify → Keys & Tokens → Private Keys → Create (หรือใช้ key ที่มี) → คัดลอก public key ไปใส่ GitHub repo → Settings → Deploy keys (read-only) → จด uuid ของ key ไว้ใส่ `PRIVATE_KEY_UUID`
   - ทางเลือก repo สาธารณะ (ถ้าตัดเอกสารธุรกิจออกก่อน): ใช้ `GIT_REPO=https://github.com/...` โดยไม่ตั้ง `PRIVATE_KEY_UUID`
2. **DNS**: `audit.jbacteam.com` → A record ไป `210.246.215.196` (หรือ proxied ผ่าน Cloudflare แบบ `admin.jbacteam.com`) ถ้ายังไม่มี ใช้โดเมน `*.sslip.io` ที่ Coolify สร้างให้ก่อนได้
3. **รหัสผ่าน dashboard** (`DASH_PASSWORD`) — บังคับ เพราะหน้าเว็บเปิดสู่อินเทอร์เน็ต
4. (ทางเลือก) **Telegram Bot** สำหรับแจ้งเตือน DM: สร้างบอทกับ @BotFather → `BOT_TOKEN`; ทักบอทก่อน 1 ครั้ง แล้วหา chat id ของตัวเอง → `OWNER_CHAT_ID`
5. (ทางเลือก, จำเป็นสำหรับช่องส่วนตัว/ปิด preview/pin) **บัญชี MTProto**: บนเครื่องของคุณรัน `.venv/Scripts/python tools/tg_login.py` → ได้ session string → ตั้ง `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` ใน Coolify (secret) ห้าม commit/ส่งผ่านแชต

## สร้างแอปด้วย API
```bash
export COOLIFY_URL=http://coolify.jbacteam.com:8000
export COOLIFY_TOKEN=...            # จาก Coolify → Keys & Tokens (rotate token ที่เคยวางในแชต)
export GIT_REPO=git@github.com:n8nhosting/jbac-telegram-audit.git   # private + deploy key (แนะนำ)
export PRIVATE_KEY_UUID=...                                          # uuid ของ key ใน Coolify
export DASH_PASSWORD='...'
export DOMAIN=https://audit.jbacteam.com   # ไม่ใส่ = ใช้ sslip.io
bash deploy/coolify_create_app.sh
```
สคริปต์จะ: หา server → สร้างโปรเจกต์ "Platinum Audit" → สร้างแอป `platinum-audit` (build pack Dockerfile, port 8000, health `/healthz`) → ตั้ง env → ขอ volume `/data` → สั่ง deploy

ถ้า API ไม่รับการสร้าง volume ให้เพิ่มใน UI: Application → Storages → Volume mount `audit-data` → `/data`

## หลัง deploy
```bash
curl -s https://audit.jbacteam.com/healthz
# นำเข้าสัญญา (ทำบนเครื่องที่มี data/ จาก tools/extract_channels.py)
curl -u admin:$DASH_PASSWORD -F seed=@data/channels.seed.json -F probe=@data/probe_report.json https://audit.jbacteam.com/admin/import
# สั่งเก็บข้อมูลรอบแรกทันที (ปกติ scheduler รันเองทุก 30 นาที) และประมวลผลวันนี้
curl -u admin:$DASH_PASSWORD -X POST https://audit.jbacteam.com/admin/run/collector
curl -u admin:$DASH_PASSWORD -X POST https://audit.jbacteam.com/admin/run/rollup
```
เปิด `https://audit.jbacteam.com/` → หน้าตาราง exception-first · สลับภาษา ไทย / English / မြန်မာ ได้ที่มุมบน (`?lang=th|en|my` จำค่าใน cookie; ถ้าไม่เลือก ใช้ภาษาจากเบราว์เซอร์ แล้วจึงไทย)

## ตัวแปรแวดล้อม
| ตัวแปร | ค่า/ความหมาย |
|---|---|
| `DB_PATH` | `/data/audit.db` |
| `AUDIT_TZ` | `Asia/Yangon` (วันตัดรอบ) |
| `DASH_USER` / `DASH_PASSWORD` | HTTP Basic ของ dashboard — ใช้ตัวอักษร ASCII เท่านั้น (เบราว์เซอร์ส่ง Basic auth แบบ ASCII) · ไม่ตั้ง password = เปิดโล่ง ใช้เฉพาะทดสอบในเครื่อง |
| `HASHTAG` | ค่าเริ่ม `#platinumclubmm` |
| `HASHTAG_ENFORCED_FROM` | วันที่เริ่มบังคับแท็ก (ก่อนหน้านั้นนับคำว่า platinum เป็น legacy_match) ค่าเริ่ม `2026-11-01` |
| `COLLECTOR_INTERVAL_MIN` | รอบเก็บข้อมูลสาธารณะ ค่าเริ่ม 30 |
| `FETCH_DELAY_MIN` / `FETCH_DELAY_MAX` | หน่วงระหว่างช่อง (วินาที) 1.5 / 2.5 |
| `BOT_TOKEN` / `OWNER_CHAT_ID` | แจ้งเตือน DM 18:00, 23:50, 00:06 |
| `ALERT_LANGS` | ภาษาของ DM คั่นด้วยจุลภาค เช่น `th,my` (ค่าเริ่ม `th`; รองรับ th / en / my ส่งทุกภาษาที่ระบุในข้อความเดียว) |
| `TG_API_ID` / `TG_API_HASH` / `TG_SESSION` | MTProto collector (ปิดถ้าไม่ตั้ง) |
| `MAX_JOINS_PER_RUN` | จำนวน join ช่องส่วนตัวสูงสุดต่อรอบ ค่าเริ่ม 3 |

## อัปเดตเดือนใหม่
รัน `tools/extract_channels.py --roster "Nov 2026 MKT Pla"` ในเครื่อง แล้ว `POST /admin/import` ซ้ำ (idempotent: อัปเดตสัญญาเดิม เพิ่มสัญญาใหม่)
