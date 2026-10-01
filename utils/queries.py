"""Shared, cached query layer for MaintDB.

Cross-page aggregations (attention counts, PM schedule, floor status, reliability,
cost, …) live here so every page reads them the same way and they cache together.
The page-local one-off queries stay inline in app.py via ``_q``.

Caching: read functions are decorated with ``@st.cache_data``. The SQLAlchemy
engine is passed as ``_engine`` (leading underscore) so Streamlit does not try to
hash it. The sidebar "Refresh Data" button already calls ``st.cache_data.clear()``;
every write helper here also clears the cache so the UI never shows stale counts.
"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

# Allowed Pareto dimensions — whitelisted because the column name is interpolated.
PARETO_DIMS = {"issue_category", "root_cause"}

# Root of the on-disk per-asset document folders. Assets are matched to folders by
# asset_id prefix (the stored folder_path column points at another machine and is
# not used). Defaults next to the project; the bundled desktop app overrides it via
# MAINTDB_DOC_ROOT to point at a writable per-user location (the .app is read-only).
DOC_ROOT = Path(os.getenv("MAINTDB_DOC_ROOT")
                or (Path(__file__).resolve().parent.parent / "Maintenance_DB"))


# ── Identity (session-scoped; persisted to the device in the sidebar) ──────────
def current_user() -> str:
    return (st.session_state.get("current_user") or "").strip()


def set_current_user(name: str) -> None:
    st.session_state["current_user"] = (name or "").strip()


def employee_names(engine):
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT name FROM employees WHERE name IS NOT NULL AND name <> '' ORDER BY name"
        )).fetchall()
    return [r[0] for r in rows]


def add_employee(engine, name, role="Maintenance"):
    """Add a person if they're not already listed, generating the next EMP### id.
    Returns the trimmed name (existing or new), or None for blank input."""
    name = (name or "").strip()
    if not name:
        return None
    with engine.begin() as c:
        if c.execute(text("SELECT 1 FROM employees WHERE name = :n"), {"n": name}).fetchone():
            return name
        nxt = c.execute(text(
            "SELECT COALESCE(MAX(CAST(SUBSTRING(employee_id FROM 4) AS INTEGER)), 0) "
            "FROM employees WHERE employee_id ~ '^EMP[0-9]+$'"
        )).scalar()
        new_id = f"EMP{int(nxt) + 1:03d}"
        c.execute(text("INSERT INTO employees(employee_id, name, role) VALUES (:i, :n, :r)"),
                  {"i": new_id, "n": name, "r": role})
    st.cache_data.clear()
    return name


# ── Settings (shop_config key/value) ───────────────────────────────────────────
def get_config(engine, key, default=None):
    with engine.connect() as c:
        row = c.execute(text("SELECT value FROM shop_config WHERE key = :k"), {"k": key}).fetchone()
    return row[0] if row and row[0] is not None else default


def get_config_float(engine, key, default=0.0):
    try:
        return float(get_config(engine, key, default))
    except (TypeError, ValueError):
        return float(default)


def get_config_int(engine, key, default=0):
    try:
        return int(float(get_config(engine, key, default)))
    except (TypeError, ValueError):
        return int(default)


def set_config(engine, key, value) -> None:
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO shop_config(key, value, updated_at) VALUES (:k, :v, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """), {"k": key, "v": str(value)})
    st.cache_data.clear()


# ── PM schedule (f1) ───────────────────────────────────────────────────────────
def pm_bucket(days_until):
    """Bucket label from days-until-due; None days means no PM interval is set."""
    if days_until is None or pd.isna(days_until):
        return "No interval"
    if days_until < 0:
        return "Overdue"
    return "Due Soon"  # caller refines "Due Soon" vs "Scheduled" with the threshold


@st.cache_data(ttl=120)
def pm_schedule_df(_engine, due_soon_days=14):
    """One row per asset with its next PM due date and status bucket.

    next_due = (last finalized Preventive date, else commission_date) + interval.
    Assets with no/zero interval get next_due = NULL → 'No interval' (shown as "—",
    never conflated with "OK")."""
    # days_until is computed in SQL against the DB session's CURRENT_DATE so this
    # page and attention_counts (which also buckets against CURRENT_DATE) never
    # disagree by a day when the host TZ and DB-session TZ resolve to different dates.
    df = pd.read_sql_query(text("""
        SELECT s.*, (s.next_due - CURRENT_DATE)::int AS days_until
        FROM (
            SELECT a.asset_id, a.asset_code, a.display_name, a.equipment_category,
                   a.planned_pm_interval_days AS interval_days,
                   a.commission_date,
                   lp.last_pm,
                   CASE
                     WHEN a.planned_pm_interval_days IS NULL OR a.planned_pm_interval_days <= 0 THEN NULL
                     ELSE (COALESCE(lp.last_pm::date, a.commission_date)
                           + a.planned_pm_interval_days * INTERVAL '1 day')::date
                   END AS next_due
            FROM assets a
            LEFT JOIN (
                SELECT asset_code, MAX(finalized_at) AS last_pm
                FROM service_reports
                WHERE record_state = 'Final' AND service_type = 'Preventive'
                GROUP BY asset_code
            ) lp ON lp.asset_code = a.asset_code
        ) s
        ORDER BY s.asset_code
    """), _engine)

    df["days_until"] = pd.to_numeric(df["days_until"], errors="coerce")
    def _status(d):
        if pd.isna(d):
            return "No interval"
        if d < 0:
            return "Overdue"
        if d <= due_soon_days:
            return "Due Soon"
        return "Scheduled"
    df["status"] = df["days_until"].apply(_status)
    return df


# ── Floor status board (f7) ────────────────────────────────────────────────────
def _floor_status(row):
    draft_type = row.get("draft_type") or ""
    astat = (row.get("asset_status") or "").strip().lower()
    if draft_type in ("Corrective", "Emergency") or "repair" in astat or astat == "down":
        return "DOWN"
    if row.get("job_no"):
        return "RUNNING"
    if any(k in astat for k in ("retired", "offline", "decommission")):
        return "OFFLINE"
    return "IDLE"


@st.cache_data(ttl=60)
def floor_status_df(_engine):
    """One row per work_center with a derived DOWN / RUNNING / IDLE / OFFLINE status.

    DOWN  = an open Corrective/Emergency draft, or asset_status indicates repair/down.
    RUNNING = an open labor ticket (time_out IS NULL) on that machine.
    OFFLINE = asset_status retired/offline. Otherwise IDLE. (DOWN > RUNNING > OFFLINE.)"""
    df = pd.read_sql_query(text("""
        SELECT wc.machine_id, wc.machine_name, wc.department,
               a.asset_code, a.asset_status, a.display_name,
               d.draft_type,
               lt.job_no, lt.op_code, lt.emp_name
        FROM work_centers wc
        LEFT JOIN assets a ON a.asset_code = wc.machine_id
        LEFT JOIN LATERAL (
            SELECT sr.service_type AS draft_type
            FROM service_reports sr
            WHERE sr.asset_code = wc.machine_id AND sr.record_state = 'Draft'
            ORDER BY sr.created_at DESC LIMIT 1
        ) d ON TRUE
        LEFT JOIN LATERAL (
            SELECT lt.job_no, lt.op_code, e.name AS emp_name
            FROM labor_tickets lt
            LEFT JOIN employees e ON e.employee_id = lt.employee_id
            WHERE lt.machine_id = wc.machine_id AND lt.time_out IS NULL
            ORDER BY lt.time_in DESC LIMIT 1
        ) lt ON TRUE
        ORDER BY wc.machine_id
    """), _engine)
    if df.empty:
        df["status"] = []
        return df
    df["status"] = df.apply(_floor_status, axis=1)
    return df


def floor_status_counts(_engine):
    df = floor_status_df(_engine)
    base = {"DOWN": 0, "RUNNING": 0, "IDLE": 0, "OFFLINE": 0}
    if not df.empty:
        base.update(df["status"].value_counts().to_dict())
    return base


# ── Issue inbox (f8) ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def open_issues_df(_engine):
    return pd.read_sql_query(text("""
        SELECT id, asset_code, asset_id, note, priority, status, created_by,
               created_at, promoted_report_id
        FROM machine_issues
        WHERE status = 'Open'
        ORDER BY CASE priority WHEN 'High' THEN 0 WHEN 'Normal' THEN 1 ELSE 2 END,
                 created_at DESC
    """), _engine)


# ── Attention counts (Today cockpit + menu badges) ─────────────────────────────
@st.cache_data(ttl=120)
def attention_counts(_engine, due_soon_days=14):
    with _engine.connect() as c:
        open_drafts = c.execute(text(
            "SELECT COUNT(*) FROM service_reports WHERE record_state = 'Draft'")).scalar()
        open_issues = c.execute(text(
            "SELECT COUNT(*) FROM machine_issues WHERE status = 'Open'")).scalar()
        pm = c.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE nd < CURRENT_DATE) AS overdue,
              COUNT(*) FILTER (WHERE nd >= CURRENT_DATE AND nd <= CURRENT_DATE + :soon) AS due_soon
            FROM (
              SELECT (COALESCE(MAX(sr.finalized_at)::date, a.commission_date)
                      + a.planned_pm_interval_days * INTERVAL '1 day')::date AS nd
              FROM assets a
              LEFT JOIN service_reports sr
                ON sr.asset_code = a.asset_code AND sr.record_state = 'Final'
                AND sr.service_type = 'Preventive'
              WHERE a.planned_pm_interval_days IS NOT NULL AND a.planned_pm_interval_days > 0
              GROUP BY a.asset_id, a.commission_date, a.planned_pm_interval_days
            ) x
            WHERE nd IS NOT NULL
        """), {"soon": int(due_soon_days)}).mappings().fetchone()
    return {
        "overdue":     int(pm["overdue"] or 0),
        "due_soon":    int(pm["due_soon"] or 0),
        "open_drafts": int(open_drafts or 0),
        "open_issues": int(open_issues or 0),
        "down":        int(floor_status_counts(_engine).get("DOWN", 0)),
    }


# ── Reliability / bad-actor scorecard (f2) ─────────────────────────────────────
@st.cache_data(ttl=120)
def bad_actor_df(_engine):
    """Per-asset reliability rollup over FINAL service events: event count, total
    downtime, emergency/corrective counts, and an MTTR proxy (avg downtime on
    unplanned events). Ordered worst-first by total downtime."""
    return pd.read_sql_query(text("""
        SELECT sr.asset_code,
               COALESCE(a.display_name, sr.asset_code) AS display_name,
               a.equipment_category,
               COUNT(*) AS events,
               COALESCE(SUM(sr.downtime_hours), 0) AS total_downtime,
               COUNT(*) FILTER (WHERE sr.service_type = 'Emergency') AS emergencies,
               COUNT(*) FILTER (WHERE sr.service_type = 'Corrective') AS correctives,
               ROUND(AVG(sr.downtime_hours)
                     FILTER (WHERE sr.service_type IN ('Corrective', 'Emergency'))::numeric, 2) AS mttr,
               MAX(sr.finalized_at) AS last_event
        FROM service_reports sr
        LEFT JOIN assets a ON a.asset_code = sr.asset_code
        WHERE sr.record_state = 'Final'
        GROUP BY sr.asset_code, a.display_name, a.equipment_category
        ORDER BY total_downtime DESC, events DESC
    """), _engine)


# ── Failure-mode Pareto (f4) ───────────────────────────────────────────────────
@st.cache_data(ttl=120)
def pareto_df(_engine, dimension):
    """Counts + downtime per category for a whitelisted dimension. NULL/blank →
    'Unknown' so unclassified events are visible, never silently dropped."""
    if dimension not in PARETO_DIMS:
        raise ValueError(f"Unsupported Pareto dimension: {dimension}")
    return pd.read_sql_query(text(f"""
        SELECT COALESCE(NULLIF(TRIM({dimension}), ''), 'Unknown') AS category,
               COUNT(*) AS events,
               COALESCE(SUM(downtime_hours), 0) AS downtime
        FROM service_reports
        WHERE record_state = 'Final'
        GROUP BY 1
        ORDER BY events DESC
    """), _engine)


# ── Searchable fix history (f3) ────────────────────────────────────────────────
def fix_history_df(engine, query="", categories=None, issues=None, root_causes=None):
    """Full-text-ish search over FINAL repair records. Not cached — it's a live,
    user-driven search. Empty filter lists mean 'all' (Postgres arrays via ANY)."""
    categories = categories or []
    issues = issues or []
    root_causes = root_causes or []
    q = (query or "").strip()
    params = {
        "q": q, "like": f"%{q}%",
        "cats": categories, "cats_all": len(categories) == 0,
        "iss": issues, "iss_all": len(issues) == 0,
        "rcs": root_causes, "rcs_all": len(root_causes) == 0,
    }
    return pd.read_sql_query(text("""
        SELECT sr.report_id, sr.service_id, sr.asset_code, a.equipment_category,
               sr.service_type, sr.issue_category, sr.root_cause,
               sr.problem_description, sr.work_performed, sr.downtime_hours,
               sr.finalized_at, p.parts
        FROM service_reports sr
        LEFT JOIN assets a ON a.asset_code = sr.asset_code
        LEFT JOIN LATERAL (
            SELECT string_agg(part_name || ' x' || quantity, ', ') AS parts
            FROM service_parts WHERE report_id = sr.report_id
        ) p ON TRUE
        WHERE sr.record_state = 'Final'
          AND (:q = '' OR (COALESCE(sr.problem_description, '') || ' ' ||
                           COALESCE(sr.work_performed, '') || ' ' ||
                           sr.asset_code) ILIKE :like)
          AND (:cats_all OR a.equipment_category = ANY(:cats))
          AND (:iss_all  OR sr.issue_category    = ANY(:iss))
          AND (:rcs_all  OR sr.root_cause        = ANY(:rcs))
        ORDER BY sr.finalized_at DESC NULLS LAST
    """), engine, params=params)


def asset_fix_history_df(engine, asset_code):
    """Finalized service history for one asset (used by the Asset detail drawer)."""
    return pd.read_sql_query(text("""
        SELECT sr.report_id, sr.service_id, sr.service_type, sr.issue_category,
               sr.root_cause, sr.problem_description, sr.work_performed,
               sr.downtime_hours, sr.event_cost, sr.finalized_at
        FROM service_reports sr
        WHERE sr.record_state = 'Final' AND sr.asset_code = :code
        ORDER BY sr.finalized_at DESC NULLS LAST
    """), engine, params={"code": asset_code})


# ── Cost tracking (f10) ────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def cost_by_asset_df(_engine):
    return pd.read_sql_query(text("""
        SELECT sr.asset_code,
               COALESCE(a.display_name, sr.asset_code) AS display_name,
               COUNT(*) AS events,
               COALESCE(SUM(sr.event_cost), 0) AS total_cost,
               COALESCE(SUM(sr.downtime_hours), 0) AS total_downtime
        FROM service_reports sr
        LEFT JOIN assets a ON a.asset_code = sr.asset_code
        WHERE sr.record_state = 'Final'
        GROUP BY sr.asset_code, a.display_name
        ORDER BY total_cost DESC
    """), _engine)


@st.cache_data(ttl=120)
def cost_by_month_df(_engine):
    return pd.read_sql_query(text("""
        SELECT date_trunc('month', sr.finalized_at)::date AS month,
               COUNT(*) AS events,
               COALESCE(SUM(sr.event_cost), 0) AS total_cost
        FROM service_reports sr
        WHERE sr.record_state = 'Final' AND sr.finalized_at IS NOT NULL
        GROUP BY date_trunc('month', sr.finalized_at)
        ORDER BY month
    """), _engine)


# ── Documents (f6) ─────────────────────────────────────────────────────────────
def asset_documents_df(engine, asset_id):
    return pd.read_sql_query(text("""
        SELECT id, file_name, rel_path, doc_type, added_by, added_at
        FROM documents WHERE asset_id = :aid ORDER BY doc_type NULLS LAST, file_name
    """), engine, params={"aid": asset_id})


def _doc_type(fname):
    low = fname.lower()
    if "registry" in low:
        return "Registry"
    if "pm" in low:
        return "PM"
    if "manual" in low or "parts" in low:
        return "Manual"
    return "Other"


def _asset_folder(asset_id):
    """The on-disk folder for an asset: an existing dir named after the asset_id
    prefix, else DOC_ROOT/<asset_id> (created on first upload)."""
    if DOC_ROOT.exists():
        for d in DOC_ROOT.iterdir():
            if d.is_dir() and (d.name == asset_id or d.name.startswith(asset_id + "-")):
                return d
    return DOC_ROOT / asset_id


def backfill_documents(engine, added_by=None):
    """Walk each asset's on-disk folder and register its files in the documents
    table. Idempotent (ON CONFLICT DO NOTHING). Returns the number newly indexed."""
    if not DOC_ROOT.exists():
        return 0
    inserted = 0
    with engine.begin() as c:
        asset_ids = [r[0] for r in c.execute(text("SELECT asset_id FROM assets")).fetchall()]
        for aid in asset_ids:
            folder = _asset_folder(aid)
            if not folder.exists():
                continue
            for f in sorted(folder.iterdir()):
                if not f.is_file() or f.name.startswith("."):
                    continue
                res = c.execute(text("""
                    INSERT INTO documents (asset_id, file_name, rel_path, doc_type, added_by)
                    VALUES (:aid, :fn, :rp, :dt, :by)
                    ON CONFLICT (asset_id, rel_path) DO NOTHING
                """), {"aid": aid, "fn": f.name, "rp": f"{folder.name}/{f.name}",
                       "dt": _doc_type(f.name), "by": added_by})
                inserted += res.rowcount or 0
    st.cache_data.clear()
    return inserted


def read_document(rel_path):
    """Return a registered document's bytes, guarding against path traversal —
    the resolved path must stay inside DOC_ROOT."""
    target = (DOC_ROOT / rel_path).resolve()
    root = DOC_ROOT.resolve()
    # Real path containment — a string-prefix check would let a sibling directory
    # whose name starts with the root's name (…/Maintenance_DB_secret) slip through.
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("Invalid document path.")
    return target.read_bytes()


def save_document(engine, asset_id, filename, data, added_by=None):
    """Save an uploaded file into the asset's folder and register it. Returns the
    rel_path. Skips the DB row if that path is already registered."""
    folder = _asset_folder(asset_id)
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name  # strip any directory component
    dest = folder / safe_name
    dest.write_bytes(data)
    rel = f"{folder.name}/{safe_name}"
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO documents (asset_id, file_name, rel_path, doc_type, added_by)
            VALUES (:aid, :fn, :rp, :dt, :by)
            ON CONFLICT (asset_id, rel_path) DO NOTHING
        """), {"aid": asset_id, "fn": safe_name, "rp": rel,
               "dt": _doc_type(safe_name), "by": added_by})
    st.cache_data.clear()
    return rel
