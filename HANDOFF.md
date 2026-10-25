# HANDOFF — ระบบตรวจสอบโพสต์ Telegram ของฝ่ายการตลาด (Platinum Club MM)

> สถานะ: **ยังไม่เริ่มเขียนโค้ด** — เอกสารนี้คือข้อสรุปการออกแบบทั้งหมดที่คุยกันไว้
> Workspace ปัจจุบันว่างเปล่า (ไม่มีไฟล์โปรเจกต์ ไม่มี git repo)

---

## 1. เป้าหมายธุรกิจ

บริษัทจ้างฝ่ายการตลาด (agency) ให้โพสต์ **รูปภาพ / ลิงก์โปรโมท** ลงในกลุ่มและแชนแนล Telegram หลายร้อยแห่ง
ปัจจุบันพนักงานตรวจด้วย **Google Sheet ด้วยมือ** (เปิดลิงก์ทีละอัน นับจำนวน นับยอดวิว แล้วกด dropdown "On Process")

ต้องการ:

1. ตรวจสอบได้จริงว่าโพสต์ถูกโพสต์จริง ในช่องที่กำหนด ในวันที่กำหนด
2. Dashboard ที่อ่านเข้าใจง่าย แทนชีต manual
3. รู้ว่าแต่ละช่องทำตามโควตา (กี่โพสต์/วัน) หรือไม่
4. บังคับใช้แฮชแท็ก `#platinumclubmm` ทุกโพสต์เพื่อให้ตรวจจับได้ง่าย

**ข้อจำกัดสำคัญจากผู้ใช้:** ต้อง **ไม่ให้ agency รู้ว่ามีระบบตรวจ** → ห้ามใช้บอทที่ต้องถูกเพิ่มเป็นแอดมินในกลุ่ม

---

## 2. ข้อมูลที่ยืนยันแล้ว

| หัวข้อ | ข้อสรุป |
|---|---|
| จำนวนกลุ่ม/ช่อง | หลักร้อย (hundreds) |
| ประเภท | จากชีตตัวอย่าง ลิงก์ทั้งหมดเป็น **public channel** (`t.me/Newmoviechannel7777`, `t.me/s/moviegood`, `t.me/Mini_Drama_Channel`, …) |
| การเข้าถึง | ต้องไม่ให้ agency รู้ → ไม่ใช้ Bot API ที่ต้องเป็นแอดมิน |
| Hashtag | `#platinumclubmm` ทุกโพสต์ |
| รูปแบบงาน | 1 ช่อง = 1 แถว มีช่วงสัญญา + streak ต่อเนื่อง + ยอดผู้ติดตาม/ยอดวิว |

### ตัวอย่างข้อมูลจากชีต (คอลัมน์ที่เห็น)

```
Reg-0..Reg-4 | @hetwaiyan2005 | 31th time continue | 3.10.26 - 3.11.26 |
Bollywood Movies | https://t.me/... (1-3 ลิงก์โพสต์) |
sub -30K / 3 day ago view -829 / 7 day ago view -1.4K | [On Process]
```

---

## 3. ทางเลือกที่พิจารณาแล้ว (และเหตุผลที่ไม่เลือก)

| วิธี | ผลสรุป |
|---|---|
| **Bot API + บอทเป็นแอดมิน** | ❌ agency เห็นบอทในกลุ่ม, อ่านย้อนหลังไม่ได้, ต้องมีคนกดเพิ่มบอททุกช่อง |
| **MTProto userbot (Telethon/GramJS) เข้าเป็นสมาชิก** | ❌ **การ join ปรากฏในรายชื่อสมาชิก** ซึ่งแอดมินเห็น, เสี่ยงบัญชีถูก ban, ต้องมี VPS เปิด 24/7, ชนเพดาน ~500 กลุ่ม/บัญชี |
| **Cloudflare Worker ถือ session MTProto** | ❌ Worker ไม่มี long-running process ไม่มี persistent state ไม่มี interactive login (OTP/2FA), IP datacenter เสี่ยงถูกทัก |
| **✅ อ่าน public channel ผ่าน `t.me/s/<username>`** | **เลือกวิธีนี้** — ไม่ต้องมีบัญชี ไม่ต้อง join ไม่มีร่องรอย ตรวจจากภายนอกได้ 100% |

### เหตุผลที่วิธีที่เลือกชนะ

- public channel มีหน้า preview ที่ไม่ต้องล็อกอิน: `https://t.me/s/<username>`
- ค้นหาแฮชแท็กในช่องได้: `https://t.me/s/<username>?q=%23platinumclubmm`
- ดูโพสต์เก่าได้ด้วย pagination: `t.me/s/<username>?before=<message_id>`
- เห็น **ยอดผู้ติดตาม** ในหัวหน้า และ **ยอดวิวต่อโพสต์** (channel เท่านั้นที่มี views)
- **ดังนั้น Cloudflare Worker ทำงานนี้ได้ทั้งหมด** → ฟรี, ไม่ต้องดูแลเซิร์ฟเวอร์

---

## 4. สถาปัตยกรรมที่แนะนำ

```
┌────────────────────────────────────────────┐
│  Cloudflare Worker  (single Worker)        │
│                                            │
│  GET  /                → dashboard (HTML)  │
│  GET  /api/summary     → KPI วันนี้         │
│  GET  /api/channels    → ตารางหลัก          │
│  GET  /api/evidence/:id→ หลักฐานโพสต์       │
│  GET  /export.csv      → ส่งให้ agency      │
│  POST /api/admin/*     → ตั้งค่า/นำเข้าช่อง  │
│                                            │
│  Cron: */30 นาที → เก็บ snapshot           │
│  Cron: 23:50     → rollup + แจ้งเตือน DM    │
└──────────────┬─────────────────────────────┘
               │ D1 (SQLite)
               ▼
     groups · posts · snapshots · rollups
               │
               ▼
   Telegram Bot (DM ถึงเจ้าของเท่านั้น)
   ⚠️ บอทไม่ต้องเข้ากลุ่ม/ช่องไหนเลย
```

**หมายเหตุ:** บอท Telegram ใช้ **ส่งสรุป/แจ้งเตือนเข้า DM ของเจ้าของ** เท่านั้น — ไม่เกี่ยวกับการเก็บข้อมูล และ agency ไม่มีทางเห็น

---

## 5. กติกาการตรวจ (Verification rules)

โพสต์จะถูกนับเป็น "ผ่าน" เมื่อ **ครบทุกข้อ**:

1. อยู่ในช่องที่อยู่ในรายการที่อนุมัติ (`groups.status = active`)
2. มีแฮชแท็ก `#platinumclubmm` (case-insensitive)
3. มี **(รูป หรือ วิดีโอ หรือ ลิงก์)** อย่างน้อย 1 อย่าง
4. `message.date` อยู่ในช่วงเวลาของวันนั้นตาม **timezone ที่กำหนด** (ต้องตัดสิน: `Asia/Yangon` UTC+6:30 หรือ `Asia/Bangkok` UTC+7 — ดูข้อ 9)
5. ไม่ซ้ำ: unique key = `(chat_id, message_id)`

### Anti-cheat ที่ควรใส่

- **Nonce รายวัน** (ตัวเลือกเสริม): บังคับ `#platinumclubmm #d20261025` → กันเอาโพสต์/ภาพเก่ามาใช้ซ้ำ
- **Streak / consecutive days**: ตรงกับคอลัมน์ "31th time continue" ในชีตเดิม — คำนวณอัตโนมัติ
- **Duplicate-caption detection**: ถ้าโพสต์เดียวกันไปลงหลายช่อง = ถูก (นั่นคืองาน) แต่ถ้าลงช่องเดิมซ้ำเกินโควตา = ไม่นับเพิ่ม
- **จับ "โพสต์แล้วลบ"**: เก็บ snapshot ตั้งแต่เห็นครั้งแรก (ถ้าลบทีหลัง ยังมีหลักฐานว่าเคยมี)

---

## 6. Data model (D1 / SQLite)

```sql
CREATE TABLE groups (
  id            INTEGER PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,      -- 'moviegood'
  url           TEXT NOT NULL,             -- 'https://t.me/moviegood'
  title         TEXT,                      -- ชื่อที่ดึงมาได้
  agency        TEXT,                      -- ผู้รับผิดชอบ
  tier          TEXT DEFAULT 'A',          -- A/B/C ← ใช้กำหนดโควตาเป็นกลุ่ม
  quota_per_day INTEGER DEFAULT 1,
  contracted_from TEXT,                    -- ISO date
  contracted_to   TEXT,
  status        TEXT DEFAULT 'active',     -- active | paused | dead | renamed
  last_checked  TEXT,
  last_error    TEXT,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE posts (
  id           INTEGER PRIMARY KEY,
  group_id     INTEGER NOT NULL REFERENCES groups(id),
  message_id   INTEGER NOT NULL,
  posted_at    TEXT NOT NULL,              -- ISO UTC + เก็บ local_date ด้วย
  local_date   TEXT NOT NULL,              -- '2026-10-25' ตาม timezone ที่ตั้ง
  has_tag      INTEGER NOT NULL,           -- 0/1
  has_media    INTEGER NOT NULL,
  has_link     INTEGER NOT NULL,
  text_preview TEXT,
  permalink    TEXT,                       -- https://t.me/<user>/<msg_id>
  views        INTEGER,
  qualifies    INTEGER NOT NULL,           -- ผ่านเงื่อนไขข้อ 5 หรือไม่
  first_seen   TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(group_id, message_id)
);

CREATE TABLE snapshots (              -- เก็บรายวันเพื่อคิด delta
  id            INTEGER PRIMARY KEY,
  group_id      INTEGER NOT NULL REFERENCES groups(id),
  captured_at   TEXT NOT NULL,
  subscribers   INTEGER,
  posts_total   INTEGER
);

CREATE TABLE post_view_snapshots (    -- วัดยอดวิว ณ วันที่ 3 / 7 หลังโพสต์
  id         INTEGER PRIMARY KEY,
  post_id    INTEGER NOT NULL REFERENCES posts(id),
  captured_at TEXT NOT NULL,
  views      INTEGER
);

CREATE TABLE daily_rollup (           -- สรุปไว้ทำ trend/CSV เร็ว
  id             INTEGER PRIMARY KEY,
  local_date     TEXT NOT NULL,
  group_id       INTEGER NOT NULL REFERENCES groups(id),
  required       INTEGER,
  qualified      INTEGER,
  status         TEXT,   -- ok | partial | missed | waiting | dead | invalid
  UNIQUE(local_date, group_id)
);
```

**ปริมาณข้อมูล:** 300 ช่อง × ~2 โพสต์/วัน ≈ 600 แถว/วัน ≈ 18k แถว/เดือน — D1 free tier รับสบาย ไม่ต้องเก็บไฟล์รูป

---

## 7. Dashboard spec (แทนชีตเดิม)

### หลักการ: **exception-first**

ตาราง 300 แถวอ่านไม่ไหว → default แสดงเฉพาะแถวที่ยังไม่ผ่าน

**แถว KPI ด้านบน**
`วันนี้ 214/300 ช่องครบ` · `Compliance 71%` · `ขาด 86` · `เลย cutoff แล้ว 12` · `โพสต์รวม 468`

**ตารางหลัก** (1 แถว = 1 ช่อง)

| คอลัมน์ | ที่มา |
|---|---|
| ช่อง (ชื่อ + @username + ลิงก์) | `groups` |
| Tier / โควตา | `groups` |
| โพสต์วันนี้ | `posts` (qualifies=1) |
| แฮชแท็ก ✅/❌ | `posts.has_tag` |
| รูป/ลิงก์ ✅/❌ | `posts.has_media`, `has_link` |
| สถานะ | คำนวณจาก `daily_rollup` |
| ขาดกี่ครั้ง/30 วัน | นับ `status='missed'` — **ใช้แทน heatmap** และ sort ห่วยสุดขึ้นบน |
| โพสต์ล่าสุด (เวลา) | `posts.posted_at` |
| ผู้ติดตาม / Δ รายวัน | `snapshots` |
| ยอดวิว 3 วัน / 7 วัน | `post_view_snapshots` |
| หลักฐาน | ลิงก์ permalink เปิดดูได้ |

**สถานะ 6 แบบ**

| สถานะ | ความหมาย |
|---|---|
| ✅ `ok` | ครบโควตาแล้ว |
| 🟡 `waiting` | ยังไม่ถึง cutoff และยังไม่ครบ |
| ❌ `missed` | เลย cutoff แล้วยังไม่ครบ |
| 🚫 `invalid` | โพสต์แล้วแต่ไม่ผ่านเงื่อนไข (ไม่มีแท็ก/ไม่มีรูป/ผิดวัน) |
| ⚪ `dead` | ช่องลบ / เปลี่ยนชื่อ / ลิงก์เสีย |
| ⏸ `paused` | อยู่นอกช่วงสัญญา |

**หน้าอื่น**
- รายละเอียดช่อง: timeline โพสต์ทั้งหมด + หลักฐาน + กราฟผู้ติดตาม
- Trend 30 วัน (ภาพรวม ไม่ใช่ heatmap 300 แถว)
- Scoreboard ราย agency (% compliance, จำนวนครั้งที่ขาด)
- Export CSV (มีคอลัมน์เดียวกับชีตเดิม เพื่อให้พนักงานใช้ต่อได้ทันที)

### Mapping จากชีตเดิม → ระบบใหม่

| ชีต | ใหม่ | หมายเหตุ |
|---|---|---|
| `@hetwaiyan2005` | ผู้โพสต์ | ⚠️ เห็นได้เฉพาะโพสต์ที่ไม่ใช่ anonymous admin |
| `31th time continue` | streak | คำนวณอัตโนมัติ |
| `3.10.26 - 3.11.26` | ช่วงสัญญา | ต้องแปลงเป็น ISO (ฟอร์แมตเดิมกำกวม) |
| ชื่อช่อง | title + สถานะช่อง | จับการเปลี่ยนชื่อ/ช่องตายได้ |
| ลิงก์ t.me 1–3 อัน | หลักฐาน | กดดูได้ |
| `sub -30K` | subscribers snapshot | เก็บทุกวัน → เห็นการเติบโตจริง |
| `3/7 day ago view` | view snapshots | คำนวณเอง ไม่ต้องพิมพ์ |
| `[On Process]` dropdown | **ตัดทิ้ง** | ระบบตัดสินเอง |
| `Reg-0 … Reg-4` | ❓ **ไม่ทราบความหมาย** | ต้องถามเจ้าของข้อมูล |

---

## 8. ความเสี่ยง / ข้อจำกัดที่ต้องรู้

1. **โพสต์ที่เป็นรูปเปล่าไม่มีแคปชั่น → ไม่มีแฮชแท็กให้ค้น**
   → ต้องกำหนดในสัญญาว่าแคปชั่นต้องมี `#platinumclubmm` เสมอ ไม่งั้นต้องใช้วิธีเดา (นับโพสต์ทุกอันในช่วงเวลา) ซึ่งเถียงยาก
2. **`t.me/s/` เห็นแค่ ~20 โพสต์ล่าสุด** → ต้องเก็บ snapshot สม่ำเสมอ ถ้าอยากได้ข้อมูลย้อนหลัง 30 วัน ต้องเริ่มเก็บตั้งแต่วันแรก
3. **Rate limit / 429 จาก t.me** — ถ้ายิงรัวจาก IP ของ Cloudflare (shared IP) อาจโดนจำกัด
   → ทยอยยิงแบบ sequential + หน่วง 1–2 วินาที (300 ช่อง ≈ 10 นาที/รอบ) และใช้ Durable Object เป็นคิวตัวเดียว
4. **Anonymous admin** — โพสต์จากแอดมินไม่ระบุชื่อ จะยืนยันไม่ได้ว่าใครโพสต์ (ยืนยันได้แค่ว่าโพสต์เกิดขึ้น) → อย่าผูก KPI กับชื่อบัญชี
5. **ช่อง private** — ถ้ามีช่อง private หลุดเข้ามาในลิสต์ จะอ่านไม่ได้เลย → ต้องมีสถานะ `dead/unsupported` และแจ้ง owner
6. **agency อาจเปลี่ยนชื่อช่องหรือย้ายช่อง** → ต้องเช็ก title ทุกวัน และเตือนเมื่อเปลี่ยน
7. **timezone ต้องฟิกซ์ให้ชัด** — cutoff ของ "วัน" ต้องตรงกับที่ตกลงในสัญญา

---

## 9. คำถามที่ยังไม่ได้คำตอบ (blocker ก่อนสร้าง)

1. **Timezone ที่ใช้ตัดวัน**: `Asia/Yangon` (UTC+6:30) หรือ `Asia/Bangkok` (UTC+7)? — กระทบทุกการคำนวณโควตา
2. **`Reg-0 … Reg-4` ในชีตคืออะไร?** (จำนวนครั้ง? ภูมิภาค? จำนวนโพสต์?)
3. **โควตาจริงต่อช่อง**: 1 โพสต์/วัน ทุกช่อง หรือแบ่ง tier (เช่น A=3, B=1)?
4. **CSV/รายชื่อช่องจริง** ทั้งหมด (300+ แถว) พร้อมช่วงสัญญา
5. **ต้องการ nonce รายวัน** (`#d20261025`) หรือใช้แค่ `#platinumclubmm`?
6. **ช่องทางแจ้งเตือน**: DM Telegram / อีเมล / LINE?
7. จำนวน agency มีเจ้าเดียวหรือหลายเจ้า (กระทบหน้า scoreboard)
8. ต้อง deploy ขึ้น Cloudflare จริง หรือรันในเครื่องก่อน?

---

## 10. ลำดับงานที่แนะนำ (ถ้าจะเริ่มสร้าง)

1. **Fetch & parse prototype** — Worker (หรือ Node script) ดึง `t.me/s/<username>` ของช่องตัวอย่าง 5–10 ช่อง แล้ว parse: title, subscribers, 20 โพสต์ล่าสุด, has_tag, has_media, has_link, views, permalink
   → พิสูจน์ว่า parse ได้จริงก่อนลงทุนทำ UI
2. **Schema + D1 migrations** — สร้างตารางตามข้อ 6 + seed ข้อมูลตัวอย่าง
3. **Dashboard v1** — KPI + ตาราง exception-first + หน้าหลักฐาน
4. **Cron collector** — เก็บ snapshot ทุก 30 นาที, rollup รายวัน, จัดการ 429/retry
5. **Alert DM** — สรุป 18:00 (เตือน) และ 23:50 (สรุปหักเงิน)
6. **CSV import/export** — นำเข้าลิสต์ช่อง, export ให้agencyดู
7. **Deploy + ตั้ง cron + ตรวจ 2–3 วันจริง**

---

## 11. Stack ที่ตกลง

| ส่วน | เลือก |
|---|---|
| Runtime | Cloudflare Worker (fetch + cron) |
| DB | Cloudflare D1 |
| Frontend | HTML + minimal JS (server-rendered จาก Worker) หรือ static + fetch API |
| แจ้งเตือน | Telegram Bot API → DM เจ้าของเท่านั้น |
| UI text | ไทย (ผู้ใช้เป็นคนไทย) |
| Hosting | Cloudflare (ฟรี tier พอ) |

**ตัดออกแล้ว:** Telethon / MTProto / VPS / Bot ในกลุ่ม / Google Sheet

---

## 12. ไฟล์ที่ควรมีในโปรเจกต์ (เป้าหมาย)

```
wrangler.jsonc
package.json
src/index.ts            # router + dashboard
src/telegram.ts         # fetch t.me/s + parser
src/verify.ts           # กติกาข้อ 5
src/db.ts               # queries
src/cron.ts             # collector + rollup + alert
src/views/              # HTML templates
migrations/0001_init.sql
samples/channels.seed.json
README.md
```
