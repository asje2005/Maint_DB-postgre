"""
Smoke tests: every page of the app renders through AppTest without raising.

These don't assert detailed behaviour — they catch the class of bug where a
render_* function crashes (bad query, renamed column, missing session key) the
moment its page is opened. They run against the live dev database.
"""
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.conftest import TEST_ASSET_ID  # noqa: E402

APP_PATH = str(ROOT / "app.py")

# session_state["page"] values handled by the bottom router in app.py
NAV_PAGES = [
    "Home",
    "Add Asset",
    "View Assets",
    "Service Reports",
    "PM Schedule",
    "ERP Dashboard",
    "Reporting",
    "Settings",
    "Records Manager",
]


@pytest.mark.parametrize("page", NAV_PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, f"{page} raised: {[repr(e.value) for e in at.exception]}"


def test_today_cockpit_renders():
    """The Today cockpit composes attention counts + floor board + drafts; this
    catches a crash in any of the shared query helpers it depends on."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Home"
    at.run()
    assert not at.exception, f"Today raised: {[repr(e.value) for e in at.exception]}"


def test_service_quick_log_default_renders():
    """Service Reports now defaults to the Quick Log tab — make sure it renders."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.run()
    assert not at.exception, f"Quick Log raised: {[repr(e.value) for e in at.exception]}"


def test_service_fix_history_renders():
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Service Reports"
    at.session_state["service_page"] = "Fix History"
    at.run()
    assert not at.exception, f"Fix History raised: {[repr(e.value) for e in at.exception]}"


def test_edit_asset_page_renders(test_asset):
    """Edit Asset needs a selected asset_id in session_state."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = "Edit Asset"
    at.session_state["edit_asset_id"] = TEST_ASSET_ID
    at.run()
    assert not at.exception, f"Edit Asset raised: {[repr(e.value) for e in at.exception]}"


def test_reporting_suite_renders_all_tabs():
    """The Reporting page renders all four tabs in one pass (AppTest executes every
    tab body): Production + Asset use live data, Maintenance shows its empty-state
    while service_reports is unpopulated, and Export builds the multi-sheet .xlsx
    workbook in-process — so any SQL, charting, or openpyxl regression trips
    at.exception here."""
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["page"] = "Reporting"
    at.run()
    assert not at.exception, f"Reporting raised: {[repr(e.value) for e in at.exception]}"

    blob = " ".join(m.value for m in at.markdown)
    # Page title rendered.
    assert "Analytics Suite" in blob
    # Production KPI present (proves the op-30 quality query ran and rendered).
    assert "First-Pass Yield" in blob
    # Maintenance empty-state path fired (service_reports has no Final rows yet).
    assert "No finalized service reports yet" in blob
    # Asset-registry data-quality centerpiece rendered (callout is a markdown card).
    assert "Preventive-maintenance intervals not configured" in blob
    # Export tab's workbook-contents card renders only after _build_full_report()
    # has assembled the .xlsx in-process, so this confirms the openpyxl path ran.
    assert "Workbook contents" in blob
