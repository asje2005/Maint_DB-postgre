"""Tests for the JobBoss → Postgres sync (utils/jobboss.py).

The JobBoss read side needs a live SQL Server, so these inject a fake ``fetch``
(normalised dicts) to exercise the Postgres-side upserts: idempotency, in-place
updates, foreign-key safety, and the safe no-op when JobBoss is unavailable.
All test rows use a Z-prefix and are cleaned up unconditionally.
"""
import pytest
from sqlalchemy import text

from utils import jobboss

EMP = "ZEMP-JB1"
JOB = "ZJOB-JB1"
TKT = "ZTKT-JB1"
TKT2 = "ZTKT-JB2"


@pytest.fixture
def cleanup(engine):
    def _del():
        with engine.begin() as c:
            c.execute(text("DELETE FROM labor_tickets WHERE jobboss_ticket_id IN (:t1, :t2)"),
                      {"t1": TKT, "t2": TKT2})
            c.execute(text("DELETE FROM jobs      WHERE job_no = :j"), {"j": JOB})
            c.execute(text("DELETE FROM employees WHERE employee_id = :e"), {"e": EMP})
    _del()
    yield
    _del()


def _fetch(employees, jobs, labor):
    return lambda: (employees, jobs, labor)


def test_sync_upserts_then_updates_in_place(engine, cleanup):
    res = jobboss.sync_to_postgres(engine, fetch=_fetch(
        [{"employee_id": EMP, "name": "JB Tester", "role": "Operator"}],
        [{"job_no": JOB, "part_no": "P1", "customer": "Cust", "order_qty": 5, "status": "Active"}],
        [{"jobboss_ticket_id": TKT, "employee_id": EMP, "job_no": JOB,
          "machine_id": None, "op_code": "30", "op_desc": "Run", "run_hours": 2.0}],
    ))
    assert res["ok"] and (res["employees"], res["jobs"], res["labor"]) == (1, 1, 1)
    with engine.connect() as c:
        assert c.execute(text("SELECT name FROM employees WHERE employee_id = :e"), {"e": EMP}).scalar() == "JB Tester"
        assert c.execute(text("SELECT employee_id FROM labor_tickets WHERE jobboss_ticket_id = :t"), {"t": TKT}).scalar() == EMP

    # Re-sync with changed values: rows update in place, never duplicate.
    jobboss.sync_to_postgres(engine, fetch=_fetch(
        [{"employee_id": EMP, "name": "JB Tester v2", "role": "Lead"}],
        [{"job_no": JOB, "status": "Completed"}],
        [{"jobboss_ticket_id": TKT, "employee_id": EMP, "job_no": JOB, "run_hours": 3.0}],
    ))
    with engine.connect() as c:
        assert c.execute(text("SELECT name FROM employees WHERE employee_id = :e"), {"e": EMP}).scalar() == "JB Tester v2"
        assert c.execute(text("SELECT status FROM jobs WHERE job_no = :j"), {"j": JOB}).scalar() == "Completed"
        assert c.execute(text("SELECT COUNT(*) FROM labor_tickets WHERE jobboss_ticket_id = :t"), {"t": TKT}).scalar() == 1
        assert float(c.execute(text("SELECT run_hours FROM labor_tickets WHERE jobboss_ticket_id = :t"), {"t": TKT}).scalar()) == 3.0


def test_labor_fk_safety_nulls_missing_parents(engine, cleanup):
    """A labor ticket referencing an employee/job/machine that isn't in Postgres must
    still import — with those FKs stored as NULL — instead of failing the sync."""
    res = jobboss.sync_to_postgres(engine, fetch=_fetch(
        [], [],
        [{"jobboss_ticket_id": TKT2, "employee_id": "ZNOEMP", "job_no": "ZNOJOB",
          "machine_id": "ZNOMACH", "op_code": "10"}],
    ))
    assert res["ok"] and res["labor"] == 1
    with engine.connect() as c:
        row = c.execute(text("SELECT employee_id, job_no, machine_id FROM labor_tickets "
                             "WHERE jobboss_ticket_id = :t"), {"t": TKT2}).mappings().fetchone()
    assert row["employee_id"] is None and row["job_no"] is None and row["machine_id"] is None


def test_labor_without_ticket_id_is_skipped(engine, cleanup):
    """No JobBoss ticket id → no stable key to upsert on → the row is skipped."""
    res = jobboss.sync_to_postgres(engine, fetch=_fetch(
        [], [], [{"jobboss_ticket_id": None, "op_code": "99"}]))
    assert res["ok"] and res["labor"] == 0


def test_labor_sync_survives_stale_pk_sequence(engine, cleanup):
    """A DB restored from the seed dump can leave the labor PK sequence behind the
    max; the sync must advance it so an insert doesn't collide on ticket_id."""
    with engine.begin() as c:
        c.execute(text("SELECT setval(pg_get_serial_sequence('labor_tickets', 'ticket_id'), 1, false)"))
    res = jobboss.sync_to_postgres(engine, fetch=_fetch([], [], [{"jobboss_ticket_id": TKT, "op_code": "30"}]))
    assert res["ok"] and res["labor"] == 1
    with engine.connect() as c:
        tid = c.execute(text("SELECT ticket_id FROM labor_tickets WHERE jobboss_ticket_id = :t"), {"t": TKT}).scalar()
    assert tid > 1  # advanced past the seeded rows instead of colliding at 1


def test_malformed_numeric_is_coerced_to_null(engine, cleanup):
    """A non-numeric JobBoss value coerces to NULL instead of aborting the sync."""
    res = jobboss.sync_to_postgres(engine, fetch=_fetch(
        [], [{"job_no": JOB, "order_qty": "12 pcs", "est_setup_hours": "n/a"}], []))
    assert res["ok"] and res["jobs"] == 1
    with engine.connect() as c:
        row = c.execute(text("SELECT order_qty, est_setup_hours FROM jobs WHERE job_no = :j"),
                        {"j": JOB}).mappings().fetchone()
    assert row["order_qty"] is None and row["est_setup_hours"] is None


def test_db_rejected_value_fails_cleanly_and_rolls_back(engine, cleanup):
    """A value Postgres rejects (e.g. a bad date) must produce a clean ok=False — not
    an uncaught traceback — and roll back everything upserted earlier in the batch."""
    res = jobboss.sync_to_postgres(engine, fetch=_fetch(
        [{"employee_id": EMP, "name": "Should Roll Back"}],
        [{"job_no": JOB, "due_date": "not-a-real-date"}], []))
    assert res["ok"] is False
    assert "failed" in res["reason"].lower()
    with engine.connect() as c:  # the earlier employee upsert rolled back with the batch
        assert c.execute(text("SELECT COUNT(*) FROM employees WHERE employee_id = :e"), {"e": EMP}).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM jobs WHERE job_no = :j"), {"j": JOB}).scalar() == 0


def test_sync_is_noop_when_jobboss_unavailable(engine, monkeypatch):
    """With no pyodbc / no config, the real path must make zero DB changes."""
    for v in jobboss.ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    assert jobboss.available() is False
    res = jobboss.sync_to_postgres(engine)  # fetch=None → live path → safe no-op
    assert res["ok"] is False
    assert (res["employees"], res["jobs"], res["labor"]) == (0, 0, 0)
    assert res["reason"]
