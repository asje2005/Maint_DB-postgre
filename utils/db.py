import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from sqlalchemy import create_engine, text

_SCHEMA_FIXES = Path(__file__).resolve().parent.parent / "schema_fixes.sql"


@st.cache_resource
def get_engine():
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db   = os.getenv("PG_DB",   "maintdb")
    user = os.getenv("PG_USER", os.getenv("USER", "postgres"))
    pwd  = os.getenv("PG_PASS", "")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


@st.cache_resource
def ensure_schema():
    """Apply schema_fixes.sql once per process so a live (or native-run) database
    is migrated automatically — no manual psql step. Every statement in that file
    is additive and idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS / ON
    CONFLICT DO NOTHING), so re-running it is safe. Cached as a resource, so the
    work happens once; if it raises (e.g. DB momentarily down) nothing is cached
    and the next call retries."""
    sql = _SCHEMA_FIXES.read_text(encoding="utf-8")
    raw = get_engine().raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(sql)            # psycopg2 executes the whole multi-statement file
        raw.commit()
    finally:
        raw.close()
    return True


def _config_float(conn, key, default):
    row = conn.execute(text("SELECT value FROM shop_config WHERE key = :k"), {"k": key}).fetchone()
    try:
        return float(row[0]) if row and row[0] is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def _num_or(value, default):
    """Coerce a data-editor cell to a number, or ``default`` when it is blank/NaN.

    A blank cell in a multi-row st.data_editor grid arrives as ``np.float64('nan')``
    (pandas upcasts the column to float64), and ``float('nan')`` is neither None nor
    catchable by SQL ``COALESCE`` — inserting it would poison every cost aggregate
    with ``NaN``. The ``v != v`` test catches NaN for plain float and numpy float."""
    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if f != f else f


def finalize_service_draft(engine, report_id, *, created_by=None, verified_by=None):
    """Finalize a Draft service report in ONE atomic transaction.

    Steps (all-or-nothing under ``engine.begin()``):
      1. Lock the row, enforce the finalize guards (Verified By present, Return To
         Service is Yes/No, not already Final).
      2. Compute ``event_cost`` from the shop_config rates and any priced parts.
      3. Generate the next free ``service_id`` (``S-<code>-<YYYYMMDD>-NNN``) and flip
         the record to Final.

    ``verified_by`` (when given) is written onto the row before the check, so the
    one-screen Quick-Log can supply it in the same submit. Raises ``ValueError`` on
    any guard failure — the caller surfaces the message and nothing is committed.
    Returns the generated ``service_id``.
    """
    with engine.begin() as conn:
        sid = _finalize_on_conn(conn, report_id, created_by=created_by, verified_by=verified_by)
    st.cache_data.clear()  # invalidate cached aggregates/badges after the write
    return sid


def _finalize_on_conn(conn, report_id, *, created_by=None, verified_by=None):
    """The finalize body, operating on an already-open connection/transaction so it
    can be composed with an insert in the SAME transaction (Quick-Log)."""
    row = conn.execute(text("""
        SELECT asset_code, record_state, return_to_service, verified_by, downtime_hours
        FROM service_reports WHERE report_id = :id FOR UPDATE
    """), {"id": report_id}).mappings().fetchone()
    if row is None:
        raise ValueError(f"Service report {report_id} not found.")
    if row["record_state"] == "Final":
        raise ValueError("This record is already finalized.")

    vby = verified_by if (verified_by is not None and str(verified_by).strip()) else row["verified_by"]
    if not (vby and str(vby).strip()):
        raise ValueError("Verified By is required before finalization.")
    if row["return_to_service"] not in ("Yes", "No"):
        raise ValueError("Return To Service must be set to Yes or No before finalization.")

    asset_code = row["asset_code"]
    downtime = float(row["downtime_hours"] or 0.0)
    labor_rate = _config_float(conn, "labor_rate_per_hour", 0.0)
    downtime_rate = _config_float(conn, "downtime_rate_per_hour", 0.0)
    parts_cost = conn.execute(text(
        "SELECT COALESCE(SUM(quantity * COALESCE(unit_cost, 0)), 0) "
        "FROM service_parts WHERE report_id = :id"
    ), {"id": report_id}).scalar() or 0.0
    event_cost = round((labor_rate + downtime_rate) * downtime + float(parts_cost), 2)

    service_date = datetime.now().strftime("%Y%m%d")
    seq = 1
    while True:
        sid = f"S-{asset_code}-{service_date}-{seq:03d}"
        if conn.execute(text("SELECT 1 FROM service_reports WHERE service_id = :s"),
                        {"s": sid}).fetchone() is None:
            break
        seq += 1

    conn.execute(text("""
        UPDATE service_reports SET
            service_id   = :sid,
            record_state = 'Final',
            finalized_at = NOW(),
            updated_at   = NOW(),
            event_cost   = :cost,
            verified_by  = :vby,
            created_by   = COALESCE(created_by, :cby)
        WHERE report_id = :id
    """), {"sid": sid, "cost": event_cost, "vby": str(vby).strip(),
           "cby": created_by, "id": report_id})
    return sid


def create_service_record(engine, *, asset_code, service_type, fields, parts,
                          finalize=False, created_by=None):
    """Create a service report (and its parts) in ONE transaction; optionally lock
    & finalize it atomically. Used by the one-screen Quick-Log so create→parts→
    finalize all roll back together on any guard failure.

    ``fields`` is a dict of optional columns (problem_description, work_performed,
    downtime_hours, return_to_service, verified_by, issue_category, root_cause).
    ``parts`` is a list of dicts: {part_name, quantity, is_battery, unit_cost}.
    Returns ``(report_id, service_id_or_None)``.
    """
    with engine.begin() as conn:
        rid = conn.execute(text("""
            INSERT INTO service_reports
                (asset_id, asset_code, record_state, service_type, problem_description,
                 work_performed, downtime_hours, return_to_service, verified_by,
                 issue_category, root_cause, created_by, entry_timestamp)
            VALUES (:aid, :code, 'Draft', :stype, :prob, :work, :dt, :rts, :vby,
                    :ic, :rc, :cby, NOW())
            RETURNING report_id
        """), {
            "aid": f"A-{asset_code}", "code": asset_code, "stype": service_type,
            "prob": fields.get("problem_description"), "work": fields.get("work_performed"),
            "dt": fields.get("downtime_hours"), "rts": fields.get("return_to_service"),
            "vby": fields.get("verified_by"), "ic": fields.get("issue_category"),
            "rc": fields.get("root_cause"), "cby": created_by,
        }).scalar()

        for p in parts:
            name = (p.get("part_name") or "").strip()
            if not name:
                continue
            conn.execute(text("""
                INSERT INTO service_parts (report_id, part_name, quantity, is_battery, unit_cost)
                VALUES (:rid, :name, :qty, :bat, :cost)
            """), {"rid": rid, "name": name, "qty": int(_num_or(p.get("quantity"), 1)),
                   "bat": bool(p.get("is_battery")), "cost": _num_or(p.get("unit_cost"), None)})

        sid = None
        if finalize:
            sid = _finalize_on_conn(conn, rid, created_by=created_by,
                                    verified_by=fields.get("verified_by"))
    st.cache_data.clear()  # invalidate cached aggregates/badges after the write
    return rid, sid


def promote_issue(engine, issue_id, created_by=None):
    """Promote an open machine issue into a service draft, atomically. If the asset
    already has an open draft, append the note to it (so the one-open-draft-per-asset
    constraint is honored rather than tripped); otherwise create a new Corrective
    draft. Marks the issue Promoted and returns the draft's report_id."""
    with engine.begin() as conn:
        issue = conn.execute(text(
            "SELECT asset_code, note FROM machine_issues WHERE id = :i FOR UPDATE"
        ), {"i": issue_id}).mappings().fetchone()
        if issue is None:
            raise ValueError("Issue not found.")
        code = issue["asset_code"]
        if not code:
            raise ValueError("This issue isn't tied to a machine, so it can't become a draft.")
        note = issue["note"]

        existing = conn.execute(text(
            "SELECT report_id, problem_description FROM service_reports "
            "WHERE asset_code = :c AND record_state = 'Draft' LIMIT 1"
        ), {"c": code}).mappings().fetchone()
        if existing:
            rid = existing["report_id"]
            merged = ((existing["problem_description"] or "").rstrip() + "\n• " + note).strip()
            conn.execute(text("UPDATE service_reports SET problem_description = :d, updated_at = NOW() "
                              "WHERE report_id = :id"), {"d": merged, "id": rid})
        else:
            rid = conn.execute(text("""
                INSERT INTO service_reports
                    (asset_id, asset_code, record_state, service_type,
                     problem_description, created_by, entry_timestamp)
                VALUES (:aid, :c, 'Draft', 'Corrective', :n, :by, NOW())
                RETURNING report_id
            """), {"aid": f"A-{code}", "c": code, "n": note, "by": created_by}).scalar()
        conn.execute(text("UPDATE machine_issues SET status = 'Promoted', "
                          "promoted_report_id = :rid, closed_at = NOW() WHERE id = :i"),
                     {"rid": rid, "i": issue_id})
    st.cache_data.clear()  # invalidate cached aggregates/badges after the write
    return rid
