"""Unit tests for the shared query layer (utils/queries.py) and cost math.

Uses the live dev database via the `engine` fixture and the disposable Z999
`test_asset`. Cached query functions are cleared before reads that follow a write,
so a stale cache never masks a regression.
"""
import pandas as pd
import pytest
import streamlit as st
from sqlalchemy import text

from utils import queries as q
from utils.db import create_service_record
from tests.conftest import TEST_ASSET_CODE, TEST_ASSET_ID


def _rates(engine):
    """The live labor + downtime rates, so cost assertions don't break when a user
    edits them on the Settings page (the defaults happen to be 75 / 250)."""
    return (q.get_config_float(engine, "labor_rate_per_hour", 75.0),
            q.get_config_float(engine, "downtime_rate_per_hour", 250.0))


def test_floor_status_precedence():
    """DOWN beats RUNNING beats OFFLINE beats IDLE, from the available signals."""
    f = q._floor_status
    assert f({"draft_type": "Corrective"}) == "DOWN"
    assert f({"draft_type": "Emergency"}) == "DOWN"
    assert f({"asset_status": "Under Repair"}) == "DOWN"
    assert f({"job_no": "J1"}) == "RUNNING"
    assert f({"draft_type": "Corrective", "job_no": "J1"}) == "DOWN"
    assert f({"asset_status": "Retired"}) == "OFFLINE"
    assert f({}) == "IDLE"


def test_pm_no_interval_shows_dash(engine, test_asset):
    """An asset with no PM interval is 'No interval' with a NaT due date — never
    silently treated as 'OK'."""
    st.cache_data.clear()
    df = q.pm_schedule_df(engine, 14)
    row = df[df["asset_code"] == TEST_ASSET_CODE].iloc[0]
    assert row["status"] == "No interval"
    assert pd.isna(row["next_due"])


def test_pm_overdue_from_commission_date(engine, test_asset):
    with engine.begin() as c:
        c.execute(text("UPDATE assets SET planned_pm_interval_days = 30, "
                       "commission_date = '2020-01-01' WHERE asset_id = :i"), {"i": TEST_ASSET_ID})
    st.cache_data.clear()
    df = q.pm_schedule_df(engine, 14)
    row = df[df["asset_code"] == TEST_ASSET_CODE].iloc[0]
    assert row["status"] == "Overdue"
    assert row["days_until"] < 0


def test_pm_uses_last_preventive_finalize(engine, test_asset):
    """A recently finalized Preventive event pushes the next due date out into the
    future (Scheduled), proving last_pm is preferred over commission_date."""
    with engine.begin() as c:
        c.execute(text("UPDATE assets SET planned_pm_interval_days = 365, "
                       "commission_date = '2000-01-01' WHERE asset_id = :i"), {"i": TEST_ASSET_ID})
    create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Preventive",
        fields={"downtime_hours": 0.0, "return_to_service": "Yes", "verified_by": "T"},
        parts=[], finalize=True, created_by="T")
    st.cache_data.clear()
    df = q.pm_schedule_df(engine, 14)
    row = df[df["asset_code"] == TEST_ASSET_CODE].iloc[0]
    assert row["status"] == "Scheduled"
    assert row["days_until"] > 300


def test_attention_counts_shape(engine):
    st.cache_data.clear()
    ac = q.attention_counts(engine, 14)
    assert {"overdue", "due_soon", "open_drafts", "open_issues", "down"} <= set(ac)
    assert all(isinstance(v, int) for v in ac.values())


def test_event_cost_formula(engine, test_asset):
    """event_cost = (labor + downtime rate) * hours + Σ qty*unit_cost, using the
    rates currently configured in shop_config."""
    labor, drate = _rates(engine)
    rid, _ = create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
        fields={"downtime_hours": 2.0, "return_to_service": "Yes", "verified_by": "T"},
        parts=[{"part_name": "X", "quantity": 3, "is_battery": False, "unit_cost": 10.0}],
        finalize=True, created_by="T")
    with engine.connect() as c:
        cost = c.execute(text("SELECT event_cost FROM service_reports WHERE report_id = :r"),
                         {"r": rid}).scalar()
    assert float(cost) == round((labor + drate) * 2 + 3 * 10, 2)


def test_event_cost_tolerates_unpriced_parts(engine, test_asset):
    """A NULL unit_cost contributes 0 rather than erroring (partial cost is fine)."""
    labor, drate = _rates(engine)
    rid, _ = create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
        fields={"downtime_hours": 1.0, "return_to_service": "Yes", "verified_by": "T"},
        parts=[{"part_name": "Unpriced", "quantity": 2, "is_battery": False, "unit_cost": None}],
        finalize=True, created_by="T")
    with engine.connect() as c:
        cost = c.execute(text("SELECT event_cost FROM service_reports WHERE report_id = :r"),
                         {"r": rid}).scalar()
    assert float(cost) == round((labor + drate) * 1, 2)  # parts add nothing


def test_fix_history_search(engine, test_asset):
    create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
        fields={"problem_description": "weird spindle alarm 7", "work_performed": "reseated cable",
                "downtime_hours": 1.0, "return_to_service": "Yes", "verified_by": "T"},
        parts=[], finalize=True, created_by="T")
    hits = q.fix_history_df(engine, "spindle alarm 7")
    assert (hits["asset_code"] == TEST_ASSET_CODE).any()
    miss = q.fix_history_df(engine, "zzz-definitely-no-match-zzz")
    assert not (miss["asset_code"] == TEST_ASSET_CODE).any()


def test_pareto_buckets_null_as_unknown(engine, test_asset):
    create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
        fields={"downtime_hours": 1.0, "return_to_service": "Yes", "verified_by": "T"},
        parts=[], finalize=True, created_by="T")  # no root_cause set
    st.cache_data.clear()
    df = q.pareto_df(engine, "root_cause")
    assert "Unknown" in set(df["category"])


def test_pareto_rejects_bad_dimension(engine):
    with pytest.raises(ValueError):
        q.pareto_df(engine, "problem_description; DROP TABLE assets")


# ── Previously-untested read layer + documents (coverage gap) ──────────────────
def test_add_employee_new_existing_and_blank(engine):
    """A new name is inserted with the next EMP### id; an existing name is a no-op
    returning the same name; blank input returns None."""
    name = "ZZ Coverage Tester Q9"
    try:
        assert q.add_employee(engine, "   ") is None          # blank → None
        assert q.add_employee(engine, name) == name           # new → inserted
        assert name in q.employee_names(engine)
        assert q.add_employee(engine, name) == name           # existing → no-op
        with engine.connect() as c:
            n = c.execute(text("SELECT COUNT(*) FROM employees WHERE name = :n"), {"n": name}).scalar()
            emp_id = c.execute(text("SELECT employee_id FROM employees WHERE name = :n"), {"n": name}).scalar()
        assert n == 1                                          # only one row, no duplicate
        assert emp_id.startswith("EMP")
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM employees WHERE name = :n"), {"n": name})


def test_config_roundtrip_and_defaults(engine):
    """set_config / get_config* round-trip a value and coerce types; a missing key
    falls back to the supplied default."""
    key = "zz_coverage_test_key"
    try:
        q.set_config(engine, key, "42.5")
        assert q.get_config(engine, key) == "42.5"
        assert q.get_config_float(engine, key, 0.0) == 42.5
        assert q.get_config_int(engine, key, 0) == 42          # int(float("42.5"))
        assert q.get_config_float(engine, "zz_missing_key_xyz", 9.0) == 9.0
        assert q.get_config_int(engine, "zz_missing_key_xyz", 3) == 3
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM shop_config WHERE key = :k"), {"k": key})


def test_reliability_and_cost_rollups(engine, test_asset):
    """bad_actor_df / cost_by_asset_df / cost_by_month_df / asset_fix_history_df all
    surface a finalized event for the asset with sane aggregates."""
    for stype, hrs in (("Corrective", 2.0), ("Emergency", 3.0)):
        create_service_record(
            engine, asset_code=TEST_ASSET_CODE, service_type=stype,
            fields={"downtime_hours": hrs, "return_to_service": "Yes", "verified_by": "T"},
            parts=[], finalize=True, created_by="T")
    st.cache_data.clear()

    ba = q.bad_actor_df(engine)
    row = ba[ba["asset_code"] == TEST_ASSET_CODE].iloc[0]
    assert int(row["events"]) == 2
    assert int(row["emergencies"]) == 1
    assert int(row["correctives"]) == 1
    assert float(row["total_downtime"]) == 5.0
    assert pd.notna(row["mttr"])

    ca = q.cost_by_asset_df(engine)
    assert (ca["asset_code"] == TEST_ASSET_CODE).any()
    assert float(ca[ca["asset_code"] == TEST_ASSET_CODE]["total_cost"].iloc[0]) > 0

    cm = q.cost_by_month_df(engine)
    assert not cm.empty and float(cm["total_cost"].sum()) > 0

    hist = q.asset_fix_history_df(engine, TEST_ASSET_CODE)
    assert len(hist) == 2


def test_open_issues_priority_ordering(engine, test_asset):
    """open_issues_df sorts High before Normal before Low regardless of insert time."""
    with engine.begin() as c:
        c.execute(text("INSERT INTO machine_issues (asset_code, asset_id, note, priority) "
                       "VALUES (:code, :id, 'normal one', 'Normal')"),
                  {"code": TEST_ASSET_CODE, "id": TEST_ASSET_ID})
        c.execute(text("INSERT INTO machine_issues (asset_code, asset_id, note, priority) "
                       "VALUES (:code, :id, 'high one', 'High')"),
                  {"code": TEST_ASSET_CODE, "id": TEST_ASSET_ID})
    st.cache_data.clear()
    df = q.open_issues_df(engine)
    mine = df[df["asset_code"] == TEST_ASSET_CODE].reset_index(drop=True)
    assert list(mine["priority"]).index("High") < list(mine["priority"]).index("Normal")
    # machine_issues for Z999 are cleaned up by the test_asset fixture teardown.


def test_save_and_read_document_with_traversal_guard(engine, test_asset):
    """save_document stores + registers a file; read_document returns its bytes and
    rejects a path that escapes the document root."""
    payload = b"%PDF-1.4 coverage-test"
    rel = q.save_document(engine, TEST_ASSET_ID, "coverage_manual.pdf", payload, added_by="T")
    assert q.read_document(rel) == payload

    docs = q.asset_documents_df(engine, TEST_ASSET_ID)
    assert (docs["file_name"] == "coverage_manual.pdf").any()

    with pytest.raises(ValueError):
        q.read_document("../../../../etc/passwd")
    # documents rows + the on-disk file are cleaned up by the test_asset fixture.
