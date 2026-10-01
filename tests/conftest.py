"""
Shared fixtures for the MaintDB test suite.

All test data uses the prefix/code  Z999  (assets) or  TEST_  (ERP records)
so it is instantly recognisable and never collides with real production data.
Every fixture cleans up after itself unconditionally.
"""
import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
DB_DIR    = BASE_DIR / "Maintenance_DB"

# ── Test-data identifiers ──────────────────────────────────────────────────────
TEST_ASSET_CODE = "Z999"
TEST_ASSET_ID   = "A-Z999"
TEST_ASSET_FOLDER = DB_DIR / "A-Z999-TEST"

TEST_WC_ID   = "TEST_WC_Z1"
TEST_EMP_ID  = "TEST_EMP_Z1"
TEST_JOB_NO  = "TEST_J_Z1"


# ── Engine ─────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def engine():  # noqa: F811 (shadows outer scope intentionally)
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db   = os.getenv("PG_DB",   "maintdb")
    user = os.getenv("PG_USER", os.getenv("USER", "postgres"))
    pwd  = os.getenv("PG_PASS", "")
    eng  = create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")
    yield eng
    eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def sync_sequences(engine):
    """
    Sync all SERIAL sequences to the current table max before any tests run.
    Prevents duplicate-key errors when seed data was imported manually
    without advancing the sequence.
    """
    with engine.connect() as conn:
        conn.execute(text(
            "SELECT setval('labor_tickets_ticket_id_seq', "
            "GREATEST((SELECT COALESCE(MAX(ticket_id), 0) FROM labor_tickets), 1))"
        ))
        conn.execute(text(
            "SELECT setval('asset_batteries_id_seq', "
            "GREATEST((SELECT COALESCE(MAX(id), 0) FROM asset_batteries), 1))"
        ))
        conn.execute(text(
            "SELECT setval('asset_peripheral_equipment_id_seq', "
            "GREATEST((SELECT COALESCE(MAX(id), 0) FROM asset_peripheral_equipment), 1))"
        ))
        conn.execute(text(
            "SELECT setval('service_reports_report_id_seq', "
            "GREATEST((SELECT COALESCE(MAX(report_id), 0) FROM service_reports), 1))"
        ))
        conn.commit()


# ── Helpers ────────────────────────────────────────────────────────────────────
def _delete_test_asset(conn, asset_id=TEST_ASSET_ID, asset_code=TEST_ASSET_CODE):
    # service_parts cascade off service_reports; delete issues/documents explicitly
    # (machine_issues.asset_id is ON DELETE SET NULL, so it would otherwise linger).
    conn.execute(text("DELETE FROM machine_issues            WHERE asset_code = :code OR asset_id = :id"),
                 {"code": asset_code, "id": asset_id})
    conn.execute(text("DELETE FROM documents                 WHERE asset_id = :id"), {"id": asset_id})
    conn.execute(text("DELETE FROM service_reports           WHERE asset_id = :id OR asset_code = :code"),
                 {"id": asset_id, "code": asset_code})
    conn.execute(text("DELETE FROM asset_peripheral_equipment WHERE asset_id = :id"), {"id": asset_id})
    conn.execute(text("DELETE FROM asset_batteries            WHERE asset_id = :id"), {"id": asset_id})
    conn.execute(text("DELETE FROM assets                     WHERE asset_id = :id"), {"id": asset_id})


def _delete_test_erp(conn):
    conn.execute(text("DELETE FROM labor_tickets WHERE employee_id = :e OR machine_id = :m OR job_no = :j"),
                 {"e": TEST_EMP_ID, "m": TEST_WC_ID, "j": TEST_JOB_NO})
    conn.execute(text("DELETE FROM jobs         WHERE job_no      = :j"), {"j": TEST_JOB_NO})
    conn.execute(text("DELETE FROM employees    WHERE employee_id = :e"), {"e": TEST_EMP_ID})
    conn.execute(text("DELETE FROM work_centers WHERE machine_id  = :m"), {"m": TEST_WC_ID})


# ── Base test asset (used by service-report & edit-asset tests) ────────────────
@pytest.fixture
def test_asset(engine):
    """
    Inserts a minimal Z999 asset row and its folder, then tears down.
    Yields the asset_id string 'A-Z999'.
    """
    TEST_ASSET_FOLDER.mkdir(parents=True, exist_ok=True)

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO assets (
                asset_id, asset_code, department_code, sequence_number,
                display_name, short_name, equipment_category,
                manufacturer, model, serial_number, control_type, build_year,
                distributor, distributor_email, distributor_phone, vendor_contacts,
                template_version, registry_creation_date, folder_path
            ) VALUES (
                :aid, :code, 'Z', '999',
                'Z999-TEST', 'Z999-TEST', 'Other',
                'TestMfr', 'TestModel', 'SN-TEST-001', 'TestControl', 2024,
                'TestDist', 'test@example.com', '555-0000', 'Test vendor',
                '1.0', NOW(), :fp
            )
        """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE, "fp": str(TEST_ASSET_FOLDER)})
        conn.commit()

    yield TEST_ASSET_ID

    with engine.connect() as conn:
        _delete_test_asset(conn)
        conn.commit()

    if TEST_ASSET_FOLDER.exists():
        shutil.rmtree(TEST_ASSET_FOLDER)


# ── Minimal ERP fixtures ───────────────────────────────────────────────────────
@pytest.fixture
def test_work_center(engine):
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO work_centers (machine_id, machine_name, department) "
            "VALUES (:id, 'Test Machine Z1', 'Support')"
        ), {"id": TEST_WC_ID})
        conn.commit()

    yield TEST_WC_ID

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM labor_tickets WHERE machine_id = :id"), {"id": TEST_WC_ID})
        conn.execute(text("DELETE FROM work_centers  WHERE machine_id = :id"), {"id": TEST_WC_ID})
        conn.commit()


@pytest.fixture
def test_employee(engine):
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO employees (employee_id, name, role) VALUES (:id, 'Test Employee Z1', 'Operator')"
        ), {"id": TEST_EMP_ID})
        conn.commit()

    yield TEST_EMP_ID

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM labor_tickets WHERE employee_id = :id"), {"id": TEST_EMP_ID})
        conn.execute(text("DELETE FROM employees    WHERE employee_id = :id"), {"id": TEST_EMP_ID})
        conn.commit()


@pytest.fixture
def test_job(engine):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO jobs (job_no, part_no, customer, order_qty, due_date,
                              est_setup_hours, est_run_hours, status)
            VALUES (:j, 'P-TEST-Z1', 'TestCo', 10, '2026-12-31', 1.5, 3.0, 'Active')
        """), {"j": TEST_JOB_NO})
        conn.commit()

    yield TEST_JOB_NO

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM labor_tickets WHERE job_no = :j"), {"j": TEST_JOB_NO})
        conn.execute(text("DELETE FROM jobs          WHERE job_no = :j"), {"j": TEST_JOB_NO})
        conn.commit()
