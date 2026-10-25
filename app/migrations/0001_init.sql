-- Platinum Club MM audit — schema v2 (docs/SPEC.md §5, hosting per ADR-002). Times are ISO-8601 UTC strings;
-- local_date is the Asia/Yangon calendar day.

CREATE TABLE IF NOT EXISTS contracts (
  id                  INTEGER PRIMARY KEY,
  sheet_contract_id   TEXT UNIQUE NOT NULL,          -- '2026-10-r005' from channels.seed.json
  month               TEXT NOT NULL,                 -- '2026-10'
  section             TEXT,                          -- only_us | only_two | only_three | only_four | influencer | unknown
  exclusivity         INTEGER,                       -- 1..5 advertisers in the channel
  quota_type          TEXT NOT NULL DEFAULT 'unknown', -- daily_post | custom | unknown
  quota_posts_per_day INTEGER,
  pin_rule            TEXT NOT NULL DEFAULT 'none',  -- daily | per_month:N | every_days:N | none
  amount_mmk          INTEGER,
  period_from         TEXT,
  period_to           TEXT,
  names               TEXT,                          -- JSON array of channel names as typed in the sheet
  admin_accounts      TEXT,                          -- JSON array of @handles
  remark_raw          TEXT,
  status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','stopped','refund')),
  created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00','now')),
  updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS channels (
  id              INTEGER PRIMARY KEY,
  channel_key     TEXT UNIQUE NOT NULL,              -- 'pub:<username>' | 'prv:<invite_hash>'
  kind            TEXT NOT NULL CHECK (kind IN ('public_preview','public_no_preview','private','group','not_channel','unknown')),
  username        TEXT,
  invite_hash     TEXT,
  tg_peer_id      INTEGER,
  title           TEXT,                              -- name as typed in the sheet
  title_observed  TEXT,                              -- latest title seen on Telegram (rename detection compares this)
  subscribers     INTEGER,
  collector       TEXT NOT NULL CHECK (collector IN ('preview','profile','invite','mtproto','none')),
  joined          INTEGER NOT NULL DEFAULT 0,        -- MTProto account can read the history (member, or public)
  join_requested_at TEXT,                            -- invite needed admin approval / failed; retry after 7 days
  dead_misses     INTEGER NOT NULL DEFAULT 0,        -- consecutive runs where the page showed no channel
  dead_at         TEXT,                              -- set after 3 consecutive misses
  last_message_id INTEGER,
  last_checked    TEXT,
  last_error      TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00','now')),
  updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS contract_channels (
  contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  position    INTEGER,
  PRIMARY KEY (contract_id, channel_id)
);

CREATE TABLE IF NOT EXISTS channel_aliases (
  id              INTEGER PRIMARY KEY,
  channel_id      INTEGER REFERENCES channels(id) ON DELETE CASCADE,
  contract_id     INTEGER REFERENCES contracts(id) ON DELETE SET NULL,
  old_title       TEXT,
  old_url         TEXT,
  old_channel_key TEXT,
  seen_at         TEXT NOT NULL,
  source          TEXT                                -- sheet | collector
);

CREATE TABLE IF NOT EXISTS posts (
  id              INTEGER PRIMARY KEY,
  channel_id      INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  message_id      INTEGER NOT NULL,
  posted_at       TEXT NOT NULL,
  local_date      TEXT NOT NULL,
  has_tag         INTEGER NOT NULL DEFAULT 0,
  has_media       INTEGER NOT NULL DEFAULT 0,
  has_link        INTEGER NOT NULL DEFAULT 0,
  has_sticker     INTEGER NOT NULL DEFAULT 0,
  legacy_match    INTEGER NOT NULL DEFAULT 0,        -- 'platinum' in text before hashtag enforcement
  is_pinned       INTEGER,                           -- NULL when the source cannot know (preview)
  text_preview    TEXT,
  permalink       TEXT,
  views           INTEGER,
  source          TEXT NOT NULL CHECK (source IN ('preview','mtproto')),
  qualifies       INTEGER NOT NULL DEFAULT 0,
  qualify_reason  TEXT,
  first_seen      TEXT NOT NULL,
  last_seen       TEXT,
  deleted_seen_at TEXT,
  UNIQUE (channel_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_channel_date ON posts(channel_id, local_date);
CREATE INDEX IF NOT EXISTS idx_posts_local_date ON posts(local_date);

CREATE TABLE IF NOT EXISTS pin_snapshots (
  id                 INTEGER PRIMARY KEY,
  channel_id         INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  captured_at        TEXT NOT NULL,
  local_date         TEXT NOT NULL,
  pinned_message_ids TEXT NOT NULL                   -- JSON array
);
CREATE INDEX IF NOT EXISTS idx_pins_channel_date ON pin_snapshots(channel_id, local_date);

CREATE TABLE IF NOT EXISTS snapshots (
  id          INTEGER PRIMARY KEY,
  channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  captured_at TEXT NOT NULL,
  subscribers INTEGER,
  title       TEXT,
  source      TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_channel ON snapshots(channel_id, captured_at);

CREATE TABLE IF NOT EXISTS post_view_snapshots (
  id          INTEGER PRIMARY KEY,
  post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  captured_at TEXT NOT NULL,
  views       INTEGER
);

CREATE TABLE IF NOT EXISTS daily_rollup (
  id          INTEGER PRIMARY KEY,
  local_date  TEXT NOT NULL,
  contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  required    INTEGER,
  qualified   INTEGER,
  pin_ok      INTEGER,                               -- NULL = not checkable
  status      TEXT NOT NULL,                         -- ok|waiting|missed|invalid|pin_missing|unverifiable|dead|renamed|paused|manual
  notes       TEXT,                                  -- JSON: per-channel detail
  computed_at TEXT NOT NULL,
  UNIQUE (local_date, contract_id)
);

CREATE TABLE IF NOT EXISTS reg_monthly (
  contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  month       TEXT NOT NULL,
  reg         INTEGER NOT NULL,
  PRIMARY KEY (contract_id, month)
);

CREATE TABLE IF NOT EXISTS price_history (
  id          INTEGER PRIMARY KEY,
  contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  month       TEXT,
  amount_mmk  INTEGER,
  note        TEXT,
  UNIQUE (contract_id, month, note)
);

CREATE TABLE IF NOT EXISTS channel_events (
  id          INTEGER PRIMARY KEY,
  channel_id  INTEGER REFERENCES channels(id) ON DELETE CASCADE,
  contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL,
  event       TEXT NOT NULL,                         -- renamed | dead | stop | refund | follow_up | substitute | joined | error
  happened_at TEXT NOT NULL,
  amount_mmk  INTEGER,
  note        TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
  id         INTEGER PRIMARY KEY,
  local_date TEXT NOT NULL,
  kind       TEXT NOT NULL,                          -- warn | summary
  sent_at    TEXT NOT NULL,
  text       TEXT,
  UNIQUE (local_date, kind)
);

CREATE TABLE IF NOT EXISTS runs (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL,                         -- collector | mtproto | rollup | alert | import
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  ok          INTEGER,
  detail      TEXT
);
