"""
CRUD integration tests for the Records Manager page tables:
  work_centers · employees · jobs · labor_tickets

Mirrors the _crud_tab / _save_crud logic the app uses via the data_editor widget.
Every test is self-contained and cleans up its own data.
"""
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import text

from tests.conftest import (
    TEST_WC_ID, TEST_EMP_ID, TEST_JOB_NO,
    _delete_test_erp,
)


# ══════════════════════════════════════════════════════════════════════════════
# WORK CENTERS
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkCentersCRUD:
    def test_create_work_center_all_fields(self, engine):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO work_centers (machine_id, machine_name, department) "
                    "VALUES (:id, :name, :dept)"
                ), {"id": TEST_WC_ID, "name": "Test Machine Z1", "dept": "Support"})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT machine_id, machine_name, department FROM work_centers WHERE machine_id = :id"),
                    {"id": TEST_WC_ID}
                ).fetchone()
            assert row is not None
            assert row[0] == TEST_WC_ID
            assert row[1] == "Test Machine Z1"
            assert row[2] == "Support"
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM work_centers WHERE machine_id = :id"), {"id": TEST_WC_ID})
                conn.commit()

    @pytest.mark.parametrize("dept", ["Lathe", "Mill", "Swiss", "QC", "Support"])
    def test_all_departments_accepted(self, engine, dept):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO work_centers (machine_id, machine_name, department) "
                    "VALUES (:id, :name, :dept)"
                ), {"id": TEST_WC_ID, "name": "Dept Test Machine", "dept": dept})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT department FROM work_centers WHERE machine_id = :id"),
                    {"id": TEST_WC_ID}
                ).fetchone()
            assert row[0] == dept
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM work_centers WHERE machine_id = :id"), {"id": TEST_WC_ID})
                conn.commit()

    def test_read_work_centers_query(self, engine, test_work_center):
        """Registry query used by the Records Manager returns the row."""
        df = pd.read_sql_query(
            "SELECT machine_id, machine_name, department FROM work_centers ORDER BY machine_id",
            engine
        )
        assert TEST_WC_ID in df["machine_id"].values

    def test_update_work_center_name_and_department(self, engine, test_work_center):
        with engine.connect() as conn:
            conn.execute(text(
                "UPDATE work_centers SET machine_name = :name, department = :dept "
                "WHERE machine_id = :id"
            ), {"name": "Updated Machine Z1", "dept": "Mill", "id": TEST_WC_ID})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT machine_name, department FROM work_centers WHERE machine_id = :id"),
                {"id": TEST_WC_ID}
            ).fetchone()
        assert row[0] == "Updated Machine Z1"
        assert row[1] == "Mill"

    def test_delete_work_center(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO work_centers (machine_id, machine_name, department) "
                "VALUES (:id, 'Delete Me', 'Support')"
            ), {"id": TEST_WC_ID})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM work_centers WHERE machine_id = :id"), {"id": TEST_WC_ID})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM work_centers WHERE machine_id = :id"), {"id": TEST_WC_ID}
            ).fetchone()
        assert row is None

    def test_duplicate_machine_id_blocked(self, engine, test_work_center):
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO work_centers (machine_id, machine_name, department) "
                    "VALUES (:id, 'Dup', 'Mill')"
                ), {"id": TEST_WC_ID})
                conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# EMPLOYEES
# ══════════════════════════════════════════════════════════════════════════════

class TestEmployeesCRUD:
    def test_create_employee_all_fields(self, engine):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO employees (employee_id, name, role) VALUES (:id, :name, :role)"
                ), {"id": TEST_EMP_ID, "name": "Test Employee Z1", "role": "Operator"})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT employee_id, name, role FROM employees WHERE employee_id = :id"),
                    {"id": TEST_EMP_ID}
                ).fetchone()
            assert row[0] == TEST_EMP_ID
            assert row[1] == "Test Employee Z1"
            assert row[2] == "Operator"
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM employees WHERE employee_id = :id"), {"id": TEST_EMP_ID})
                conn.commit()

    def test_role_field_is_optional(self, engine):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO employees (employee_id, name, role) VALUES (:id, :name, NULL)"
                ), {"id": TEST_EMP_ID, "name": "No Role Employee"})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT role FROM employees WHERE employee_id = :id"),
                    {"id": TEST_EMP_ID}
                ).fetchone()
            assert row[0] is None
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM employees WHERE employee_id = :id"), {"id": TEST_EMP_ID})
                conn.commit()

    def test_read_employees_query(self, engine, test_employee):
        df = pd.read_sql_query(
            "SELECT employee_id, name, role FROM employees ORDER BY employee_id", engine
        )
        assert TEST_EMP_ID in df["employee_id"].values

    def test_update_employee_name_and_role(self, engine, test_employee):
        with engine.connect() as conn:
            conn.execute(text(
                "UPDATE employees SET name = :name, role = :role WHERE employee_id = :id"
            ), {"name": "Updated Employee Z1", "role": "Lead Machinist", "id": TEST_EMP_ID})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, role FROM employees WHERE employee_id = :id"),
                {"id": TEST_EMP_ID}
            ).fetchone()
        assert row[0] == "Updated Employee Z1"
        assert row[1] == "Lead Machinist"

    def test_delete_employee(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO employees (employee_id, name) VALUES (:id, 'Delete Me')"
            ), {"id": TEST_EMP_ID})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM employees WHERE employee_id = :id"), {"id": TEST_EMP_ID})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM employees WHERE employee_id = :id"), {"id": TEST_EMP_ID}
            ).fetchone()
        assert row is None


# ══════════════════════════════════════════════════════════════════════════════
# JOBS
# ══════════════════════════════════════════════════════════════════════════════

class TestJobsCRUD:
    def test_create_job_all_fields(self, engine):
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO jobs (job_no, part_no, customer, order_qty, due_date,
                                     est_setup_hours, est_run_hours, status)
                    VALUES (:j, 'P-TEST-001', 'TestCo', 25, '2026-09-30', 2.0, 8.5, 'Active')
                """), {"j": TEST_JOB_NO})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT * FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO}
                ).mappings().fetchone()

            assert row["part_no"]         == "P-TEST-001"
            assert row["customer"]        == "TestCo"
            assert row["order_qty"]       == 25
            assert row["due_date"]        == date(2026, 9, 30)
            assert float(row["est_setup_hours"]) == 2.0
            assert float(row["est_run_hours"])   == 8.5
            assert row["status"]          == "Active"
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO})
                conn.commit()

    @pytest.mark.parametrize("status", ["Active", "Scheduled", "Completed", "On Hold"])
    def test_all_job_statuses_accepted(self, engine, status):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO jobs (job_no, part_no, customer, status) "
                    "VALUES (:j, 'P-STATUS', 'TestCo', :s)"
                ), {"j": TEST_JOB_NO, "s": status})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT status FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO}
                ).fetchone()
            assert row[0] == status
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO})
                conn.commit()

    def test_read_jobs_query(self, engine, test_job):
        df = pd.read_sql_query("""
            SELECT job_no, part_no, customer, order_qty, due_date,
                   est_setup_hours, est_run_hours, status
            FROM jobs ORDER BY job_no
        """, engine)
        assert TEST_JOB_NO in df["job_no"].values

    def test_update_job_all_fields(self, engine, test_job):
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE jobs SET
                    part_no         = 'P-UPDATED',
                    customer        = 'NewCo',
                    order_qty       = 50,
                    due_date        = '2027-03-15',
                    est_setup_hours = 3.5,
                    est_run_hours   = 12.0,
                    status          = 'Completed'
                WHERE job_no = :j
            """), {"j": test_job})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM jobs WHERE job_no = :j"), {"j": test_job}
            ).mappings().fetchone()

        assert row["part_no"]                  == "P-UPDATED"
        assert row["customer"]                 == "NewCo"
        assert row["order_qty"]                == 50
        assert row["due_date"]                 == date(2027, 3, 15)
        assert float(row["est_setup_hours"])   == 3.5
        assert float(row["est_run_hours"])     == 12.0
        assert row["status"]                   == "Completed"

    def test_delete_job(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO jobs (job_no, customer, status) VALUES (:j, 'Del Co', 'Active')"
            ), {"j": TEST_JOB_NO})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO}
            ).fetchone()
        assert row is None

    def test_optional_job_fields_accept_null(self, engine):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO jobs (job_no, customer, status) "
                    "VALUES (:j, 'Null Test Co', 'Active')"
                ), {"j": TEST_JOB_NO})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT part_no, order_qty, due_date FROM jobs WHERE job_no = :j"),
                    {"j": TEST_JOB_NO}
                ).fetchone()
            assert row[0] is None
            assert row[1] is None
            assert row[2] is None
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM jobs WHERE job_no = :j"), {"j": TEST_JOB_NO})
                conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# LABOR TICKETS (serial PK — pk_is_serial=True in app)
# ══════════════════════════════════════════════════════════════════════════════

class TestLaborTicketsCRUD:
    @pytest.fixture
    def test_ticket(self, engine, test_work_center, test_employee, test_job):
        """Creates a single labor ticket, yields its ticket_id, cleans up."""
        with engine.connect() as conn:
            ticket_id = conn.execute(text("""
                INSERT INTO labor_tickets
                    (employee_id, job_no, machine_id, op_code, op_desc,
                     time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap)
                VALUES
                    (:emp, :job, :wc, '10', 'Test Op',
                     '2026-06-01 08:00:00+00', '2026-06-01 12:00:00+00',
                     0.5, 3.5, 10, 1)
                RETURNING ticket_id
            """), {"emp": TEST_EMP_ID, "job": TEST_JOB_NO, "wc": TEST_WC_ID}).scalar()
            conn.commit()
        yield ticket_id
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM labor_tickets WHERE ticket_id = :id"), {"id": ticket_id})
            conn.commit()

    def test_create_labor_ticket_all_fields(self, engine, test_work_center, test_employee, test_job):
        ticket_id = None
        try:
            with engine.connect() as conn:
                ticket_id = conn.execute(text("""
                    INSERT INTO labor_tickets
                        (employee_id, job_no, machine_id, op_code, op_desc,
                         time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap)
                    VALUES
                        (:emp, :job, :wc, '30', 'Turning Op',
                         '2026-06-10 07:00:00+00', '2026-06-10 15:30:00+00',
                         1.0, 7.5, 20, 2)
                    RETURNING ticket_id
                """), {"emp": TEST_EMP_ID, "job": TEST_JOB_NO, "wc": TEST_WC_ID}).scalar()
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT * FROM labor_tickets WHERE ticket_id = :id"),
                    {"id": ticket_id}
                ).mappings().fetchone()

            assert row["employee_id"]  == TEST_EMP_ID
            assert row["job_no"]       == TEST_JOB_NO
            assert row["machine_id"]   == TEST_WC_ID
            assert row["op_code"]      == "30"
            assert row["op_desc"]      == "Turning Op"
            assert float(row["setup_hours"]) == 1.0
            assert float(row["run_hours"])   == 7.5
            assert row["qty_good"]     == 20
            assert row["qty_scrap"]    == 2
        finally:
            if ticket_id:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM labor_tickets WHERE ticket_id = :id"), {"id": ticket_id})
                    conn.commit()

    def test_read_labor_tickets_query(self, engine, test_ticket):
        df = pd.read_sql_query("""
            SELECT ticket_id, employee_id, job_no, machine_id, op_code, op_desc,
                   time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap
            FROM labor_tickets ORDER BY ticket_id
        """, engine)
        assert test_ticket in df["ticket_id"].values

    def test_update_labor_ticket_fields(self, engine, test_ticket):
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE labor_tickets SET
                    op_desc    = 'Updated Op Desc',
                    run_hours  = 5.0,
                    qty_good   = 15,
                    qty_scrap  = 0
                WHERE ticket_id = :id
            """), {"id": test_ticket})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT op_desc, run_hours, qty_good, qty_scrap FROM labor_tickets WHERE ticket_id = :id"),
                {"id": test_ticket}
            ).fetchone()
        assert row[0] == "Updated Op Desc"
        assert float(row[1]) == 5.0
        assert row[2] == 15
        assert row[3] == 0

    def test_ticket_time_out_nullable(self, engine, test_work_center, test_employee, test_job):
        """time_out=NULL represents an active (clocked-in) ticket."""
        ticket_id = None
        try:
            with engine.connect() as conn:
                ticket_id = conn.execute(text("""
                    INSERT INTO labor_tickets
                        (employee_id, job_no, machine_id, op_code, time_in)
                    VALUES (:emp, :job, :wc, '10', NOW())
                    RETURNING ticket_id
                """), {"emp": TEST_EMP_ID, "job": TEST_JOB_NO, "wc": TEST_WC_ID}).scalar()
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT time_out FROM labor_tickets WHERE ticket_id = :id"),
                    {"id": ticket_id}
                ).fetchone()
            assert row[0] is None
        finally:
            if ticket_id:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM labor_tickets WHERE ticket_id = :id"), {"id": ticket_id})
                    conn.commit()

    def test_delete_labor_ticket(self, engine, test_ticket):
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM labor_tickets WHERE ticket_id = :id"), {"id": test_ticket})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM labor_tickets WHERE ticket_id = :id"), {"id": test_ticket}
            ).fetchone()
        assert row is None

    def test_active_checkins_query(self, engine, test_work_center, test_employee, test_job):
        """The Live View query (time_out IS NULL) returns only open tickets."""
        ticket_id = None
        try:
            with engine.connect() as conn:
                ticket_id = conn.execute(text("""
                    INSERT INTO labor_tickets (employee_id, job_no, machine_id, op_code, time_in)
                    VALUES (:emp, :job, :wc, '10', NOW())
                    RETURNING ticket_id
                """), {"emp": TEST_EMP_ID, "job": TEST_JOB_NO, "wc": TEST_WC_ID}).scalar()
                conn.commit()

            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT ticket_id FROM labor_tickets WHERE time_out IS NULL AND machine_id = :wc"),
                    {"wc": TEST_WC_ID}
                ).fetchall()

            ticket_ids = [r[0] for r in rows]
            assert ticket_id in ticket_ids
        finally:
            if ticket_id:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM labor_tickets WHERE ticket_id = :id"), {"id": ticket_id})
                    conn.commit()

    def test_serial_pk_auto_increments(self, engine, test_work_center, test_employee, test_job):
        """Each new labor ticket gets a unique, incrementing ticket_id."""
        ids = []
        try:
            with engine.connect() as conn:
                for _ in range(3):
                    tid = conn.execute(text("""
                        INSERT INTO labor_tickets (employee_id, job_no, machine_id, op_code, time_in)
                        VALUES (:emp, :job, :wc, '10', NOW())
                        RETURNING ticket_id
                    """), {"emp": TEST_EMP_ID, "job": TEST_JOB_NO, "wc": TEST_WC_ID}).scalar()
                    ids.append(tid)
                conn.commit()
            assert len(set(ids)) == 3
            assert ids == sorted(ids)
        finally:
            with engine.connect() as conn:
                for tid in ids:
                    conn.execute(text("DELETE FROM labor_tickets WHERE ticket_id = :id"), {"id": tid})
                conn.commit()
