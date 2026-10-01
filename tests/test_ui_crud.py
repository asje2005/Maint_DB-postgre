"""
UI tests for the create/insert forms on the Add Asset and Records Manager pages.

Like the other UI tests, these drive the real app via AppTest: fill the form,
click the submit button, and verify a row was written. All test rows use
clearly-fake identifiers and are cleaned up.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.conftest import TEST_ASSET_ID  # noqa: E402

APP_PATH = str(ROOT / "app.py")

# Uses a valid department letter (E) because the Add-Asset form now rejects codes
# outside the L/M/S/Q/E set; 998 keeps it clear of the real low-numbered assets.
NEW_ASSET_CODE = "E998"
NEW_ASSET_ID   = "A-E998"
NEW_WC_ID      = "TEST_WC_UI"


def _widget(seq, label):
    for w in seq:
        if w.label == label:
            return w
    raise AssertionError(f"widget {label!r} not found; have {[w.label for w in seq]}")


# ── Add Asset ────────────────────────────────────────────────────────────────────
@pytest.fixture
def cleanup_new_asset(engine):
    def _purge():
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM asset_peripheral_equipment WHERE asset_id = :id"), {"id": NEW_ASSET_ID})
            conn.execute(text("DELETE FROM asset_batteries            WHERE asset_id = :id"), {"id": NEW_ASSET_ID})
            conn.execute(text("DELETE FROM service_reports            WHERE asset_id = :id"), {"id": NEW_ASSET_ID})
            conn.execute(text("DELETE FROM assets                     WHERE asset_id = :id"), {"id": NEW_ASSET_ID})
            conn.commit()
    _purge()
    yield
    _purge()


def test_add_asset_via_ui(engine, cleanup_new_asset):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Add Asset"
    at.run()
    assert not at.exception

    _widget(at.text_input, "Asset Code").set_value(NEW_ASSET_CODE)
    _widget(at.selectbox, "Equipment Category").set_value("Mill")
    _widget(at.text_input, "Manufacturer").set_value("TestMfr")
    _widget(at.text_input, "Model Name/Number").set_value("TestModel")
    _widget(at.button, "Register Asset").click()
    at.run()
    assert not at.exception, f"{[repr(e.value) for e in at.exception]}"

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT asset_code, manufacturer, model, equipment_category
            FROM assets WHERE asset_id = :id
        """), {"id": NEW_ASSET_ID}).mappings().fetchone()
    assert row is not None, "Add Asset should have created the row"
    assert row["asset_code"]         == NEW_ASSET_CODE
    assert row["manufacturer"]       == "TestMfr"
    assert row["model"]              == "TestModel"
    assert row["equipment_category"] == "Mill"


def test_add_asset_rejects_bad_code(engine, cleanup_new_asset):
    """An invalid asset code must not create a row."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Add Asset"
    at.run()
    _widget(at.text_input, "Asset Code").set_value("BAD1")  # two letters, not letter+3 digits
    _widget(at.button, "Register Asset").click()
    at.run()
    assert not at.exception
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM assets WHERE asset_code = :c"), {"c": "BAD1"}
        ).scalar()
    assert count == 0


# ── Edit Asset (save an edit) ────────────────────────────────────────────────────
def test_edit_asset_save_via_ui(engine, test_asset):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Edit Asset"
    at.session_state["edit_asset_id"] = TEST_ASSET_ID
    at.run()
    assert not at.exception

    _widget(at.text_input, "Manufacturer").set_value("EditedMfr")
    _widget(at.text_input, "Display Name").set_value("Edited Name")
    _widget(at.button, "Save All Changes").click()
    at.run()
    assert not at.exception, f"{[repr(e.value) for e in at.exception]}"

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT manufacturer, display_name FROM assets WHERE asset_id = :id"),
            {"id": TEST_ASSET_ID}
        ).mappings().fetchone()
    assert row["manufacturer"]  == "EditedMfr"
    assert row["display_name"]  == "Edited Name"


def test_delete_asset_via_ui(engine, test_asset):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Edit Asset"
    at.session_state["edit_asset_id"] = TEST_ASSET_ID
    at.run()
    assert not at.exception

    _widget(at.button, "Delete Asset").click()
    at.run()                                            # reveals the confirm button
    _widget(at.button, "Yes, Delete Permanently").click()
    at.run()
    assert not at.exception, f"{[repr(e.value) for e in at.exception]}"

    with engine.connect() as conn:
        gone = conn.execute(
            text("SELECT 1 FROM assets WHERE asset_id = :id"), {"id": TEST_ASSET_ID}
        ).fetchone()
    assert gone is None, "Asset should be deleted after confirming"


# ── Asset Registry (View Assets lists the asset) ─────────────────────────────────
def test_view_assets_lists_asset(test_asset):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "View Assets"
    at.run()
    assert not at.exception
    keys = [b.key for b in at.button if b.key]
    assert any(TEST_ASSET_ID in k for k in keys), \
        f"Test asset {TEST_ASSET_ID} should appear with its row buttons; saw {keys[:8]}"


# ── Records Manager (add a work center) ──────────────────────────────────────────
def test_records_manager_add_work_center_via_ui(engine):
    def _purge():
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM labor_tickets WHERE machine_id = :m"), {"m": NEW_WC_ID})
            conn.execute(text("DELETE FROM work_centers  WHERE machine_id = :m"), {"m": NEW_WC_ID})
            conn.commit()
    _purge()

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Records Manager"
    at.run()
    assert not at.exception

    # The Work Centers tab is first; its add form holds the only Machine ID / Machine Name widgets.
    _widget(at.text_input, "Machine ID").set_value(NEW_WC_ID)
    _widget(at.text_input, "Machine Name").set_value("UI Test Machine")
    _widget(at.selectbox, "Department").set_value("Mill")
    _widget(at.button, "Add").click()
    at.run()
    assert not at.exception, f"{[repr(e.value) for e in at.exception]}"

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT machine_name, department FROM work_centers WHERE machine_id = :m"),
                {"m": NEW_WC_ID}
            ).mappings().fetchone()
        assert row is not None, "Records Manager should have inserted the work center"
        assert row["machine_name"] == "UI Test Machine"
        assert row["department"]   == "Mill"
    finally:
        _purge()
