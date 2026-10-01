"""Tests for one-screen Quick-Log capture (f9) — the create→parts→finalize path
must be a single all-or-nothing transaction."""
import math

import numpy as np
import pytest
from sqlalchemy import text

from utils import queries as q
from utils.db import create_service_record, _num_or
from tests.conftest import TEST_ASSET_CODE


def _rates(engine):
    return (q.get_config_float(engine, "labor_rate_per_hour", 75.0),
            q.get_config_float(engine, "downtime_rate_per_hour", 250.0))


def test_log_and_finalize_one_transaction(engine, test_asset):
    rid, sid = create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
        fields={"problem_description": "p", "work_performed": "w", "downtime_hours": 2.0,
                "return_to_service": "Yes", "verified_by": "Tech"},
        parts=[{"part_name": "Seal", "quantity": 2, "is_battery": False, "unit_cost": 12.5}],
        finalize=True, created_by="Tech")
    assert sid.startswith(f"S-{TEST_ASSET_CODE}-")
    with engine.connect() as c:
        rec = c.execute(text("SELECT record_state, event_cost, created_by "
                             "FROM service_reports WHERE report_id = :r"), {"r": rid}).mappings().fetchone()
        n_parts = c.execute(text("SELECT COUNT(*) FROM service_parts WHERE report_id = :r"),
                            {"r": rid}).scalar()
    labor, drate = _rates(engine)
    assert rec["record_state"] == "Final"
    assert rec["created_by"] == "Tech"
    assert float(rec["event_cost"]) == round((labor + drate) * 2 + 2 * 12.5, 2)
    assert n_parts == 1


def test_num_or_coerces_nan_and_bad_values():
    """_num_or must turn a blank/NaN data-editor cell into the default — a raw NaN
    leaking through would poison every downstream cost aggregate."""
    assert _num_or(float("nan"), 0) == 0
    assert _num_or(np.float64("nan"), None) is None
    assert _num_or(None, 7) == 7
    assert _num_or("not-a-number", 3) == 3
    assert _num_or(12.5, 0) == 12.5


def test_finalize_with_nan_part_cell_stays_finite(engine, test_asset):
    """A real blank data_editor cell arrives as np.float64('nan'); the finalize must
    coerce it (qty→default 1, cost→0) and produce a finite event_cost, not NaN."""
    labor, drate = _rates(engine)
    rid, sid = create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
        fields={"downtime_hours": 1.0, "return_to_service": "Yes", "verified_by": "T"},
        parts=[{"part_name": "BlankCell", "quantity": np.float64("nan"),
                "is_battery": False, "unit_cost": np.float64("nan")}],
        finalize=True, created_by="T")
    with engine.connect() as c:
        cost = c.execute(text("SELECT event_cost FROM service_reports WHERE report_id = :r"),
                         {"r": rid}).scalar()
        qty = c.execute(text("SELECT quantity FROM service_parts WHERE report_id = :r"),
                        {"r": rid}).scalar()
    assert math.isfinite(float(cost))
    assert float(cost) == round((labor + drate) * 1, 2)  # NaN cost contributes 0
    assert qty == 1  # NaN quantity coerced to the default 1


def test_save_as_draft_stays_draft(engine, test_asset):
    rid, sid = create_service_record(
        engine, asset_code=TEST_ASSET_CODE, service_type="Preventive",
        fields={"problem_description": "x", "downtime_hours": 0.0,
                "return_to_service": "Yes", "verified_by": None},
        parts=[], finalize=False, created_by="Tech")
    assert sid is None
    with engine.connect() as c:
        state = c.execute(text("SELECT record_state FROM service_reports WHERE report_id = :r"),
                          {"r": rid}).scalar()
    assert state == "Draft"


def test_finalize_rolls_back_on_missing_verifier(engine, test_asset):
    """A blank Verified By aborts the whole transaction — no draft, no orphan parts."""
    with pytest.raises(ValueError):
        create_service_record(
            engine, asset_code=TEST_ASSET_CODE, service_type="Corrective",
            fields={"downtime_hours": 1.0, "return_to_service": "Yes", "verified_by": None},
            parts=[{"part_name": "Belt", "quantity": 1, "is_battery": False, "unit_cost": 5.0}],
            finalize=True, created_by="T")
    with engine.connect() as c:
        n_reports = c.execute(text("SELECT COUNT(*) FROM service_reports WHERE asset_code = :c"),
                              {"c": TEST_ASSET_CODE}).scalar()
        n_parts = c.execute(text(
            "SELECT COUNT(*) FROM service_parts sp JOIN service_reports sr ON sr.report_id = sp.report_id "
            "WHERE sr.asset_code = :c"), {"c": TEST_ASSET_CODE}).scalar()
    assert n_reports == 0
    assert n_parts == 0
