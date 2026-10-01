"""Optional JobBoss / ECI M1 (SQL Server) → Postgres sync.

The app reads everything from Postgres. This module pulls *reference + labor* data
FROM JobBoss INTO Postgres so those tables can be backed by the live shop system —
without changing how any page works and without breaking when JobBoss is offline.

Design guarantees
-----------------
* **Read-only against JobBoss, upsert-only into Postgres.** Existing rows are
  updated in place; nothing is deleted. Locally-added employees/jobs and the
  seeded data are preserved.
* **Safe no-op when JobBoss is unreachable.** If ``pyodbc`` isn't installed, the
  connection isn't configured, or the server can't be reached, ``sync_to_postgres``
  changes nothing and returns ``ok=False`` with a reason. The app keeps running on
  whatever is already in Postgres.
* **No hardcoded credentials.** Connection details come from environment variables.
* **Idempotent.** Re-running updates the same rows (labor is keyed by its JobBoss
  ticket id via ``labor_tickets.jobboss_ticket_id``), so a re-sync never duplicates.

Setup (run on a machine that can reach the JobBoss server)
----------------------------------------------------------
1. Install the Microsoft ODBC Driver for SQL Server and the optional Python deps::

       pip install -r requirements-jobboss.txt        # pyodbc

2. Export the connection (never commit these)::

       export JOBBOSS_SERVER='192.168.1.50\\SQLEXPRESS'
       export JOBBOSS_DB='JOBBOSS_DB'
       export JOBBOSS_USER='readonly_user'
       export JOBBOSS_PASSWORD='...'
       # optional: export JOBBOSS_DRIVER='ODBC Driver 18 for SQL Server'

3. Sync from the CLI (``python sync_jobboss.py``) or the **Advanced → Settings**
   page's "Sync from JobBoss" button.

IMPORTANT — confirm the schema
------------------------------
The three SELECTs below use the column names from the app's old example snippet,
which are GUESSES at the JobBoss/ECI M1 schema. Edit ``_Q_EMPLOYEES`` / ``_Q_JOBS``
/ ``_Q_LABOR`` so each query returns the normalised column names the upserts expect
(documented above each query) for *your* JobBoss instance before relying on the data.
"""
import os

import streamlit as st
from sqlalchemy import text

ENV_VARS = ("JOBBOSS_SERVER", "JOBBOSS_DB", "JOBBOSS_USER", "JOBBOSS_PASSWORD")


# ── Connection config (env vars only) ──────────────────────────────────────────
def config():
    """Return the JobBoss connection settings from the environment, or None when
    the required vars (server + database) are unset."""
    server = os.getenv("JOBBOSS_SERVER")
    database = os.getenv("JOBBOSS_DB")
    if not (server and database):
        return None
    return {
        "server":   server,
        "database": database,
        "user":     os.getenv("JOBBOSS_USER", ""),
        "password": os.getenv("JOBBOSS_PASSWORD", ""),
        "driver":   os.getenv("JOBBOSS_DRIVER", "ODBC Driver 18 for SQL Server"),
    }


def available():
    """True only if pyodbc is importable AND the connection is configured. Used to
    decide whether a live sync can even be attempted."""
    try:
        import pyodbc  # noqa: F401
    except ImportError:
        return False
    return config() is not None


def status_text():
    """A short, human-readable reason the sync can/can't run — for the UI."""
    try:
        import pyodbc  # noqa: F401
    except ImportError:
        return "pyodbc is not installed (pip install -r requirements-jobboss.txt)."
    if config() is None:
        return ("JobBoss connection not configured — set the JOBBOSS_SERVER / "
                "JOBBOSS_DB / JOBBOSS_USER / JOBBOSS_PASSWORD environment variables.")
    return "Ready: pyodbc installed and connection configured."


def _connect():
    """Open a JobBoss (SQL Server) connection from the env config. Raises if pyodbc
    is missing or the connection isn't configured."""
    import pyodbc
    cfg = config()
    if cfg is None:
        raise RuntimeError(
            "JobBoss is not configured (set " + " / ".join(ENV_VARS) + ").")
    conn_str = (
        f"Driver={{{cfg['driver']}}};"
        f"Server={cfg['server']};"
        f"Database={cfg['database']};"
        f"UID={cfg['user']};"
        f"PWD={cfg['password']};"
        "Encrypt=optional;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


# ── JobBoss read queries — VERIFY/EDIT these against your real JobBoss schema ───
# Each must return exactly the normalised columns named in the comment; the SELECT
# aliases below are the mapping point (the source column names are guesses).

# Table/column names follow the JobBoss / ECI M1 conventions in the app's SQL
# Integration Guide (EMPLOYEE / JOB_ORDER / LABOR_TICKET / WORK_CENTER), but some
# columns are still best-guesses — confirm each against your instance.

# -> employee_id, name, role
_Q_EMPLOYEES = """
    SELECT EMPLOYEE_ID AS employee_id,
           FIRST_LAST_NAME AS name,
           JOB_TITLE AS role
    FROM EMPLOYEE
"""

# -> job_no, part_no, customer, order_qty, due_date, est_setup_hours, est_run_hours, status
_Q_JOBS = """
    SELECT JOB_NUMBER AS job_no,
           PART_NUMBER AS part_no,
           CUSTOMER_NAME AS customer,
           ORDER_QUANTITY AS order_qty,
           DUE_DATE AS due_date,
           ESTIMATE_SETUP_HRS AS est_setup_hours,
           ESTIMATE_RUN_HRS AS est_run_hours,
           STATUS AS status
    FROM JOB_ORDER
"""

# -> jobboss_ticket_id, employee_id, job_no, machine_id, op_code, op_desc,
#    time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap
_Q_LABOR = """
    SELECT TICKET_ID AS jobboss_ticket_id,
           EMPLOYEE_ID AS employee_id,
           JOB_NUMBER AS job_no,
           WORK_CENTER_ID AS machine_id,
           OP_CODE AS op_code,
           OP_DESCRIPTION AS op_desc,
           TIME_IN AS time_in,
           TIME_OUT AS time_out,
           SETUP_HRS AS setup_hours,
           RUN_HRS AS run_hours,
           QTY_GOOD AS qty_good,
           QTY_SCRAP AS qty_scrap
    FROM LABOR_TICKET
"""


def _default_fetch():
    """Open JobBoss and return (employees, jobs, labor) as lists of plain dicts."""
    conn = _connect()
    try:
        cur = conn.cursor()

        def rows(sql):
            cur.execute(sql)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        return rows(_Q_EMPLOYEES), rows(_Q_JOBS), rows(_Q_LABOR)
    finally:
        conn.close()


# ── Postgres upserts (schema-agnostic: operate on normalised dicts) ─────────────
def _s(v):
    """Trim to a clean string, or None for blank/None."""
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _int(v):
    """Coerce to int, or None when not a clean number — so one malformed JobBoss
    value (e.g. '12 pcs') becomes NULL instead of aborting the whole sync."""
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _num(v):
    """Coerce to float, or None when not a clean number (see ``_int``)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _upsert_employees(conn, rows):
    n = 0
    for r in rows:
        eid, name = _s(r.get("employee_id")), _s(r.get("name"))
        if not eid or not name:
            continue
        conn.execute(text("""
            INSERT INTO employees (employee_id, name, role)
            VALUES (:id, :name, :role)
            ON CONFLICT (employee_id) DO UPDATE
              SET name = EXCLUDED.name,
                  role = COALESCE(EXCLUDED.role, employees.role)
        """), {"id": eid, "name": name, "role": _s(r.get("role"))})
        n += 1
    return n


def _upsert_jobs(conn, rows):
    n = 0
    for r in rows:
        job_no = _s(r.get("job_no"))
        if not job_no:
            continue
        conn.execute(text("""
            INSERT INTO jobs (job_no, part_no, customer, order_qty, due_date,
                              est_setup_hours, est_run_hours, status)
            VALUES (:job, :part, :cust, :qty, :due, :setup, :run, :status)
            ON CONFLICT (job_no) DO UPDATE
              SET part_no = EXCLUDED.part_no, customer = EXCLUDED.customer,
                  order_qty = EXCLUDED.order_qty, due_date = EXCLUDED.due_date,
                  est_setup_hours = EXCLUDED.est_setup_hours,
                  est_run_hours = EXCLUDED.est_run_hours, status = EXCLUDED.status
        """), {"job": job_no, "part": _s(r.get("part_no")), "cust": _s(r.get("customer")),
               "qty": _int(r.get("order_qty")), "due": r.get("due_date"),
               "setup": _num(r.get("est_setup_hours")), "run": _num(r.get("est_run_hours")),
               "status": _s(r.get("status"))})
        n += 1
    return n


def _upsert_labor(conn, rows):
    """Upsert labor tickets keyed by their JobBoss ticket id. Foreign keys that
    don't exist in Postgres (employee/job/machine) are stored as NULL rather than
    failing the row, so an out-of-sync reference never aborts the whole sync; the
    app already renders NULL employee/job/machine gracefully."""
    # A DB restored straight from the seed dump can leave the SERIAL sequence behind
    # the seeded max; advance it so JobBoss inserts (which rely on the ticket_id
    # default) never collide with an existing PK. Idempotent and self-correcting.
    conn.execute(text(
        "SELECT setval(pg_get_serial_sequence('labor_tickets', 'ticket_id'), "
        "GREATEST((SELECT COALESCE(MAX(ticket_id), 0) FROM labor_tickets), 1))"))
    emp_ids = {r[0] for r in conn.execute(text("SELECT employee_id FROM employees"))}
    job_nos = {r[0] for r in conn.execute(text("SELECT job_no FROM jobs"))}
    machines = {r[0] for r in conn.execute(text("SELECT machine_id FROM work_centers"))}
    n = 0
    for r in rows:
        jid = _s(r.get("jobboss_ticket_id"))
        if not jid:
            continue  # no stable key → can't upsert idempotently; skip
        emp = _s(r.get("employee_id")); emp = emp if emp in emp_ids else None
        job = _s(r.get("job_no"));      job = job if job in job_nos else None
        mid = _s(r.get("machine_id"));  mid = mid if mid in machines else None
        conn.execute(text("""
            INSERT INTO labor_tickets
                (jobboss_ticket_id, employee_id, job_no, machine_id, op_code, op_desc,
                 time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap)
            VALUES (:jid, :emp, :job, :mid, :opc, :opd, :tin, :tout,
                    :setup, :run, :good, :scrap)
            ON CONFLICT (jobboss_ticket_id) WHERE jobboss_ticket_id IS NOT NULL DO UPDATE
              SET employee_id = EXCLUDED.employee_id, job_no = EXCLUDED.job_no,
                  machine_id = EXCLUDED.machine_id, op_code = EXCLUDED.op_code,
                  op_desc = EXCLUDED.op_desc, time_in = EXCLUDED.time_in,
                  time_out = EXCLUDED.time_out, setup_hours = EXCLUDED.setup_hours,
                  run_hours = EXCLUDED.run_hours, qty_good = EXCLUDED.qty_good,
                  qty_scrap = EXCLUDED.qty_scrap
        """), {"jid": jid, "emp": emp, "job": job, "mid": mid,
               "opc": _s(r.get("op_code")), "opd": _s(r.get("op_desc")),
               "tin": r.get("time_in"), "tout": r.get("time_out"),
               "setup": _num(r.get("setup_hours")), "run": _num(r.get("run_hours")),
               "good": _int(r.get("qty_good")), "scrap": _int(r.get("qty_scrap"))})
        n += 1
    return n


def sync_to_postgres(engine, fetch=None):
    """Pull employees/jobs/labor from JobBoss and upsert them into Postgres in one
    transaction. Returns a status dict::

        {"ok": bool, "reason": str, "employees": int, "jobs": int, "labor": int}

    ``fetch`` is injectable for testing/alternate sources: a zero-arg callable that
    returns ``(employees, jobs, labor)`` as lists of normalised dicts. When omitted,
    the live JobBoss connection is used — and if JobBoss is unavailable, this is a
    safe no-op (no DB writes) reporting ``ok=False``."""
    if fetch is None:
        if not available():
            return {"ok": False, "reason": status_text(),
                    "employees": 0, "jobs": 0, "labor": 0}
        try:
            fetch = _default_fetch
            employees, jobs, labor = fetch()
        except Exception as e:  # connection/query failure → no-op, surface the cause
            return {"ok": False, "reason": f"JobBoss read failed: {e}",
                    "employees": 0, "jobs": 0, "labor": 0}
    else:
        employees, jobs, labor = fetch()

    try:
        with engine.begin() as conn:  # one transaction → a failure rolls back cleanly
            ne = _upsert_employees(conn, employees)
            nj = _upsert_jobs(conn, jobs)
            nl = _upsert_labor(conn, labor)
    except Exception as e:  # a bad source value must not crash the caller (UI/CLI)
        return {"ok": False, "reason": f"JobBoss upsert failed: {e}",
                "employees": 0, "jobs": 0, "labor": 0}
    st.cache_data.clear()  # refresh cached floor/attention/ERP reads after the sync
    return {"ok": True, "reason": "Synced from JobBoss.",
            "employees": ne, "jobs": nj, "labor": nl}
