# Jbac Telegram Auto Audit — Platinum Club MM

ระบบตรวจงานโพสต์โฆษณาใน Telegram ที่บริษัทจ้างเจ้าของช่องลง (แทนการตรวจด้วย Excel มือ)

**เอกสารหลัก:** [`docs/SPEC.md`](docs/SPEC.md) (ฉบับเดียวที่ใช้ตัดสิน) และ [`docs/ADR-001-hybrid-collection.md`](docs/ADR-001-hybrid-collection.md)
`HANDOFF.md` และ `TELEGRAM_MARKETING_DASHBOARD_HANDOFF_TH.md` เป็นเอกสารรุ่นก่อนที่เขียนก่อนเห็นข้อมูลจริง — เก็บไว้อ้างอิง แต่ SPEC.md แทนทุกจุดที่ขัดกัน

## สถานะ (25 ต.ค. 2026)
- ✅ ถอดข้อมูลจาก `Platinum Marketing Plan.xlsx` เป็น seed data + รายงานคุณภาพข้อมูล (`data/data_quality.md`)
- ✅ พิสูจน์ความเป็นไปได้ของการอ่าน `t.me/s/` (probe 108 username) → ตัดสินสถาปัตยกรรม Hybrid
- ✅ Dashboard วิเคราะห์จาก Excel: https://claude.ai/artifact/GQaZoeQFZqCCsgKLuDbZM6 (ส่วนตัว จนกว่าจะกดแชร์จากหน้า)
- ✅ ระบบตรวจจริง (Python service: FastAPI + scheduler + SQLite + Telethon) ใน `app/` ทดสอบในเครื่องแล้ว — ดู SPEC.md §10b, ADR-002 · dashboard และ DM 3 ภาษา ไทย / English / မြန်မာ
- ✅ ปรับ UI dashboard (26 ต.ค. 2026): หน้ารวมแบบ exception-first — การ์ด KPI + แถบสัดส่วนสถานะที่กดกรองได้ + นับถอยหลัง cutoff, ตารางแบ่งแถบตามความรุนแรง, ไอคอนสถานะ SVG, มือถือเป็นการ์ด
- ✅ Theme เดียวกับ Payment Recon + หน้าจัดการ (26 ต.ค. 2026): sidebar/topbar/การ์ดไล่สี สลับมืด-สว่าง (`localStorage.adm_theme`) · เมนู: ตรวจวันนี้ · รายงานรายเดือน (สัญญา × วัน) · สัญญา · ช่อง · Reg รายเดือน · หยุด/คืนเงิน/ติดตาม · นำเข้า/ส่งออก · ตั้งค่าและสถานะ — รายการที่แก้จากหน้าเว็บติด 🔒 และ import ชีตจะไม่ทับ (`docs/superpowers/specs/2026-10-26-manage-pages-design.md`)
- ✅ Deploy บน Coolify แล้ว (26 ต.ค. 2026): https://audit.jbacteam.com (HTTP Basic, user `admin`) — repo `github.com/n8nhosting/jbac-telegram-audit` (private, deploy key), push `main` แล้วสั่ง deploy ใน Coolify หรือ `POST /api/v1/deploy?uuid=<app>` (`deploy/README.md`)

## รัน service ในเครื่อง
```powershell
.\.venv\Scripts\python -m app.importer data\channels.seed.json data\probe_report.json --db data\audit.db
$env:DB_PATH="data/audit.db"; $env:DASH_PASSWORD="test"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8010      # http://127.0.0.1:8010 (admin / test)
```
scheduler เริ่ม collector สาธารณะหลังสตาร์ท 20 วินาที (ยิง t.me จริง ~6 นาที/รอบ) และ rollup ทุก 15 นาที

## โครงสร้าง
```
Platinum Marketing Plan.xlsx      ไฟล์ต้นทางของทีมการตลาด (ห้ามแก้)
tools/
  extract_channels.py             xlsx → data/*  (seed, สรุปรายเดือน, ประวัติ, reg, events, data_quality.md)
  probe_tme.py                    ยิง t.me/s/<username> ตรวจว่าอ่านได้จริง → data/probe_report.{json,md}
  build_dashboard_data.py         data/* → dashboard/data/*.csv
  tests/                          69 เทสต์ (unittest) + fixtures HTML จริง
data/                             ผลลัพธ์ (probe/raw/ ไม่เข้า git)
dashboard/                        index.html (หน้าใน Dashboard artifact) + data/*.csv + store/
docs/                             SPEC.md, ADR-001
```

## วิธีรัน (Windows)
Python ตัว default (3.14) ไม่มี openpyxl ให้ใช้ตัวของ scoop:
```powershell
$py = "C:\Users\ADMIN\scoop\apps\python313\current\python.exe"
& $py -I -m unittest discover -s tools/tests -t .        # เทสต์ทั้งหมด
& $py -I tools/extract_channels.py                       # ~20 วินาที → data/
& $py -I tools/probe_tme.py --limit 5                    # ลองก่อน 5 ช่อง; ไม่ใส่ --limit = ทั้งหมด (~5 นาที, GET อย่างเดียว)
& $py -I tools/probe_tme.py --rerender                   # สร้างรายงานใหม่จากหน้าที่เซฟไว้ ไม่ยิงซ้ำ
& $py -I tools/build_dashboard_data.py                   # → dashboard/data/*.csv
```
เมื่อชีตเดือนใหม่มา: รัน extract ด้วย `--roster "Nov 2026 MKT Pla"` แล้ว build_dashboard_data และอัปโหลด CSV ใหม่เข้า dashboard

## ตัวเลขที่ควรรู้ (ตุลาคม 2026)
| | |
|---|---|
| สัญญา / ยอดจ่าย | 87 / 24,785,602 MMK |
| ช่องจริง | 172 (97 สาธารณะ, 75 ลิงก์เชิญส่วนตัว) · 42 สัญญาคุมหลายช่อง |
| อ่านโพสต์จากภายนอกได้ | 67 ช่อง (39%) · สัญญาที่ตรวจครบจากภายนอก 31 (8.30M MMK) |
| ใช้ `#platinumclubmm` อยู่แล้ว | 49 ช่อง |
| สัญญาไม่มีผู้สมัครเลย ≥3 เดือน | 10 สัญญา = 2,045,666 MMK/เดือน |
