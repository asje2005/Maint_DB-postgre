-- Upgrade an EXISTING live database in place (without wiping data).
--
-- Everything here is also baked into schema.sql, so a fresh install needs only
-- schema.sql (or, in Docker, maintdb_dump.sql + service_reports_schema.sql).
-- This file matters only for an older database created before these changes.
-- Apply to an existing DB with: psql -d maintdb -f schema_fixes.sql

-- 1. Make assets.asset_code's index UNIQUE (originally found 2026-06-18).
--    schema.sql already creates it UNIQUE; this DROP/recreate is a harmless
--    no-op on a fresh DB and only fixes an older index created without UNIQUE.
--    No data migration needed — no duplicates existed at time of discovery.
DROP INDEX IF EXISTS idx_assets_asset_code;
CREATE UNIQUE INDEX idx_assets_asset_code ON assets(asset_code);

-- 2. Enforce at most one OPEN draft per asset at the database level.
--    schema.sql already creates this index; the IF NOT EXISTS makes it a no-op
--    on a fresh DB. The app pre-checks this, but two rapid clicks could race past
--    the check; this partial unique index makes a second open draft impossible.
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_draft_per_asset
    ON service_reports(asset_code) WHERE record_state = 'Draft';

-- 3. Service-report issue/cause fields and the parts table (added 2026-06-19).
--    Adds the issue_category / root_cause columns and the service_parts child
--    table to an existing database. No-ops if they already exist.
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS issue_category TEXT;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS root_cause     TEXT;

CREATE TABLE IF NOT EXISTS service_parts (
    id         SERIAL PRIMARY KEY,
    report_id  INTEGER NOT NULL REFERENCES service_reports(report_id) ON DELETE CASCADE,
    part_name  TEXT NOT NULL,
    quantity   INTEGER NOT NULL DEFAULT 1,
    is_battery BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_service_parts_report_id ON service_parts(report_id);

-- 4. Streamline release — identity, PM scheduling, cost, docs, issues (added 2026-06-20).
--    All additive and idempotent; safe to re-run. The app also applies this file
--    automatically on first boot (utils.db.ensure_schema), so a native-run user
--    never needs to invoke psql by hand.

-- shop_config: small key/value store for editable settings (cost rates, PM threshold).
CREATE TABLE IF NOT EXISTS shop_config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO shop_config (key, value) VALUES
    ('labor_rate_per_hour',    '75.00'),
    ('downtime_rate_per_hour', '250.00'),
    ('pm_due_soon_days',       '14')
ON CONFLICT (key) DO NOTHING;

-- documents: pointers (relative paths) to the per-asset files already on disk
-- under Maintenance_DB/<folder>. Files are NOT copied into the DB.
CREATE TABLE IF NOT EXISTS documents (
    id        SERIAL PRIMARY KEY,
    asset_id  TEXT REFERENCES assets(asset_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    rel_path  TEXT NOT NULL,            -- relative to the Maintenance_DB/ root
    doc_type  TEXT,                     -- PM / Manual / Registry / Other
    added_by  TEXT,
    added_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (asset_id, rel_path)
);
CREATE INDEX IF NOT EXISTS idx_documents_asset ON documents(asset_id);

-- machine_issues: lightweight "noticed a problem" inbox; an issue can be promoted
-- into a service_reports draft (promoted_report_id links the two).
CREATE TABLE IF NOT EXISTS machine_issues (
    id                 SERIAL PRIMARY KEY,
    asset_code         TEXT,
    asset_id           TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
    note               TEXT NOT NULL,
    priority           TEXT DEFAULT 'Normal',   -- Low / Normal / High
    status             TEXT DEFAULT 'Open',     -- Open / Promoted / Closed
    created_by         TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    promoted_report_id INTEGER REFERENCES service_reports(report_id) ON DELETE SET NULL,
    closed_at          TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_issues_status ON machine_issues(status);

-- Cost tracking + identity stamp on service events.
ALTER TABLE service_parts   ADD COLUMN IF NOT EXISTS unit_cost  NUMERIC(10, 2);
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS event_cost NUMERIC(12, 2);
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS created_by TEXT;

-- Speeds the PM "last preventive finalize" lookup and reliability aggregates.
CREATE INDEX IF NOT EXISTS idx_sr_type_state_final
    ON service_reports(asset_id, service_type, record_state, finalized_at);

-- 5. JobBoss / ECI M1 sync (added 2026-06-20).
--    Origin key so labor tickets pulled FROM JobBoss can be upserted idempotently
--    (a re-sync updates the same row instead of inserting a duplicate). Locally
--    created/seeded tickets keep it NULL. Additive + idempotent; the app applies
--    it automatically on first boot via utils.db.ensure_schema.
ALTER TABLE labor_tickets ADD COLUMN IF NOT EXISTS jobboss_ticket_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_labor_jobboss_ticket
    ON labor_tickets(jobboss_ticket_id) WHERE jobboss_ticket_id IS NOT NULL;

-- A database restored straight from the seed dump can leave the labor PK sequence
-- behind the seeded max (the dump resets it to 1), so the next generated ticket_id
-- would collide with an existing row — e.g. the first JobBoss-synced labor ticket.
-- Advance it past the current max on every boot; idempotent and self-correcting.
SELECT setval(pg_get_serial_sequence('labor_tickets', 'ticket_id'),
              GREATEST((SELECT COALESCE(MAX(ticket_id), 0) FROM labor_tickets), 1));
