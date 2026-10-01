"""Tests for the issue inbox → service draft promotion (f8)."""
from sqlalchemy import text

from utils.db import promote_issue
from tests.conftest import TEST_ASSET_CODE, TEST_ASSET_ID


def _add_issue(engine, note):
    with engine.begin() as c:
        return c.execute(text(
            "INSERT INTO machine_issues (asset_code, asset_id, note, priority, created_by) "
            "VALUES (:c, :a, :n, 'High', 'T') RETURNING id"
        ), {"c": TEST_ASSET_CODE, "a": TEST_ASSET_ID, "n": note}).scalar()


def test_promote_creates_corrective_draft(engine, test_asset):
    iid = _add_issue(engine, "alarm A")
    rid = promote_issue(engine, iid, created_by="T")
    with engine.connect() as c:
        rec = c.execute(text("SELECT record_state, service_type, problem_description "
                             "FROM service_reports WHERE report_id = :r"), {"r": rid}).mappings().fetchone()
        iss = c.execute(text("SELECT status, promoted_report_id FROM machine_issues WHERE id = :i"),
                        {"i": iid}).mappings().fetchone()
    assert rec["record_state"] == "Draft"
    assert rec["service_type"] == "Corrective"
    assert "alarm A" in (rec["problem_description"] or "")
    assert iss["status"] == "Promoted"
    assert iss["promoted_report_id"] == rid


def test_promote_appends_to_existing_draft(engine, test_asset):
    """Promoting when an open draft already exists must append (not create a second
    draft) so the one-open-draft-per-asset constraint is respected."""
    with engine.begin() as c:
        rid0 = c.execute(text(
            "INSERT INTO service_reports (asset_id, asset_code, record_state, service_type, "
            "problem_description) VALUES (:a, :c, 'Draft', 'Corrective', 'first') RETURNING report_id"
        ), {"a": TEST_ASSET_ID, "c": TEST_ASSET_CODE}).scalar()
    iid = _add_issue(engine, "second issue")
    rid = promote_issue(engine, iid)
    assert rid == rid0
    with engine.connect() as c:
        desc = c.execute(text("SELECT problem_description FROM service_reports WHERE report_id = :r"),
                         {"r": rid0}).scalar()
        n_drafts = c.execute(text("SELECT COUNT(*) FROM service_reports "
                                  "WHERE asset_code = :c AND record_state = 'Draft'"),
                             {"c": TEST_ASSET_CODE}).scalar()
    assert "first" in desc and "second issue" in desc
    assert n_drafts == 1
