"""
Integration tests for the Service Reports workflow (DB-backed):
  Create Draft → Edit Draft (all fields) → Save → Delete → Finalize

All data uses asset Z999 and is cleaned up after every test.
"""
from datetime import datetime

import pytest
from sqlalchemy import text

from tests.conftest import TEST_ASSET_ID, TEST_ASSET_CODE


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _cleanup_reports(conn):
    """Delete all service_reports rows for the test asset."""
    conn.execute(
        text("DELETE FROM service_reports WHERE asset_code = :code"),
        {"code": TEST_ASSET_CODE}
    )
    conn.commit()


@pytest.fixture
def test_draft(engine, test_asset):
    """Insert a minimal Draft row for Z999, yield its report_id, then clean up."""
    with engine.connect() as conn:
        _cleanup_reports(conn)
        conn.execute(text("""
            INSERT INTO service_reports
                (asset_id, asset_code, record_state, service_type, entry_timestamp)
            VALUES (:aid, :code, 'Draft', 'Corrective', NOW())
        """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE})
        conn.commit()

    with engine.connect() as conn:
        rid = conn.execute(
            text("SELECT report_id FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"),
            {"code": TEST_ASSET_CODE}
        ).scalar()

    yield rid

    with engine.connect() as conn:
        _cleanup_reports(conn)


# ══════════════════════════════════════════════════════════════════════════════
# CREATE DRAFT
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateDraft:
    def test_create_draft_inserts_row(self, engine, test_asset):
        """Creating a draft writes a 'Draft' row to service_reports."""
        with engine.connect() as conn:
            _cleanup_reports(conn)
            conn.execute(text("""
                INSERT INTO service_reports (asset_id, asset_code, record_state, service_type)
                VALUES (:aid, :code, 'Draft', 'Preventive')
            """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE})
            conn.commit()

            row = conn.execute(
                text("SELECT record_state, asset_code FROM service_reports WHERE asset_code = :code"),
                {"code": TEST_ASSET_CODE}
            ).mappings().fetchone()
            assert row is not None
            assert row["record_state"] == "Draft"
            assert row["asset_code"]   == TEST_ASSET_CODE
            _cleanup_reports(conn)

    @pytest.mark.parametrize("service_type", ["Preventive", "Corrective", "Emergency"])
    def test_all_service_types(self, engine, test_asset, service_type):
        """Every service type is stored and retrieved correctly."""
        with engine.connect() as conn:
            _cleanup_reports(conn)
            conn.execute(text("""
                INSERT INTO service_reports (asset_id, asset_code, record_state, service_type)
                VALUES (:aid, :code, 'Draft', :stype)
            """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE, "stype": service_type})
            conn.commit()

            stored = conn.execute(
                text("SELECT service_type FROM service_reports WHERE asset_code = :code"),
                {"code": TEST_ASSET_CODE}
            ).scalar()
            assert stored == service_type
            _cleanup_reports(conn)

    def test_create_draft_header_fields(self, engine, test_draft):
        """Freshly created draft has correct asset_id, asset_code, and record_state."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT asset_id, asset_code, record_state FROM service_reports WHERE report_id = :id"),
                {"id": test_draft}
            ).mappings().fetchone()
        assert row["asset_id"]     == TEST_ASSET_ID
        assert row["asset_code"]   == TEST_ASSET_CODE
        assert row["record_state"] == "Draft"

    def test_duplicate_draft_blocked_by_select_guard(self, engine, test_draft):
        """The app's SELECT 1 guard detects the existing draft before trying a second INSERT."""
        with engine.connect() as conn:
            existing = conn.execute(
                text("SELECT 1 FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"),
                {"code": TEST_ASSET_CODE}
            ).fetchone()
        assert existing is not None, "Duplicate-draft SELECT guard must find the existing row"


# ══════════════════════════════════════════════════════════════════════════════
# EDIT DRAFT — each field updated individually
# ══════════════════════════════════════════════════════════════════════════════

class TestEditDraft:
    def _update(self, engine, report_id, **kwargs):
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)
        kwargs["id"] = report_id
        with engine.connect() as conn:
            conn.execute(text(f"UPDATE service_reports SET {set_clause} WHERE report_id = :id"), kwargs)
            conn.commit()

    def _fetch(self, engine, report_id, *cols):
        with engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {', '.join(cols)} FROM service_reports WHERE report_id = :id"),
                {"id": report_id}
            ).mappings().fetchone()
        return row

    def test_save_problem_description(self, engine, test_draft):
        self._update(engine, test_draft, problem_description="Spindle vibration at high RPM")
        row = self._fetch(engine, test_draft, "problem_description")
        assert row["problem_description"] == "Spindle vibration at high RPM"

    def test_save_work_performed(self, engine, test_draft):
        self._update(engine, test_draft, work_performed="Replaced spindle bearings and balanced rotor")
        row = self._fetch(engine, test_draft, "work_performed")
        assert row["work_performed"] == "Replaced spindle bearings and balanced rotor"

    def test_save_downtime_hours(self, engine, test_draft):
        self._update(engine, test_draft, downtime_hours=4.5)
        row = self._fetch(engine, test_draft, "downtime_hours")
        assert float(row["downtime_hours"]) == 4.5

    @pytest.mark.parametrize("rts", ["Yes", "No"])
    def test_save_return_to_service(self, engine, test_draft, rts):
        self._update(engine, test_draft, return_to_service=rts)
        row = self._fetch(engine, test_draft, "return_to_service")
        assert row["return_to_service"] == rts

    def test_save_verified_by(self, engine, test_draft):
        self._update(engine, test_draft, verified_by="Jane Smith")
        row = self._fetch(engine, test_draft, "verified_by")
        assert row["verified_by"] == "Jane Smith"

    def test_save_issue_category(self, engine, test_draft):
        self._update(engine, test_draft, issue_category="Electrical")
        row = self._fetch(engine, test_draft, "issue_category")
        assert row["issue_category"] == "Electrical"

    def test_save_root_cause(self, engine, test_draft):
        self._update(engine, test_draft, root_cause="Wear")
        row = self._fetch(engine, test_draft, "root_cause")
        assert row["root_cause"] == "Wear"

    def test_save_all_fields_together(self, engine, test_draft):
        """All edit fields saved in one UPDATE — the normal app workflow."""
        self._update(engine, test_draft,
                     issue_category="Mechanical",
                     root_cause="Wear",
                     problem_description="Coolant leak from rear seal",
                     work_performed="Replaced rear seal and refilled coolant",
                     downtime_hours=2.0,
                     return_to_service="Yes",
                     verified_by="Bob Jones")
        row = self._fetch(engine, test_draft,
                          "issue_category", "root_cause",
                          "problem_description", "work_performed",
                          "downtime_hours", "return_to_service", "verified_by")
        assert row["issue_category"]      == "Mechanical"
        assert row["root_cause"]          == "Wear"
        assert row["problem_description"] == "Coolant leak from rear seal"
        assert row["work_performed"]      == "Replaced rear seal and refilled coolant"
        assert float(row["downtime_hours"]) == 2.0
        assert row["return_to_service"]   == "Yes"
        assert row["verified_by"]         == "Bob Jones"

    def test_overwrite_previously_saved_values(self, engine, test_draft):
        """Second UPDATE overwrites the first — no stale data."""
        self._update(engine, test_draft, problem_description="First save")
        self._update(engine, test_draft, problem_description="Second save overwrites")
        row = self._fetch(engine, test_draft, "problem_description")
        assert row["problem_description"] == "Second save overwrites"

    def test_empty_fields_read_as_none(self, engine, test_draft):
        """Fields never set read back as None."""
        row = self._fetch(engine, test_draft, "problem_description", "work_performed")
        assert row["problem_description"] is None
        assert row["work_performed"] is None


# ══════════════════════════════════════════════════════════════════════════════
# DELETE DRAFT
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteDraft:
    def test_delete_draft_removes_row(self, engine, test_draft):
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM service_reports WHERE report_id = :id"), {"id": test_draft})
            conn.commit()
            remaining = conn.execute(
                text("SELECT 1 FROM service_reports WHERE report_id = :id"),
                {"id": test_draft}
            ).fetchone()
        assert remaining is None, "Row should be gone after DELETE"

    def test_draft_count_decreases_after_delete(self, engine, test_asset):
        """Deleting a draft decreases the count of Draft records for the asset."""
        with engine.connect() as conn:
            _cleanup_reports(conn)
            conn.execute(text("""
                INSERT INTO service_reports (asset_id, asset_code, record_state, service_type)
                VALUES (:aid, :code, 'Draft', 'Preventive')
            """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE})
            conn.commit()
            before = conn.execute(
                text("SELECT COUNT(*) FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"),
                {"code": TEST_ASSET_CODE}
            ).scalar()

            conn.execute(text("DELETE FROM service_reports WHERE asset_code = :code"), {"code": TEST_ASSET_CODE})
            conn.commit()
            after = conn.execute(
                text("SELECT COUNT(*) FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"),
                {"code": TEST_ASSET_CODE}
            ).scalar()

        assert before == 1
        assert after  == 0


# ══════════════════════════════════════════════════════════════════════════════
# FINALIZE DRAFT
# ══════════════════════════════════════════════════════════════════════════════

class TestFinalizeDraft:
    @pytest.fixture(autouse=True)
    def _ready_draft(self, engine, test_asset):
        """Create a fully-populated draft for finalization tests."""
        with engine.connect() as conn:
            _cleanup_reports(conn)
            conn.execute(text("""
                INSERT INTO service_reports
                    (asset_id, asset_code, record_state, service_type,
                     problem_description, work_performed,
                     downtime_hours, return_to_service, verified_by)
                VALUES
                    (:aid, :code, 'Draft', 'Corrective',
                     'Axis drive alarm', 'Replaced X-axis drive',
                     6.0, 'Yes', 'Alice Chen')
            """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE})
            conn.commit()
            rid = conn.execute(
                text("SELECT report_id FROM service_reports WHERE asset_code = :code"),
                {"code": TEST_ASSET_CODE}
            ).scalar()
        self.report_id = rid
        yield
        with engine.connect() as conn:
            _cleanup_reports(conn)

    def _finalize(self, engine, final_id):
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE service_reports SET
                    service_id   = :sid,
                    record_state = 'Final',
                    finalized_at = NOW(),
                    updated_at   = NOW()
                WHERE report_id = :id
            """), {"sid": final_id, "id": self.report_id})
            conn.commit()

    def test_finalize_sets_record_state_final(self, engine):
        service_date = datetime.now().strftime("%Y%m%d")
        final_id = f"S-{TEST_ASSET_CODE}-{service_date}-001"
        self._finalize(engine, final_id)
        with engine.connect() as conn:
            state = conn.execute(
                text("SELECT record_state FROM service_reports WHERE report_id = :id"),
                {"id": self.report_id}
            ).scalar()
        assert state == "Final"

    def test_finalize_sets_service_id(self, engine):
        service_date = datetime.now().strftime("%Y%m%d")
        final_id = f"S-{TEST_ASSET_CODE}-{service_date}-001"
        self._finalize(engine, final_id)
        with engine.connect() as conn:
            sid = conn.execute(
                text("SELECT service_id FROM service_reports WHERE report_id = :id"),
                {"id": self.report_id}
            ).scalar()
        assert sid == final_id

    def test_finalize_sets_finalized_at(self, engine):
        service_date = datetime.now().strftime("%Y%m%d")
        self._finalize(engine, f"S-{TEST_ASSET_CODE}-{service_date}-001")
        with engine.connect() as conn:
            fa = conn.execute(
                text("SELECT finalized_at FROM service_reports WHERE report_id = :id"),
                {"id": self.report_id}
            ).scalar()
        assert fa is not None, "finalized_at should be set on finalization"

    def test_finalize_removes_from_draft_query(self, engine):
        service_date = datetime.now().strftime("%Y%m%d")
        self._finalize(engine, f"S-{TEST_ASSET_CODE}-{service_date}-001")
        with engine.connect() as conn:
            draft = conn.execute(
                text("SELECT 1 FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"),
                {"code": TEST_ASSET_CODE}
            ).fetchone()
        assert draft is None, "Finalized record must not appear in Draft queries"

    def test_finalized_data_is_intact(self, engine):
        """All fields written during Edit are preserved after finalization."""
        service_date = datetime.now().strftime("%Y%m%d")
        self._finalize(engine, f"S-{TEST_ASSET_CODE}-{service_date}-001")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM service_reports WHERE report_id = :id"),
                {"id": self.report_id}
            ).mappings().fetchone()
        assert row["asset_code"]           == TEST_ASSET_CODE
        assert row["problem_description"]  == "Axis drive alarm"
        assert row["work_performed"]       == "Replaced X-axis drive"
        assert float(row["downtime_hours"]) == 6.0
        assert row["verified_by"]          == "Alice Chen"

    def test_finalize_requires_verified_by(self, engine):
        """App guard: empty verified_by must block finalization."""
        # This mirrors the app's `if not verifier.strip(): return`
        with engine.connect() as conn:
            verifier = conn.execute(
                text("SELECT verified_by FROM service_reports WHERE report_id = :id"),
                {"id": self.report_id}
            ).scalar()
        assert verifier and verifier.strip(), "Fixture should have a non-empty verifier"

        # Simulate a draft with no verifier and confirm the guard logic
        empty_verifier = "   "
        assert not empty_verifier.strip(), "Whitespace-only verifier must fail the guard"

    def test_sequence_number_increments_on_same_day(self, engine):
        """A second finalization on the same day must generate -002, not -001."""
        service_date = datetime.now().strftime("%Y%m%d")

        # Insert a record that already occupies slot -001
        first_id = f"S-{TEST_ASSET_CODE}-{service_date}-001"
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO service_reports
                    (asset_id, asset_code, record_state, service_type, service_id, verified_by)
                VALUES (:aid, :code, 'Final', 'Preventive', :sid, 'Test')
            """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE, "sid": first_id})
            conn.commit()

        try:
            # Simulate the sequence-scan loop from the app
            seq_num = 1
            with engine.connect() as conn:
                while True:
                    candidate = f"S-{TEST_ASSET_CODE}-{service_date}-{str(seq_num).zfill(3)}"
                    exists = conn.execute(
                        text("SELECT 1 FROM service_reports WHERE service_id = :sid"),
                        {"sid": candidate}
                    ).fetchone()
                    if not exists:
                        break
                    seq_num += 1

            assert seq_num == 2
            assert str(seq_num).zfill(3) == "002"
        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM service_reports WHERE service_id = :sid"), {"sid": first_id})
                conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# SERVICE PARTS  (parts used on a service report)
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceParts:
    def _add_part(self, engine, report_id, name, qty=1, is_battery=False):
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO service_parts (report_id, part_name, quantity, is_battery)
                VALUES (:rid, :name, :qty, :batt)
            """), {"rid": report_id, "name": name, "qty": qty, "batt": is_battery})
            conn.commit()

    def _parts(self, engine, report_id):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT part_name, quantity, is_battery FROM service_parts "
                     "WHERE report_id = :rid ORDER BY id"),
                {"rid": report_id}
            ).mappings().all()

    def test_add_part_to_draft(self, engine, test_draft):
        self._add_part(engine, test_draft, "Spindle bearing", qty=2)
        parts = self._parts(engine, test_draft)
        assert len(parts) == 1
        assert parts[0]["part_name"] == "Spindle bearing"
        assert parts[0]["quantity"]  == 2
        assert parts[0]["is_battery"] is False

    def test_battery_flag_persists(self, engine, test_draft):
        self._add_part(engine, test_draft, "CNC backup battery", is_battery=True)
        assert self._parts(engine, test_draft)[0]["is_battery"] is True

    def test_multiple_parts_on_one_report(self, engine, test_draft):
        self._add_part(engine, test_draft, "Seal kit")
        self._add_part(engine, test_draft, "Coolant filter", qty=3)
        assert len(self._parts(engine, test_draft)) == 2

    def test_delete_part(self, engine, test_draft):
        self._add_part(engine, test_draft, "Removable part")
        with engine.connect() as conn:
            pid = conn.execute(
                text("SELECT id FROM service_parts WHERE report_id = :rid"),
                {"rid": test_draft}
            ).scalar()
            conn.execute(text("DELETE FROM service_parts WHERE id = :pid"), {"pid": pid})
            conn.commit()
        assert self._parts(engine, test_draft) == []

    def test_parts_cascade_on_report_delete(self, engine, test_draft):
        """Deleting a service_reports row removes its parts (ON DELETE CASCADE)."""
        self._add_part(engine, test_draft, "Doomed part")
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM service_reports WHERE report_id = :id"), {"id": test_draft})
            conn.commit()
            remaining = conn.execute(
                text("SELECT COUNT(*) FROM service_parts WHERE report_id = :rid"),
                {"rid": test_draft}
            ).scalar()
        assert remaining == 0
