"""
UI tests for the Service Reports screens — these drive the real Streamlit app
via streamlit.testing.AppTest (not just the SQL behind it).

They render app.py, land on the Service Reports page through session_state,
interact with the widgets (dropdowns, the parts form, buttons), and assert both
the rendered output and the resulting database rows. Uses the Z999 test asset.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

# app.py does `from utils.db import get_engine`, so the repo root must be importable.
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.conftest import TEST_ASSET_ID, TEST_ASSET_CODE  # noqa: E402

APP_PATH = str(ROOT / "app.py")


# ── helpers ─────────────────────────────────────────────────────────────────────
def _widget(seq, label):
    for w in seq:
        if w.label == label:
            return w
    raise AssertionError(f"widget {label!r} not found; have {[w.label for w in seq]}")


def _markdown_contains(at, needle):
    return any(needle in (m.value or "") for m in at.markdown)


def _button_by_key(at, key):
    for b in at.button:
        if b.key == key:
            return b
    raise AssertionError(f"button with key {key!r} not found")


def _edit_app(report_id):
    """Render the app on Service Reports → Edit Existing Draft for one draft."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Edit Existing Draft"
    at.session_state["selected_draft_id"] = report_id
    return at.run()


# ── fixtures ────────────────────────────────────────────────────────────────────
@pytest.fixture
def ui_draft(engine, test_asset):
    """A clean Z999 Draft (no parts); yields its report_id and cleans up."""
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
        conn.commit()
        conn.execute(text("""
            INSERT INTO service_reports (asset_id, asset_code, record_state, service_type, entry_timestamp)
            VALUES (:aid, :code, 'Draft', 'Corrective', NOW())
        """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE})
        conn.commit()
        rid = conn.execute(
            text("SELECT report_id FROM service_reports WHERE asset_code = :c AND record_state = 'Draft'"),
            {"c": TEST_ASSET_CODE}
        ).scalar()

    yield rid

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
        conn.commit()


# ── tests: the edit form renders the new fields ──────────────────────────────────
def test_edit_form_shows_new_fields(ui_draft):
    at = _edit_app(ui_draft)
    assert not at.exception
    labels = [s.label for s in at.selectbox]
    assert "Issue Category" in labels
    assert "Root Cause" in labels
    assert any(b.label == "Add Part" for b in at.button), "Parts add form should be present"


# ── tests: saving issue category + root cause via the UI ─────────────────────────
def test_save_issue_and_root_cause_via_ui(engine, ui_draft):
    at = _edit_app(ui_draft)
    _widget(at.selectbox, "Issue Category").set_value("Electrical")
    _widget(at.selectbox, "Root Cause").set_value("Wear")
    _widget(at.button, "Save Changes to Draft").click()
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT issue_category, root_cause FROM service_reports WHERE report_id = :id"),
            {"id": ui_draft}
        ).mappings().fetchone()
    assert row["issue_category"] == "Electrical"
    assert row["root_cause"] == "Wear"


# ── tests: adding a part through the form ────────────────────────────────────────
def test_add_part_via_ui(engine, ui_draft):
    at = _edit_app(ui_draft)
    _widget(at.text_input, "Part name").set_value("Spindle bearing")
    _widget(at.number_input, "Qty").set_value(2)
    _widget(at.button, "Add Part").click()
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT part_name, quantity, is_battery FROM service_parts "
                 "WHERE report_id = :id ORDER BY id"),
            {"id": ui_draft}
        ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["part_name"] == "Spindle bearing"
    assert rows[0]["quantity"] == 2
    assert rows[0]["is_battery"] is False


def test_add_battery_part_via_ui(engine, ui_draft):
    at = _edit_app(ui_draft)
    _widget(at.text_input, "Part name").set_value("CNC backup battery")
    _widget(at.checkbox, "Battery replacement").set_value(True)
    _widget(at.button, "Add Part").click()
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT part_name, is_battery FROM service_parts WHERE report_id = :id"),
            {"id": ui_draft}
        ).mappings().fetchone()
    assert row["part_name"] == "CNC backup battery"
    assert row["is_battery"] is True


def test_blank_part_name_is_rejected(engine, ui_draft):
    """Submitting the add-part form with no name must not insert a row."""
    at = _edit_app(ui_draft)
    _widget(at.button, "Add Part").click()
    at.run()
    assert not at.exception
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM service_parts WHERE report_id = :id"),
            {"id": ui_draft}
        ).scalar()
    assert count == 0


# ── tests: deleting a part via its trash button ──────────────────────────────────
def test_delete_part_via_ui(engine, ui_draft):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO service_parts (report_id, part_name, quantity, is_battery)
            VALUES (:r, 'Old part', 1, FALSE)
        """), {"r": ui_draft})
        conn.commit()

    at = _edit_app(ui_draft)
    _widget(at.button, "Remove").click()   # per-part delete button (label is just the trash icon)
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM service_parts WHERE report_id = :id"),
            {"id": ui_draft}
        ).scalar()
    assert count == 0


# ── tests: finalize review shows the new fields and parts ────────────────────────
def test_finalize_review_shows_issue_cause_and_parts(engine, ui_draft):
    # Populate the draft and give it a part.
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE service_reports SET
                issue_category = 'Electrical', root_cause = 'Wear',
                verified_by = 'Alice Chen', return_to_service = 'Yes'
            WHERE report_id = :id
        """), {"id": ui_draft})
        conn.execute(text("""
            INSERT INTO service_parts (report_id, part_name, quantity, is_battery)
            VALUES (:r, 'Spindle bearing', 2, FALSE)
        """), {"r": ui_draft})
        conn.commit()

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Finalize Service Draft"
    at.session_state["selected_draft_id"] = ui_draft
    at.run()
    assert not at.exception

    assert _markdown_contains(at, "Electrical"), "Finalize review should show the issue category"
    assert _markdown_contains(at, "Wear"), "Finalize review should show the root cause"
    assert _markdown_contains(at, "Spindle bearing"), "Finalize review should list parts used"


# ── tests: full edit save (every field at once) ──────────────────────────────────
def test_full_edit_save_via_ui(engine, ui_draft):
    at = _edit_app(ui_draft)
    _widget(at.text_area, "Problem / Fault Description").set_value("Coolant leak from rear seal")
    _widget(at.text_area, "Action Taken / Work Performed").set_value("Replaced rear seal")
    _widget(at.selectbox, "Issue Category").set_value("Mechanical")
    _widget(at.selectbox, "Root Cause").set_value("Wear")
    _widget(at.number_input, "Downtime (Hours)").set_value(3.5)
    _widget(at.selectbox, "Return To Service?").set_value("Yes")
    _widget(at.text_input, "Report Compiled / Verified By").set_value("Bob Jones")
    _widget(at.button, "Save Changes to Draft").click()
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT problem_description, work_performed, issue_category, root_cause,
                   downtime_hours, return_to_service, verified_by
            FROM service_reports WHERE report_id = :id
        """), {"id": ui_draft}).mappings().fetchone()
    assert row["problem_description"] == "Coolant leak from rear seal"
    assert row["work_performed"]      == "Replaced rear seal"
    assert row["issue_category"]      == "Mechanical"
    assert row["root_cause"]          == "Wear"
    assert float(row["downtime_hours"]) == 3.5
    assert row["return_to_service"]   == "Yes"
    assert row["verified_by"]         == "Bob Jones"


# ── tests: finalizing a draft through the UI ─────────────────────────────────────
def test_finalize_via_ui(engine, ui_draft):
    # Finalize button only appears once verified_by + return_to_service are set.
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE service_reports SET
                problem_description = 'Axis alarm', work_performed = 'Replaced drive',
                verified_by = 'Alice Chen', return_to_service = 'Yes'
            WHERE report_id = :id
        """), {"id": ui_draft})
        conn.commit()

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Finalize Service Draft"
    at.session_state["selected_draft_id"] = ui_draft
    at.run()
    assert not at.exception

    _widget(at.button, "Lock & Finalize Record").click()
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT record_state, service_id, finalized_at FROM service_reports WHERE report_id = :id"),
            {"id": ui_draft}
        ).mappings().fetchone()
    assert row["record_state"] == "Final"
    assert row["service_id"].startswith(f"S-{TEST_ASSET_CODE}-")
    assert row["finalized_at"] is not None


# ── tests: creating a draft through the UI ───────────────────────────────────────
def test_create_draft_via_ui(engine, test_asset):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
        conn.commit()

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Create Service Draft"
    at.run()
    assert not at.exception

    # The asset selectbox uses dict options with a format_func; set the raw dict value.
    sel = _widget(at.selectbox, "Select Target Asset")
    sel.set_value({"code": TEST_ASSET_CODE, "label": "Z999-TEST"})
    _widget(at.selectbox, "Service Type / Classification").set_value("Preventive")
    _widget(at.button, "Create Draft Record").click()
    at.run()
    assert not at.exception

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT record_state, service_type FROM service_reports WHERE asset_code = :c"),
                {"c": TEST_ASSET_CODE}
            ).mappings().fetchone()
        assert row is not None, "A draft row should have been created"
        assert row["record_state"] == "Draft"
        assert row["service_type"] == "Preventive"
    finally:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
            conn.commit()


# ── tests: Quick Log save-as-draft through the UI ────────────────────────────────
def test_quick_log_save_draft_via_ui(engine, test_asset):
    """Driving the one-screen Quick Log → Save as draft must create a Draft row
    (exercises the _render_quick_log → create_service_record wiring)."""
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
        conn.commit()

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Quick Log"
    at.run()
    assert not at.exception

    _widget(at.selectbox, "Machine").set_value({"code": TEST_ASSET_CODE, "label": "Z999-TEST"})
    _widget(at.selectbox, "Service type").set_value("Preventive")
    _widget(at.button, "💾 Save as draft").click()
    at.run()
    assert not at.exception

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT record_state, service_type FROM service_reports WHERE asset_code = :c"),
                {"c": TEST_ASSET_CODE}
            ).mappings().fetchone()
        assert row is not None, "Quick Log should have created a draft"
        assert row["record_state"] == "Draft"
        assert row["service_type"] == "Preventive"
    finally:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
            conn.commit()


# ── tests: capture an issue and promote it to a draft through the UI ──────────────
def test_issue_capture_and_promote_via_ui(engine, test_asset):
    """Log an issue in the Issues inbox, then Promote it — a Corrective draft is
    created and the issue is marked Promoted."""
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM machine_issues  WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
        conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
        conn.commit()

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Issues"
    at.run()
    assert not at.exception

    _widget(at.selectbox, "Machine").set_value({"code": TEST_ASSET_CODE, "label": "Z999-TEST"})
    _widget(at.text_area, "What did you notice?").set_value("spindle grinding noise")
    _widget(at.button, "Log issue").click()
    at.run()
    assert not at.exception

    try:
        with engine.connect() as conn:
            issue = conn.execute(
                text("SELECT id, status FROM machine_issues WHERE asset_code = :c"),
                {"c": TEST_ASSET_CODE}
            ).mappings().fetchone()
        assert issue is not None and issue["status"] == "Open"

        _button_by_key(at, f"issue_promote_{issue['id']}").click()
        at.run()
        assert not at.exception

        with engine.connect() as conn:
            promoted = conn.execute(
                text("SELECT status, promoted_report_id FROM machine_issues WHERE id = :i"),
                {"i": issue["id"]}
            ).mappings().fetchone()
            draft = conn.execute(
                text("SELECT record_state, service_type FROM service_reports "
                     "WHERE asset_code = :c AND record_state = 'Draft'"),
                {"c": TEST_ASSET_CODE}
            ).mappings().fetchone()
        assert promoted["status"] == "Promoted"
        assert promoted["promoted_report_id"] is not None
        assert draft is not None and draft["service_type"] == "Corrective"
    finally:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM machine_issues  WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
            conn.execute(text("DELETE FROM service_reports WHERE asset_code = :c"), {"c": TEST_ASSET_CODE})
            conn.commit()


# ── tests: deleting a draft through the UI (with its confirm step) ────────────────
def test_delete_draft_via_ui(engine, ui_draft):
    at = _edit_app(ui_draft)
    _widget(at.button, "Delete Draft").click()
    at.run()                                          # reveals the confirm button
    _widget(at.button, "Delete Permanently").click()
    at.run()
    assert not at.exception

    with engine.connect() as conn:
        gone = conn.execute(
            text("SELECT 1 FROM service_reports WHERE report_id = :id"), {"id": ui_draft}
        ).fetchone()
    assert gone is None, "Draft should be deleted after confirming"
