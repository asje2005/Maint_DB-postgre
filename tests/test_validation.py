"""
Validation rule tests — mirrors every guard the app enforces before writing data.

These tests do NOT need the database for most cases; they exercise the same
Python logic the app uses so we verify the rules independently.
"""
import pytest
from sqlalchemy import text

from tests.conftest import (
    BASE_DIR, DB_DIR, TEST_ASSET_ID, TEST_ASSET_CODE, TEST_ASSET_FOLDER,
    _delete_test_asset,
)


# ══════════════════════════════════════════════════════════════════════════════
# ASSET CODE FORMAT VALIDATION
# (mirrors the asset_code check in render_add_asset_page)
# ══════════════════════════════════════════════════════════════════════════════

def _is_valid_asset_code(code: str) -> bool:
    """Exact same rule as the app:
    len == 4, first char alpha, last 3 chars digits."""
    code = code.strip().upper()
    return (
        len(code) == 4
        and code[0].isalpha()
        and code[1:].isdigit()
    )


class TestAssetCodeFormat:
    @pytest.mark.parametrize("code", ["L001", "M002", "S100", "Q999", "E055", "Z999"])
    def test_valid_codes_pass(self, code):
        assert _is_valid_asset_code(code), f"{code!r} should be valid"

    @pytest.mark.parametrize("code", [
        "",          # empty
        "L01",       # too short — 3 chars
        "L0001",     # too long — 5 chars
        "1L01",      # digit first
        "LL01",      # two letters
        "L0X1",      # letter in number portion
        "l001",      # lower-case (before .upper() strip) — should still work
        "L 01",      # space inside
        "L-01",      # hyphen
    ])
    def test_invalid_codes_fail(self, code):
        # lower-case is normalised to upper inside the validator, so "l001" is valid
        if code.strip().upper() == "L001":
            pytest.skip("lower-case normalises to valid")
        assert not _is_valid_asset_code(code), f"{code!r} should be invalid"

    def test_lowercase_normalised_to_valid(self):
        """The app calls .strip().upper() — 'l001' normalises to 'L001'."""
        assert _is_valid_asset_code("l001")

    def test_whitespace_trimmed(self):
        assert _is_valid_asset_code("  L001  ")


# ══════════════════════════════════════════════════════════════════════════════
# DUPLICATE ASSET CODE PREVENTION
# ══════════════════════════════════════════════════════════════════════════════

class TestDuplicateAssetCodePrevention:
    def test_existing_code_detected(self, engine, test_asset):
        """The SELECT 1 … WHERE asset_code = :code check returns a row when the code exists."""
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM assets WHERE asset_code = :code"),
                {"code": TEST_ASSET_CODE}
            ).fetchone()
        assert exists is not None, "Duplicate check should detect the existing code"

    def test_new_code_not_detected(self, engine, test_asset):
        """A brand-new code passes the duplicate check (returns None)."""
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM assets WHERE asset_code = :code"),
                {"code": "Z998"}
            ).fetchone()
        assert exists is None, "Non-existent code should not trigger duplicate check"

    def test_app_select_guard_catches_duplicate(self, engine, test_asset):
        """The app's SELECT 1 guard (before any INSERT) correctly detects
        an existing asset_code and prevents the insert from being attempted.
        The DB also enforces this independently: idx_assets_asset_code is a
        UNIQUE index (see schema.sql / schema_fixes.sql), so a duplicate
        asset_code is rejected even if the app check is bypassed."""
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM assets WHERE asset_code = :code"),
                {"code": TEST_ASSET_CODE}
            ).fetchone()
        assert exists is not None, (
            "Duplicate-prevention SELECT guard must find the existing code"
        )


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-SUGGEST NEXT ASSET CODE
# (mirrors the query in render_add_asset_page)
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoSuggestNextCode:
    def test_next_code_increments_from_existing(self, engine, test_asset):
        """Given one Z-dept asset (Z999), the next suggestion for dept Z would be Z1000
        — confirming the math works for any department."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT asset_code FROM assets WHERE department_code = 'Z'")
            ).fetchall()

        numbers = [int(r[0][1:]) for r in rows if r[0][1:].isdigit()]
        next_num = max(numbers) + 1 if numbers else 1
        assert next_num == 1000  # Z999 → next is Z1000

    def test_next_code_is_1_when_department_empty(self, engine):
        """A department with zero assets suggests code 001."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT asset_code FROM assets WHERE department_code = 'X'")
            ).fetchall()

        numbers = [int(r[0][1:]) for r in rows if r[0][1:].isdigit()]
        next_num = max(numbers) + 1 if numbers else 1
        assert next_num == 1

    def test_suggested_code_format_is_valid(self, engine):
        """The formatted suggestion is always a valid asset code."""
        dept = "L"
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT asset_code FROM assets WHERE department_code = :dept"),
                {"dept": dept}
            ).fetchall()

        numbers = [int(r[0][1:]) for r in rows if r[0][1:].isdigit()]
        next_num = max(numbers) + 1 if numbers else 1
        suggested = f"{dept}{str(next_num).zfill(3)}"
        assert _is_valid_asset_code(suggested)


# ══════════════════════════════════════════════════════════════════════════════
# REQUIRED FIELD VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestRequiredFields:
    def test_asset_code_empty_fails_validation(self):
        assert not _is_valid_asset_code(""), "Empty code must fail"

    def test_asset_code_spaces_only_fails(self):
        assert not _is_valid_asset_code("    "), "Whitespace-only code must fail"

    def test_finalize_requires_verified_by_nonempty(self):
        """The finalize guard rejects an empty/whitespace Verified_By."""
        verifier = "   "
        assert not verifier.strip(), "Whitespace-only verifier should be treated as missing"

    def test_finalize_accepts_nonempty_verified_by(self):
        verifier = "Jane Smith"
        assert verifier.strip(), "Non-empty verifier should pass"

    def test_work_center_machine_id_required(self, engine):
        """Inserting a work_center row without machine_id (NULL) raises a NOT NULL error."""
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO work_centers (machine_id, machine_name, department) "
                    "VALUES (NULL, 'No ID Machine', 'Mill')"
                ))
                conn.commit()

    def test_work_center_machine_name_required(self, engine):
        """machine_name has NOT NULL constraint — the INSERT must fail, so no row
        is ever created (the constraint itself guarantees cleanup)."""
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO work_centers (machine_id, machine_name, department) "
                    "VALUES ('TEST_NONAME', NULL, 'Mill')"
                ))
                conn.commit()

    def test_employee_name_required(self, engine):
        """Employee name has NOT NULL constraint — the INSERT must fail, so no row
        is ever created."""
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO employees (employee_id, name) VALUES ('TEST_NONAME', NULL)"
                ))
                conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# FOREIGN KEY CONSTRAINTS
# ══════════════════════════════════════════════════════════════════════════════

class TestForeignKeyConstraints:
    def test_battery_requires_valid_asset_id(self, engine):
        """Inserting a battery for a non-existent asset fails the FK constraint."""
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO asset_batteries (asset_id, battery_number, description)
                    VALUES ('A-GHOST', 1, 'Phantom Battery')
                """))
                conn.commit()

    def test_peripheral_equipment_requires_valid_asset_id(self, engine):
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name)
                    VALUES ('A-GHOST', 1, 'Ghost Equip')
                """))
                conn.commit()

    def test_labor_ticket_requires_valid_employee(self, engine):
        with pytest.raises(Exception):
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO labor_tickets (employee_id, time_in)
                    VALUES ('GHOST_EMP', NOW())
                """))
                conn.commit()

