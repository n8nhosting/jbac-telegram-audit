# ADR-002 — รันระบบตรวจเป็น Python service ตัวเดียวบน Coolify (แทน Cloudflare Worker + D1)

สถานะ: **ตัดสินแล้ว** · 25 ตุลาคม 2026 · เปลี่ยนเฉพาะ "ที่รัน/ภาษา" ของ SPEC §4 — กติกาตรวจ (§6), data model (§5) และสถาปัตยกรรม Hybrid (ADR-001) คงเดิม

## บริบท
- SPEC ฉบับ 1.1 วาง Cloudflare Worker + D1 เป็นแกน เพราะตอนนั้นไม่มีเซิร์ฟเวอร์และต้องการค่าใช้จ่ายศูนย์
- 25 ต.ค. 2026 ผู้ใช้ให้เครื่อง Ubuntu ที่รัน **Coolify 4.5.0** (`coolify.jbacteam.com`, IP 210.246.215.196) ซึ่งใช้ deploy งานอื่นของบริษัทอยู่แล้ว (deploy จาก GitHub repo ด้วย Dockerfile/Docker Compose, มีโดเมน `*.jbacteam.com` ผ่าน Cloudflare)
- ส่วน MTProto (Telethon) ต้องเป็น process ที่รันต่อเนื่องอยู่แล้ว และ parser ของหน้า t.me ที่ทดสอบไว้เขียนด้วย Python (`tools/probe_tme.py`)

## การตัดสินใจ
1. **หนึ่ง container, หนึ่ง process**: FastAPI (dashboard + API) + APScheduler (collector ทุก 30 นาที, rollup, alert) + Telethon (เมื่อตั้งค่า session) ใน process เดียว เขียน SQLite (WAL) บน volume `/data`
2. **Deploy บน Coolify** ด้วย build pack Dockerfile จาก Git repo; env vars เป็น secret ของ Coolify; โดเมน `audit.jbacteam.com` (รอ DNS) หรือโดเมน sslip.io ชั่วคราว
3. **ไม่ใช้ Cloudflare Worker/D1** ในรุ่นนี้ — เก็บไว้เป็นทางเลือกถ้าอยากแยก public collector ออกจาก server ภายหลัง (parser เดียวกัน port ได้)
4. Telethon session สร้าง **บนเครื่องของผู้ใช้** ด้วย `tools/tg_login.py` แล้ววางเป็น env `TG_SESSION` (StringSession) — ไม่มี OTP/2FA ผ่านแชต ไม่มีไฟล์ session ใน repo

## เหตุผล
- ตัด limit ของ Worker (subrequest/CPU time) ที่ต้องแก้ด้วย Durable Object queue ออกไปทั้งหมด
- ลดจาก 2 ส่วนที่ต้อง deploy (Worker + collector) เหลือ 1
- ใช้โค้ด Python ที่มีเทสต์แล้วต่อได้ทันที (`parse_preview`, `parse_invite`, `parse_profile`)
- ผู้ใช้ดูแล Coolify อยู่แล้ว ไม่เพิ่มแพลตฟอร์มใหม่

## ผลที่ตามมา
- ต้องมี Git repo ให้ Coolify ดึง (ทีมเคยใช้ repo สาธารณะ) → repo นี้ต้องไม่มีข้อมูลธุรกิจ: `data/`, `dashboard/data/` อยู่ใน `.gitignore` และนำเข้า seed ผ่าน `POST /admin/import` แทน
- Dashboard ต้องมีรหัสผ่าน (HTTP Basic, env `DASH_PASSWORD`) เพราะเปิดสู่อินเทอร์เน็ต
- ถ้า container ล้ม งานเก็บข้อมูลหยุดทั้งหมดจนกว่าจะ restart (Coolify restart อัตโนมัติ) — ยอมรับได้ เพราะรอบเก็บทุก 30 นาทีและสถานะที่ขาดช่วงกลายเป็น `unverifiable` ไม่ใช่ `missed`
- Backup = สำเนาไฟล์ `audit.db` บน volume (Coolify backup หรือ cron `sqlite3 .backup`)
