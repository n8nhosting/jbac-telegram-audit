# Audit Service (Coolify) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single deployable service that imports the Excel-derived seed, collects posts/subscriber snapshots from Telegram (public preview pages now, MTProto when a session is supplied), evaluates each contract per Asia/Yangon day, shows a Thai exception-first dashboard, and DMs the owner — running as one container on the user's Coolify server.

**Architecture:** One Python process: FastAPI serves the dashboard/API; an in-process APScheduler runs the public collector (httpx, sequential, 1.5–2.5 s apart), the optional Telethon collector, the daily rollup and the alerts; SQLite (WAL) on a mounted volume is the only state. Parsers already tested in `tools/probe_tme.py` move to `app/tgweb.py` and are re-exported so the probe keeps working.

**Tech Stack:** Python 3.12 (container) / 3.13 (local venv `.venv`), FastAPI, uvicorn, Jinja2, httpx, APScheduler 3, Telethon, sqlite3 (stdlib), unittest. Docker image built by Coolify from a Git repo (Dockerfile build pack).

**Spec:** `docs/SPEC.md` (§5 data model, §6 rules, §7 dashboard) with hosting changed by ADR-002 (this plan's Task 0): Coolify instead of Cloudflare Worker/D1.

## Global Constraints

- Day cutoff timezone: **Asia/Yangon** (user decision 2026-10-25); all `local_date` values derive from it.
- Hashtag `#platinumclubmm`, case-insensitive, whole token; `#platinumclubmm_extra` does not count. Before `HASHTAG_ENFORCED_FROM` (env, ISO date, default `2026-11-01`) a post whose text contains `platinum` counts as `legacy_match`.
- Media = photo or video; stickers never count. Link = anchor in text or link preview.
- Never turn "no access" into "missed": a channel the service cannot read yields `unverifiable`.
- Outbound to t.me: GET only, sequential, random 1.5–2.5 s delay, browser UA, retry 429/5xx with backoff, never join from the web path. Telethon joins an invite at most once per channel and at most 3 joins per run.
- Secrets only via environment variables (`DASH_PASSWORD`, `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `BOT_TOKEN`, `OWNER_CHAT_ID`); none in the repo, logs or templates. The repo may become public: `data/` and `dashboard/data/` stay git-ignored; the seed is uploaded through `/admin/import`.
- Tests: `.venv/Scripts/python -I -m unittest discover -s tests -t .` must pass after every task, plus the existing `tools/tests` suite.
- UI text Thai; numbers tabular; works at 400 px width.

## Review Focus

1. A contract whose only channels are private and MTProto is not configured must show `unverifiable`, never `missed` — Task 5 `test_private_without_mtproto_is_unverifiable`.
2. A post at 23:45 UTC+6:30 vs 00:15 next day must land on the right Yangon date — Task 5 `test_local_date_yangon_boundary`.
3. Preview page returns 200 but has no `.tgme_channel_info` (restricted/no preview) must mark the channel `profile`-collected, not create posts or errors — Task 4 `test_collector_marks_no_preview_channel`.
4. Importing the same seed twice must not duplicate channels or contracts (idempotent upsert) — Task 3 `test_import_twice_is_idempotent`.
5. Dashboard with an empty database must render (no 500) and say no data — Task 7 `test_dashboard_renders_empty_db`.

---

### Task 0: ADR-002 and project skeleton

**Files:**
- Create: `docs/ADR-002-hosting-coolify-python.md`, `app/__init__.py`, `app/config.py`, `requirements.txt`, `Dockerfile`, `.dockerignore`, `tests/__init__.py`, `tests/test_config.py`
- Modify: `.gitignore` (add `.venv/`, `*.db`, `*.session`, `data/`, `dashboard/data/`, `dashboard/store/`)

**Interfaces:**
- Produces: `app.config.Settings` dataclass with fields `db_path: str` (default `data/audit.db`), `tz: str` (`Asia/Yangon`), `hashtag: str` (`#platinumclubmm`), `hashtag_enforced_from: str` (`2026-11-01`), `dash_user: str` (`admin`), `dash_password: str | None`, `tg_api_id: int | None`, `tg_api_hash: str | None`, `tg_session: str | None`, `bot_token: str | None`, `owner_chat_id: str | None`, `fetch_delay_min: float` (1.5), `fetch_delay_max: float` (2.5), `collector_interval_min: int` (30), `public_base_url: str | None`; `load_settings(env: Mapping[str,str]) -> Settings`; `settings.mtproto_enabled` property (all three TG_* set); `settings.alerts_enabled`.

- [ ] Write `tests/test_config.py`: `test_defaults` (empty env → tz Asia/Yangon, hashtag, db_path, mtproto_enabled False), `test_env_overrides` (TG_API_ID="123" → int 123, mtproto_enabled True when all three set).
- [ ] Run: `.venv/Scripts/python -I -m unittest discover -s tests -t .` → FAIL (ModuleNotFoundError app.config)
- [ ] Implement `app/config.py`; write ADR-002 (why Coolify + single Python service replaces Worker/D1: server exists, MTProto needs a long-lived process, parsers already in Python, no subrequest limits; consequences: SQLite volume, one container, Telethon session created locally by the user).
- [ ] Write `Dockerfile` (python:3.12-slim, `pip install -r requirements.txt`, copy `app/`, `EXPOSE 8000`, `CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`), `.dockerignore`, `requirements.txt` pinned from the venv freeze.
- [ ] Run tests → PASS.

### Task 1: Database schema and helpers

**Files:**
- Create: `app/db.py`, `app/migrations/0001_init.sql`, `tests/test_db.py`

**Interfaces:**
- Produces: `connect(db_path) -> sqlite3.Connection` (row_factory=Row, WAL, foreign_keys on), `migrate(conn)` (applies `app/migrations/*.sql` in order, records in `schema_migrations(name)`), `now_utc() -> str` ISO. Tables exactly as SPEC §5 plus: `channels.collector` ∈ `preview|profile|invite|mtproto|none`, `alerts(id, local_date, kind, sent_at, UNIQUE(local_date, kind))`, `runs(id, kind, started_at, finished_at, ok INTEGER, detail TEXT)`.

- [ ] Write `tests/test_db.py`: `test_migrate_creates_tables` (in-memory `:memory:` → set of table names ⊇ {contracts, channels, contract_channels, channel_aliases, posts, pin_snapshots, snapshots, post_view_snapshots, daily_rollup, reg_monthly, price_history, channel_events, alerts, runs}), `test_migrate_is_idempotent` (second call no error, one row per migration).
- [ ] Run → FAIL. Implement. Run → PASS.

### Task 2: Move parsers to `app/tgweb.py`

**Files:**
- Create: `app/tgweb.py`
- Modify: `tools/probe_tme.py` (replace parser definitions with `from app.tgweb import parse_count, extract_hashtags, is_preview_url, parse_post, summarize_posts, parse_preview, parse_invite, parse_profile, HASHTAG` keeping the same names)
- Test: existing `tools/tests/test_probe_parse.py` must stay green; new `tests/test_tgweb.py`

**Interfaces:**
- Produces: the same functions as today plus `async fetch_text(client: httpx.AsyncClient, url: str, retries=3) -> FetchResult(ok: bool, status: int|None, final_url: str, html: str, error: str|None)` and `search_url(username) -> str` = `https://t.me/s/{username}?q=%23platinumclubmm`, `preview_url(username)`, `profile_url(username)`, `invite_url(hash)`.

- [ ] Write `tests/test_tgweb.py`: `test_urls` (exact strings), `test_parse_preview_fixture` (reuse `tools/tests/fixtures/tgme_s_mini_drama_channel.html`: 20 posts, subscribers 108000).
- [ ] Run both suites → new test FAILS (no module). Move code. Run both suites → PASS (69 + new).

### Task 3: Seed importer

**Files:**
- Create: `app/importer.py`, `tests/test_importer.py`, `tests/fixtures/seed_small.json` (2 contracts, 4 channels incl. one private, one old link, one external, reg_history, price_history_note)

**Interfaces:**
- Consumes: `channels.seed.json` shape from `tools/extract_channels.py` (`contracts[]`, `channels[]`).
- Produces: `import_seed(conn, seed: dict, probe: dict | None = None) -> ImportStats(contracts, channels, aliases, reg_rows)`. Mapping: contract → `contracts` upsert by `sheet_contract_id`; each non-old channel → `channels` upsert by `channel_key` (`pub:<username>` / `prv:<hash>`; external links skipped) with `kind` from seed + optional probe `profile_kind` (`preview`→`public_preview`/collector `preview`; `channel_no_preview`/`restricted_channel`→`public_no_preview`/`profile`; `user_or_bot`→`not_channel`/`none`; private→`private`/`invite`); old links → `channel_aliases`; `reg_history` → `reg_monthly` resolved to `YYYY-MM` relative to the contract month (same rule as `tools/extract_channels.resolve_reg_months`); `price_history_note` → `price_history`.

- [ ] Write tests: `test_import_counts` (2 contracts, 3 channels, 1 alias, reg rows = len(reg_history)), `test_import_twice_is_idempotent` (counts unchanged), `test_collector_from_probe_kind`.
- [ ] Run → FAIL. Implement. Run → PASS.
- [ ] Add CLI: `python -m app.importer data/channels.seed.json [data/probe_report.json]` and run it against the real seed locally → print stats (87 contracts, 178 channels, 36 aliases).

### Task 4: Public collector

**Files:**
- Create: `app/collector.py`, `tests/test_collector.py`

**Interfaces:**
- Consumes: `app.tgweb` parsers/fetch, `app.db`.
- Produces: `async run_public_collector(conn, settings, client=None, sleep=asyncio.sleep) -> RunStats(channels, posts_new, posts_updated, snapshots, renamed, errors)`; per channel: collector `preview` → GET `search_url` → upsert posts (`source='preview'`, `has_tag`, `has_media`, `has_link`, `views`, `permalink`, `posted_at`, `local_date` via `app.rules.local_date_of`) + snapshot (title, subscribers) + rename detection (title differs from `channels.title` → `channel_aliases` row + `channel_events(event='renamed')`); if page has no channel info → set `collector='profile'`; collector `profile` → GET profile → snapshot or `channel_events(dead)` when `missing`; collector `invite` → GET invite → snapshot/rename; `none` skipped. Errors recorded in `channels.last_error`, never raise. `upsert_post(conn, channel_id, post: dict, source) -> bool(new)`.

- [ ] Write tests with a fake client returning fixture HTML: `test_collector_upserts_posts_and_snapshot` (fixture preview → 20 posts, 1 snapshot, subscribers 108000), `test_collector_marks_no_preview_channel` (profile fixture under /s/ final URL without /s/ → collector becomes `profile`, 0 posts, snapshot subscribers 333880), `test_rename_creates_alias` (title change → alias + event), `test_invite_snapshot` (invite fixture → 29782).
- [ ] Run → FAIL. Implement. Run → PASS.

### Task 5: Rules and daily rollup

**Files:**
- Create: `app/rules.py`, `app/rollup.py`, `tests/test_rules.py`, `tests/test_rollup.py`

**Interfaces:**
- Produces (pure): `local_date_of(iso_utc: str, tz: str) -> str`; `post_qualifies(post: dict, local_date: str, settings) -> tuple[bool, str]` (reason ∈ `ok|legacy_match|no_tag|no_media_or_link|sticker`); `evaluate_contract_day(contract: dict, channel_days: list[ChannelDay], now_local: datetime, settings) -> Verdict(status, required, qualified, pin_ok, notes)` where `ChannelDay(channel_key, kind, collector, readable: bool, qualified: int, posts_total: int, pinned_today: bool | None, dead: bool, renamed: bool)`; status rules as SPEC §6 with precedence `paused > dead > manual(custom quota) > unverifiable > ok > pin_missing > invalid > waiting(before 23:59 local) > missed`.
- `rollup_date(conn, local_date: str, settings, now=None) -> int` writes `daily_rollup` rows for every active contract.

- [ ] Write tests: `test_local_date_yangon_boundary` (`2026-10-25T17:29:00+00:00` → `2026-10-25`; `2026-10-25T17:31:00+00:00` → `2026-10-26`), `test_post_qualifies_tag_and_media`, `test_legacy_platinum_before_enforcement`, `test_sticker_never_qualifies`, `test_private_without_mtproto_is_unverifiable`, `test_waiting_before_cutoff_missed_after`, `test_all_channels_must_meet_quota`, `test_custom_quota_is_manual`, `test_rollup_writes_rows` (DB with imported small seed + 2 posts).
- [ ] Run → FAIL. Implement. Run → PASS.

### Task 6: Scheduler, alerts, main

**Files:**
- Create: `app/scheduler.py`, `app/alerts.py`, `app/main.py`, `tests/test_alerts.py`

**Interfaces:**
- `build_summary(conn, local_date) -> Summary(total, ok, waiting, missed, unverifiable, invalid, pin_missing, dead, posts)`; `format_alert(summary, local_date, kind) -> str` Thai text; `async send_alert(settings, text, client)` → Bot API `sendMessage`; `maybe_send(conn, settings, local_date, kind)` idempotent via `alerts` table.
- Scheduler jobs (Asia/Yangon): collector every `collector_interval_min` minutes; rollup every 15 min for today; alert `warn` at 18:00, `summary` at 23:50; MTProto collector every 30 min offset by 10 when enabled.
- `app/main.py`: FastAPI app from `app.web.create_app(settings)`; on startup `migrate` + start scheduler; `/healthz`.

- [ ] Tests: `test_format_alert_thai_contains_counts`, `test_maybe_send_once` (fake sender called once for same date+kind).
- [ ] Run → FAIL. Implement. Run → PASS.

### Task 7: Web dashboard (Thai)

**Files:**
- Create: `app/web.py`, `app/templates/base.html`, `index.html`, `contract.html`, `app/static/style.css`, `tests/test_web.py`

**Interfaces:**
- Routes: `GET /` (today by default, `?date=YYYY-MM-DD`, `?status=`), `GET /contracts/{id}`, `GET /api/summary?date=`, `GET /api/contracts?date=`, `GET /export.csv?from=&to=`, `POST /admin/import` (multipart `seed`, optional `probe`), `POST /admin/run/{collector|rollup|mtproto}`, `GET /healthz`. HTTP Basic auth on everything except `/healthz` when `dash_password` is set.
- Dashboard: KPI row (ครบ / รอ / ขาด / ตรวจไม่ได้ / ไม่ผ่านเงื่อนไข / โพสต์วันนี้), exception-first table sorted missed → invalid → unverifiable → waiting → ok, columns per SPEC §7, evidence links.

- [ ] Tests with `fastapi.testclient`: `test_dashboard_renders_empty_db` (200, contains "ยังไม่มีข้อมูล"), `test_basic_auth_required_when_password_set` (401 without creds), `test_import_endpoint` (post small seed → 200, counts), `test_export_csv_header`.
- [ ] Run → FAIL. Implement. Run → PASS.

### Task 8: MTProto collector (optional path) + login helper

**Files:**
- Create: `app/mtproto.py`, `tools/tg_login.py`, `tests/test_mtproto.py`

**Interfaces:**
- `message_to_post(msg) -> dict` (duck-typed Telethon message: `id`, `date`, `message`, `entities`, `photo`, `video`, `document`, `sticker`, `pinned`, `views`) producing the same post dict shape as `tgweb.parse_post` with `source='mtproto'` and `is_pinned` set; `async run_mtproto_collector(conn, settings, client_factory=None)`: for channels with collector in (`invite`,`profile`) → ensure joined (≤3 joins/run), `iter_messages(min_id=last_message_id, limit=200)`, upsert posts, `pin_snapshots` from `get_messages(filter=InputMessagesFilterPinned)`, participants snapshot. FloodWait ≤120 s sleep else skip channel.
- `tools/tg_login.py`: interactive local script → prints a StringSession to paste into Coolify env `TG_SESSION` (never written to disk).

- [ ] Tests: `test_message_to_post_photo_with_tag`, `test_message_to_post_sticker_not_media`, `test_pinned_flag`.
- [ ] Run → FAIL. Implement. Run → PASS.

### Task 9: Deploy to Coolify

**Files:**
- Create: `deploy/coolify_create_app.sh` (API: create app from public repo with Dockerfile build pack, set env vars, persistent storage `/data`, deploy), `deploy/README.md` (Thai: GitHub repo, DNS `audit.jbacteam.com` → 210.246.215.196 or Cloudflare proxied, env list, first import, Telethon login)
- Modify: `README.md`, `docs/SPEC.md` §4/§11 (hosting note → ADR-002)

- [ ] Local smoke: `.venv/Scripts/python -m app.importer data/channels.seed.json data/probe_report.json` then `uvicorn app.main:app --port 8010` → `GET /healthz` 200, `GET /` 200 (basic auth).
- [ ] Coolify: run `deploy/coolify_create_app.sh` once the repo URL exists (blocked on the user pushing the repo; everything else done) → `GET https://<fqdn>/healthz` 200.
