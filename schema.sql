-- Manufacturing Operation Database — PostgreSQL Schema
-- Run this once against an empty database:
--   psql -d maintdb -f schema.sql

-- ============================================================
-- SHOP FLOOR / ERP
-- ============================================================

CREATE TABLE work_centers (
    machine_id   TEXT PRIMARY KEY,
    machine_name TEXT NOT NULL,
    department   TEXT NOT NULL
);

CREATE TABLE employees (
    employee_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    role        TEXT
);

CREATE TABLE jobs (
    job_no          TEXT PRIMARY KEY,
    part_no         TEXT,
    customer        TEXT,
    order_qty       INTEGER,
    due_date        DATE,
    est_setup_hours NUMERIC(6, 2),
    est_run_hours   NUMERIC(6, 2),
    status          TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status);

CREATE TABLE labor_tickets (
    ticket_id   SERIAL PRIMARY KEY,
    employee_id TEXT        REFERENCES employees(employee_id),
    job_no      TEXT        REFERENCES jobs(job_no),
    machine_id  TEXT        REFERENCES work_centers(machine_id),
    op_code     TEXT,
    op_desc     TEXT,
    time_in     TIMESTAMPTZ,
    time_out    TIMESTAMPTZ,
    setup_hours NUMERIC(6, 2),
    run_hours   NUMERIC(6, 2),
    qty_good    INTEGER,
    qty_scrap   INTEGER,
    jobboss_ticket_id TEXT          -- origin id when synced from JobBoss (NULL for local rows)
);

CREATE INDEX idx_labor_tickets_job_no      ON labor_tickets(job_no);
CREATE UNIQUE INDEX uq_labor_jobboss_ticket
    ON labor_tickets(jobboss_ticket_id) WHERE jobboss_ticket_id IS NOT NULL;
CREATE INDEX idx_labor_tickets_employee_id ON labor_tickets(employee_id);
CREATE INDEX idx_labor_tickets_machine_id  ON labor_tickets(machine_id);
CREATE INDEX idx_labor_tickets_time_in     ON labor_tickets(time_in);
CREATE INDEX idx_lt_op_code                ON labor_tickets(op_code);
CREATE INDEX idx_lt_op_machine             ON labor_tickets(op_code, machine_id);
CREATE INDEX idx_lt_active                 ON labor_tickets(time_in) WHERE time_out IS NULL;


-- ============================================================
-- MAINTENANCE / ASSET REGISTRY
-- ============================================================

CREATE TABLE assets (
    asset_id                 TEXT PRIMARY KEY,  -- e.g. A-L001
    asset_code               TEXT NOT NULL,     -- e.g. L001  (matches work_centers.machine_id)
    department_code          CHAR(1),           -- L M S Q E
    sequence_number          TEXT,
    display_name             TEXT,
    short_name               TEXT,
    equipment_category       TEXT,              -- Lathe / Mill / Swiss / QC / Support
    primary_function         TEXT,              -- Machining / Inspection / Handling / Utility
    manufacturer             TEXT,
    model                    TEXT,
    serial_number            TEXT,
    control_type             TEXT,
    build_year               INTEGER,
    distributor              TEXT,
    distributor_email        TEXT,
    distributor_phone        TEXT,
    vendor_contacts          TEXT,
    facility                 TEXT,
    area_cell                TEXT,
    commission_date          DATE,
    asset_status             TEXT,
    planned_pm_interval_days INTEGER,
    installation_notes       TEXT,
    known_quirks             TEXT,
    special_tooling          TEXT,
    reference_document       TEXT,
    template_version         TEXT,
    registry_created_by      TEXT,
    registry_creation_date   TIMESTAMPTZ,
    final_lock_date          DATE,
    approved_by              TEXT,
    folder_path              TEXT
);

-- asset_code links back to work_centers where relevant
CREATE UNIQUE INDEX idx_assets_asset_code      ON assets(asset_code);
CREATE INDEX idx_assets_equipment_category     ON assets(equipment_category);
CREATE INDEX idx_assets_asset_status           ON assets(asset_status);
CREATE INDEX idx_assets_dept_code              ON assets(department_code);

CREATE TABLE asset_batteries (
    id                       SERIAL PRIMARY KEY,
    asset_id                 TEXT        NOT NULL REFERENCES assets(asset_id),
    battery_number           INTEGER     NOT NULL,  -- 1, 2, 3
    description              TEXT,
    part_number              TEXT,
    replacement_interval_days INTEGER
);

CREATE INDEX idx_asset_batteries_asset_battery ON asset_batteries(asset_id, battery_number);

CREATE TABLE asset_peripheral_equipment (
    id             SERIAL PRIMARY KEY,
    asset_id       TEXT    NOT NULL REFERENCES assets(asset_id),
    equip_number   INTEGER NOT NULL,  -- 1, 2, 3
    name           TEXT,
    make           TEXT,
    model          TEXT,
    serial_number  TEXT
);

CREATE INDEX idx_asset_pe_asset_equip ON asset_peripheral_equipment(asset_id, equip_number);


-- ============================================================
-- SERVICE REPORTS
-- ============================================================

CREATE TABLE service_reports (
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

CREATE INDEX idx_sr_asset_id     ON service_reports(asset_id);
CREATE INDEX idx_sr_record_state ON service_reports(record_state);
CREATE INDEX idx_sr_asset_state  ON service_reports(asset_id, record_state);

-- At most one open draft per asset
CREATE UNIQUE INDEX uq_one_open_draft_per_asset
    ON service_reports(asset_code) WHERE record_state = 'Draft';

-- Parts replaced or installed during a service event (one row per part)
CREATE TABLE service_parts (
    id         SERIAL PRIMARY KEY,
    report_id  INTEGER NOT NULL REFERENCES service_reports(report_id) ON DELETE CASCADE,
    part_name  TEXT NOT NULL,
    quantity   INTEGER NOT NULL DEFAULT 1,
    is_battery BOOLEAN NOT NULL DEFAULT FALSE  -- true when the part is a battery replacement
);

CREATE INDEX idx_service_parts_report_id ON service_parts(report_id);


-- ============================================================
-- SETTINGS / DOCUMENTS / ISSUES / COST  (Streamline release)
-- ============================================================

-- Editable settings (cost rates, PM due-soon threshold), one row per key.
CREATE TABLE shop_config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO shop_config (key, value) VALUES
    ('labor_rate_per_hour',    '75.00'),
    ('downtime_rate_per_hour', '250.00'),
    ('pm_due_soon_days',       '14');

-- Pointers to per-asset files on disk under Maintenance_DB/<folder> (not stored in DB).
CREATE TABLE documents (
    id        SERIAL PRIMARY KEY,
    asset_id  TEXT REFERENCES assets(asset_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    rel_path  TEXT NOT NULL,            -- relative to the Maintenance_DB/ root
    doc_type  TEXT,                     -- PM / Manual / Registry / Other
    added_by  TEXT,
    added_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (asset_id, rel_path)
);
CREATE INDEX idx_documents_asset ON documents(asset_id);

-- Lightweight "noticed a problem" inbox; promotable into a service_reports draft.
CREATE TABLE machine_issues (
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
CREATE INDEX idx_issues_status ON machine_issues(status);

-- Cost tracking + identity stamp on service events.
ALTER TABLE service_parts   ADD COLUMN unit_cost  NUMERIC(10, 2);
ALTER TABLE service_reports ADD COLUMN event_cost NUMERIC(12, 2);
ALTER TABLE service_reports ADD COLUMN created_by TEXT;

CREATE INDEX idx_sr_type_state_final
    ON service_reports(asset_id, service_type, record_state, finalized_at);
