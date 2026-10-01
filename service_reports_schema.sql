-- Service-report tables for a fresh database.
--
-- maintdb_dump.sql seeds the asset/ERP tables but does NOT contain
-- service_reports or service_parts, so on a brand-new volume those tables would
-- be missing and the app would fail. This file is mounted into the Postgres
-- container after the dump (it sorts after "maintdb_dump.sql") and creates them.
--
-- Everything here is idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS), so it
-- also safely upgrades an older database that predates these tables/columns.

CREATE TABLE IF NOT EXISTS service_reports (
    report_id           SERIAL PRIMARY KEY,
    service_id          TEXT UNIQUE,
    asset_id            TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
    asset_code          TEXT NOT NULL,
    record_state        TEXT NOT NULL DEFAULT 'Draft',  -- Draft / Final
    service_type        TEXT,                           -- Preventive / Corrective / Emergency
    issue_category      TEXT,                           -- Mechanical / Electrical / Pneumatic / Hydraulic / Software / Operator / Process / Other / Unknown
    root_cause          TEXT,                           -- Wear / Misalignment / Contamination / Electrical Fault / Software / Parameters / Installation Error / Damage / Unknown
    problem_description TEXT,
    work_performed      TEXT,
    downtime_hours      NUMERIC(6, 2),
    return_to_service   TEXT,                           -- Yes / No
    verified_by         TEXT,
    entry_timestamp     TIMESTAMPTZ DEFAULT NOW(),
    finalized_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Add the issue/cause columns to an existing service_reports table if it predates them.
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS issue_category TEXT;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS root_cause     TEXT;

CREATE INDEX IF NOT EXISTS idx_sr_asset_id     ON service_reports(asset_id);
CREATE INDEX IF NOT EXISTS idx_sr_record_state ON service_reports(record_state);
CREATE INDEX IF NOT EXISTS idx_sr_asset_state  ON service_reports(asset_id, record_state);

-- At most one open draft per asset
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_draft_per_asset
    ON service_reports(asset_code) WHERE record_state = 'Draft';

-- Parts replaced or installed during a service event (one row per part)
CREATE TABLE IF NOT EXISTS service_parts (
    id         SERIAL PRIMARY KEY,
    report_id  INTEGER NOT NULL REFERENCES service_reports(report_id) ON DELETE CASCADE,
    part_name  TEXT NOT NULL,
    quantity   INTEGER NOT NULL DEFAULT 1,
    is_battery BOOLEAN NOT NULL DEFAULT FALSE  -- true when the part is a battery replacement
);

CREATE INDEX IF NOT EXISTS idx_service_parts_report_id ON service_parts(report_id);
