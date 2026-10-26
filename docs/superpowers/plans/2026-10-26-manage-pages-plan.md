# Manage pages + Payment Recon theme — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use `- [ ]` checkboxes.

**Goal:** Give the audit service a Payment-Recon-styled shell and server-rendered management pages for every sheet in the Excel file.

**Architecture:** Same FastAPI + Jinja + SQLite app. New module `app/manage.py` holds the HTML management routes (APIRouter),
`app/links.py` the t.me URL classifier, `app/forms.py` CSRF/flash helpers. Templates under `app/templates/manage/`.
Migration `0002_manage.sql` adds lock/note columns and `admin_log`.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLite, python-multipart (already pinned). No JS framework; ~40 lines of vanilla JS for theme toggle + sidebar drawer.

**Spec:** docs/superpowers/specs/2026-10-26-manage-pages-design.md

## Global Constraints
- Tokens/fonts copied from Payment Recon (see spec §เป้าหมาย 1); light default; `data-theme` + `localStorage.adm_theme`.
- Every user-facing string goes through `t()` in th/en/my; `tests/test_ui.py` RAW_KEY check must cover every new page.
- Manual edits set `manual_locked=1`; `import_seed` must leave locked contracts/channels untouched (still attaches channels).
- All HTML POSTs: CSRF double-submit (`csrf` cookie == form field) and `Origin` host check; JSON `/admin/*` POSTs get the Origin check.
- Tests: `.venv\Scripts\python -I -m unittest discover -s tests -t .` stays green after every task.

## Review Focus
1. Import after manual edit: locked contract keeps its fee/quota; unlocked one updates (test in test_importer).
2. Cross-site form POST with foreign `Origin` → 403; same-origin form without csrf → 403 (test_manage).
3. Adding a channel by an invite link that already exists attaches the existing row instead of duplicating (test_manage).
4. Reg grid save with blank cells deletes nothing and does not insert zeros (test_manage).
5. Monthly grid for a month with no rollups renders without error and marks cells as "not computed" (test_manage).

---

### Task 1: Theme shell + dashboard KPI tiles
Files: Modify `app/templates/base.html`, `index.html`, `contract.html`; `app/web.py` (`/logout`, `nav` context); `app/i18n.py` (nav keys). Test: `tests/test_shell.py`.
- [ ] test: shell renders sidebar nav with `data-nav="dashboard"` active, `<html data-theme>` attr absent (JS sets), topbar has lang switch; `/logout` → 401 with `WWW-Authenticate`.
- [ ] implement; run suite; commit.

### Task 2: Migration 0002 + lock-aware importer + forms helpers
Files: `app/migrations/0002_manage.sql`, `app/importer.py`, `app/forms.py` (`new_csrf`, `check_csrf`, `set_flash`, `pop_flash`, `log_admin`). Tests: `tests/test_importer.py` (+2), `tests/test_forms.py`.
- [ ] tests first (locked rows untouched; csrf compare; flash roundtrip; admin_log row).
- [ ] implement; suite; commit.

### Task 3: `app/links.py` + contracts manage pages
Files: `app/links.py` (`classify_url(url) -> dict`, `channel_key_for(info)`), `app/manage.py` (router: list/new/edit/save/attach/detach), templates `manage/contracts.html`, `manage/contract_form.html`. Tests: `tests/test_links.py`, `tests/test_manage.py`.
- [ ] tests: classify 6 URL shapes; create contract via form → row with `manual_locked=1`, id `2026-10-m001`; edit updates; attach by URL creates/links channel; attach existing invite link reuses row; detach.
- [ ] implement; suite; commit.

### Task 4: Channels manage pages
Templates `manage/channels.html`, `manage/channel_form.html`; routes list/new/edit/save/revive. Tests in test_manage.
- [ ] tests: list filters dead; revive clears dead_at/misses + admin_log; edit URL change writes alias and new key.
- [ ] implement; suite; commit.

### Task 5: Reg grid
Template `manage/regs.html`; routes GET/POST `/manage/regs`. Tests: save upserts only filled cells; months param.
- [ ] tests; implement; suite; commit.

### Task 6: Lists (stop/refund/follow_up/substitute)
Template `manage/lists.html`; routes list/add/delete. Tests: add stop → contract status stopped + event; delete event; refund amount stored.
- [ ] tests; implement; suite; commit.

### Task 7: Monthly report
Template `reports/month.html`; route `/reports/month?month=`. Helper `month_summary(conn, month)`, `month_grid(conn, month)`. Tests: summary numbers from seed; grid cell statuses; empty month.
- [ ] tests; implement; suite; commit.

### Task 8: Data (import/export) + Settings/status pages
Templates `manage/data.html`, `manage/settings.html`; routes. Tests: import form → flash with counts; settings masks password; run buttons need csrf.
- [ ] tests; implement; suite; commit.

### Task 9: i18n sweep, screenshots, deploy, docs
- [ ] extend RAW_KEY test to all new pages ×3 langs; screenshots 1366/390/dark; deploy; README/SPEC §10b/deploy README; memory.
