-- Management pages: rows edited by hand are locked against the sheet importer; every change is logged.
ALTER TABLE contracts ADD COLUMN manual_locked INTEGER NOT NULL DEFAULT 0;
ALTER TABLE contracts ADD COLUMN note TEXT;
ALTER TABLE channels ADD COLUMN manual_locked INTEGER NOT NULL DEFAULT 0;
ALTER TABLE channels ADD COLUMN note TEXT;

CREATE TABLE IF NOT EXISTS admin_log (
  id     INTEGER PRIMARY KEY,
  at     TEXT NOT NULL,
  user   TEXT,
  action TEXT NOT NULL,                              -- contract.create | contract.update | channel.create | ... (see app/manage.py)
  target TEXT,                                       -- sheet_contract_id / channel_key / month
  detail TEXT                                        -- JSON
);
CREATE INDEX IF NOT EXISTS idx_admin_log_at ON admin_log(at);
