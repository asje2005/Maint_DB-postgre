"""
CRUD integration tests for the assets, asset_batteries, and
asset_peripheral_equipment tables — covering every form field.
"""
import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import (
    BASE_DIR, DB_DIR, TEST_ASSET_ID, TEST_ASSET_CODE, TEST_ASSET_FOLDER,
    _delete_test_asset,
)

DEPARTMENTS = ["L", "M", "S", "Q", "E"]
CATEGORIES  = ["Lathe", "Mill", "Swiss", "QC", "Support", "Other"]
STATUSES    = ["Active", "Inactive", "Under Repair", "Decommissioned"]


# ══════════════════════════════════════════════════════════════════════════════
# CREATE — every column in the assets table
# ══════════════════════════════════════════════════════════════════════════════

class TestAssetCreate:
    def test_create_asset_all_fields(self, engine):
        """Every column the Add Asset & Edit Asset forms can populate is written
        and read back correctly."""
        folder = TEST_ASSET_FOLDER
        folder.mkdir(parents=True, exist_ok=True)

        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO assets (
                        asset_id, asset_code, department_code, sequence_number,
                        display_name, short_name, equipment_category,
                        primary_function, manufacturer, model, serial_number,
                        control_type, build_year,
                        distributor, distributor_email, distributor_phone,
                        vendor_contacts, facility, area_cell,
                        commission_date, asset_status,
                        planned_pm_interval_days,
                        installation_notes, known_quirks,
                        special_tooling, reference_document,
                        template_version, registry_creation_date, folder_path
                    ) VALUES (
                        :aid, :code, 'Z', '999',
                        'Z999-FullTest', 'Z999-FullTest', 'Lathe',
                        'Machining', 'Haas', 'TL-1', 'SN-FULL-001',
                        'Haas CNC', 2022,
                        'Haas Automation', 'service@haas.com', '800-331-6746',
                        'Contact John at ext 42', 'Building A', 'Cell 3',
                        '2022-01-15', 'Active',
                        180,
                        'Level floor required', 'Spindle chatter above 8000 RPM',
                        'ER32 collet chuck', 'Manual_TL1_Rev3.pdf',
                        '1.0', NOW(), :fp
                    )
                """), {"aid": TEST_ASSET_ID, "code": TEST_ASSET_CODE, "fp": str(folder)})
                conn.commit()

            # Read back every field
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT * FROM assets WHERE asset_id = :id"),
                    {"id": TEST_ASSET_ID}
                ).mappings().fetchone()

            assert row is not None
            assert row["asset_code"]               == "Z999"
            assert row["department_code"]          == "Z"
            assert row["sequence_number"]          == "999"
            assert row["display_name"]             == "Z999-FullTest"
            assert row["short_name"]               == "Z999-FullTest"
            assert row["equipment_category"]       == "Lathe"
            assert row["primary_function"]         == "Machining"
            assert row["manufacturer"]             == "Haas"
            assert row["model"]                    == "TL-1"
            assert row["serial_number"]            == "SN-FULL-001"
            assert row["control_type"]             == "Haas CNC"
            assert row["build_year"]               == 2022
            assert row["distributor"]              == "Haas Automation"
            assert row["distributor_email"]        == "service@haas.com"
            assert row["distributor_phone"]        == "800-331-6746"
            assert row["vendor_contacts"]          == "Contact John at ext 42"
            assert row["facility"]                 == "Building A"
            assert row["area_cell"]                == "Cell 3"
            assert row["commission_date"]          == date(2022, 1, 15)
            assert row["asset_status"]             == "Active"
            assert row["planned_pm_interval_days"] == 180
            assert row["installation_notes"]       == "Level floor required"
            assert row["known_quirks"]             == "Spindle chatter above 8000 RPM"
            assert row["special_tooling"]          == "ER32 collet chuck"
            assert row["reference_document"]       == "Manual_TL1_Rev3.pdf"
            assert row["template_version"]         == "1.0"
            assert row["folder_path"] == str(folder)

        finally:
            with engine.connect() as conn:
                _delete_test_asset(conn)
                conn.commit()
            if folder.exists():
                shutil.rmtree(folder)

    def test_create_asset_duplicate_code_blocked_via_app_check(self, engine, test_asset):
        """The app guards duplicates with a SELECT 1 check before INSERT.
        This test verifies that check returns a row when the code already exists,
        which causes the app to abort and show an error rather than inserting.
        The DB-level UNIQUE index idx_assets_asset_code (schema.sql /
        schema_fixes.sql) backs this up as a second line of defence."""
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM assets WHERE asset_code = :code"),
                {"code": TEST_ASSET_CODE}
            ).fetchone()
        assert exists is not None, "App duplicate-check SELECT should detect Z999"

    @pytest.mark.parametrize("dept", DEPARTMENTS)
    def test_all_department_codes_accepted(self, engine, dept):
        """Each valid department letter can be stored and retrieved."""
        aid  = f"A-{dept}998"
        code = f"{dept}998"
        folder = DB_DIR / f"A-{code}-TEST"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO assets (asset_id, asset_code, department_code, sequence_number,
                                       display_name, short_name, equipment_category,
                                       template_version, registry_creation_date, folder_path)
                    VALUES (:aid, :code, :dept, '998', :code, :code, 'Other',
                            '1.0', NOW(), :fp)
                """), {"aid": aid, "code": code, "dept": dept, "fp": str(folder)})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT department_code FROM assets WHERE asset_id = :id"),
                    {"id": aid}
                ).fetchone()
            assert row[0] == dept

        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM assets WHERE asset_id = :id"), {"id": aid})
                conn.commit()
            if folder.exists():
                shutil.rmtree(folder)

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_all_equipment_categories_accepted(self, engine, category):
        """Every equipment category option can be stored and retrieved."""
        aid  = "A-Z997"
        code = "Z997"
        folder = DB_DIR / "A-Z997-CAT-TEST"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO assets (asset_id, asset_code, department_code, sequence_number,
                                       display_name, short_name, equipment_category,
                                       template_version, registry_creation_date, folder_path)
                    VALUES (:aid, :code, 'Z', '997', :code, :code, :cat,
                            '1.0', NOW(), :fp)
                """), {"aid": aid, "code": code, "cat": category, "fp": str(folder)})
                conn.commit()

            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT equipment_category FROM assets WHERE asset_id = :id"),
                    {"id": aid}
                ).fetchone()
            assert row[0] == category

        finally:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM assets WHERE asset_id = :id"), {"id": aid})
                conn.commit()
            if folder.exists():
                shutil.rmtree(folder)


# ══════════════════════════════════════════════════════════════════════════════
# READ
# ══════════════════════════════════════════════════════════════════════════════

class TestAssetRead:
    def test_read_asset_exists(self, engine, test_asset):
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT asset_id, asset_code, manufacturer FROM assets WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchone()
        assert row is not None
        assert row[0] == TEST_ASSET_ID
        assert row[1] == TEST_ASSET_CODE
        assert row[2] == "TestMfr"

    def test_read_nonexistent_asset_returns_none(self, engine):
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM assets WHERE asset_id = 'A-DOESNOTEXIST'")
            ).fetchone()
        assert row is None

    def test_asset_list_query_returns_rows(self, engine, test_asset):
        """The main registry query (as used by render_view_assets_page) returns results."""
        import pandas as pd
        df = pd.read_sql_query("""
            SELECT a.asset_id, a.asset_code, a.manufacturer, a.model, a.serial_number,
                   a.equipment_category, a.build_year, a.control_type, a.distributor,
                   a.distributor_email, a.distributor_phone, a.vendor_contacts, a.folder_path,
                   b.description          AS battery_1_desc,
                   b.replacement_interval_days AS battery_1_interval,
                   (SELECT COUNT(*) FROM asset_peripheral_equipment p WHERE p.asset_id = a.asset_id) AS eq_count
            FROM assets a
            LEFT JOIN asset_batteries b ON a.asset_id = b.asset_id AND b.battery_number = 1
            ORDER BY a.asset_id
        """, engine)
        assert not df.empty
        assert TEST_ASSET_ID in df["asset_id"].values

    def test_search_by_manufacturer(self, engine, test_asset):
        """Filtering by manufacturer text in the registry search works."""
        # Use %% to escape literal % from psycopg2's parameter-placeholder parser
        import pandas as pd
        df = pd.read_sql_query(
            "SELECT asset_id FROM assets WHERE manufacturer ILIKE '%%TestMfr%%'", engine
        )
        assert TEST_ASSET_ID in df["asset_id"].values

    def test_search_by_serial_number(self, engine, test_asset):
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT asset_id FROM assets WHERE serial_number = 'SN-TEST-001'")
            ).fetchone()
        assert row is not None
        assert row[0] == TEST_ASSET_ID

    def test_category_filter_query(self, engine, test_asset):
        """Category = 'Other' returns the test asset."""
        import pandas as pd
        df = pd.read_sql_query(
            "SELECT asset_id FROM assets WHERE equipment_category = 'Other'", engine
        )
        assert TEST_ASSET_ID in df["asset_id"].values


# ══════════════════════════════════════════════════════════════════════════════
# UPDATE (Edit Asset page — all form fields)
# ══════════════════════════════════════════════════════════════════════════════

class TestAssetUpdate:
    def test_update_all_editable_fields(self, engine, test_asset):
        """Every field the Edit Asset form can change is verified after save."""
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE assets SET
                    display_name             = 'Z999-Updated',
                    short_name               = 'Z999-Updated',
                    equipment_category       = 'Mill',
                    primary_function         = 'Milling',
                    asset_status             = 'Under Repair',
                    facility                 = 'Building B',
                    area_cell                = 'Cell 7',
                    commission_date          = '2023-06-01',
                    planned_pm_interval_days = 90,
                    manufacturer             = 'Haas Updated',
                    model                    = 'VF-2',
                    serial_number            = 'SN-UPDATED-999',
                    control_type             = 'Haas NGC',
                    build_year               = 2023,
                    distributor              = 'Updated Dist',
                    distributor_email        = 'updated@dist.com',
                    distributor_phone        = '800-000-0001',
                    vendor_contacts          = 'Updated vendor notes',
                    installation_notes       = 'Requires 3-phase 480V',
                    known_quirks             = 'Home switch sticks occasionally',
                    special_tooling          = 'HSK63A spindle',
                    reference_document       = 'VF2_Service_Manual.pdf'
                WHERE asset_id = :id
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM assets WHERE asset_id = :id"),
                {"id": test_asset}
            ).mappings().fetchone()

        assert row["display_name"]             == "Z999-Updated"
        assert row["equipment_category"]       == "Mill"
        assert row["primary_function"]         == "Milling"
        assert row["asset_status"]             == "Under Repair"
        assert row["facility"]                 == "Building B"
        assert row["area_cell"]                == "Cell 7"
        assert row["commission_date"]          == date(2023, 6, 1)
        assert row["planned_pm_interval_days"] == 90
        assert row["manufacturer"]             == "Haas Updated"
        assert row["model"]                    == "VF-2"
        assert row["serial_number"]            == "SN-UPDATED-999"
        assert row["control_type"]             == "Haas NGC"
        assert row["build_year"]               == 2023
        assert row["distributor"]              == "Updated Dist"
        assert row["distributor_email"]        == "updated@dist.com"
        assert row["distributor_phone"]        == "800-000-0001"
        assert row["vendor_contacts"]          == "Updated vendor notes"
        assert row["installation_notes"]       == "Requires 3-phase 480V"
        assert row["known_quirks"]             == "Home switch sticks occasionally"
        assert row["special_tooling"]          == "HSK63A spindle"
        assert row["reference_document"]       == "VF2_Service_Manual.pdf"

    @pytest.mark.parametrize("status", STATUSES)
    def test_all_asset_statuses_accepted(self, engine, test_asset, status):
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE assets SET asset_status = :s WHERE asset_id = :id"),
                {"s": status, "id": test_asset}
            )
            conn.commit()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT asset_status FROM assets WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchone()
        assert row[0] == status

    def test_null_optional_fields_accepted(self, engine, test_asset):
        """Optional fields can be set to NULL without error."""
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE assets SET
                    primary_function = NULL, facility = NULL, area_cell = NULL,
                    commission_date  = NULL, planned_pm_interval_days = NULL,
                    installation_notes = NULL, known_quirks = NULL,
                    special_tooling = NULL, reference_document = NULL
                WHERE asset_id = :id
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT primary_function, facility FROM assets WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchone()
        assert row[0] is None
        assert row[1] is None


# ══════════════════════════════════════════════════════════════════════════════
# DELETE
# ══════════════════════════════════════════════════════════════════════════════

class TestAssetDelete:
    def test_delete_asset_removes_row(self, engine, test_asset):
        with engine.connect() as conn:
            _delete_test_asset(conn)
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM assets WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchone()
        assert row is None

        if TEST_ASSET_FOLDER.exists():
            shutil.rmtree(TEST_ASSET_FOLDER)

    def test_delete_asset_cascades_batteries(self, engine, test_asset):
        """After deleting an asset, its battery rows are gone too."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_batteries (asset_id, battery_number, description, part_number, replacement_interval_days)
                VALUES (:id, 1, 'CNC Memory Backup', 'CR2032', 365)
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            _delete_test_asset(conn)
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM asset_batteries WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchone()
        assert row is None

        if TEST_ASSET_FOLDER.exists():
            shutil.rmtree(TEST_ASSET_FOLDER)

    def test_delete_asset_cascades_peripheral_equipment(self, engine, test_asset):
        """After deleting an asset, its peripheral equipment rows are gone too."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name, make, model, serial_number)
                VALUES (:id, 1, 'Parts Catcher', 'Hydrafeed', 'PC-100', 'PC-SN-001')
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            _delete_test_asset(conn)
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM asset_peripheral_equipment WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchone()
        assert row is None

        if TEST_ASSET_FOLDER.exists():
            shutil.rmtree(TEST_ASSET_FOLDER)


# ══════════════════════════════════════════════════════════════════════════════
# BATTERIES — all fields (Battery Configuration expander)
# ══════════════════════════════════════════════════════════════════════════════

class TestAssetBatteries:
    def test_create_two_batteries_all_fields(self, engine, test_asset):
        """Both battery slots (1 & 2) with all fields are stored and retrieved."""
        with engine.connect() as conn:
            for n, desc, part, interval in [
                (1, "CNC Memory Backup", "CR2032",   365),
                (2, "Drive Encoder Backup", "ER6C",  730),
            ]:
                conn.execute(text("""
                    INSERT INTO asset_batteries
                        (asset_id, battery_number, description, part_number, replacement_interval_days)
                    VALUES (:aid, :n, :desc, :part, :interval)
                """), {"aid": test_asset, "n": n, "desc": desc, "part": part, "interval": interval})
            conn.commit()

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM asset_batteries WHERE asset_id = :id ORDER BY battery_number"),
                {"id": test_asset}
            ).mappings().fetchall()

        assert len(rows) == 2
        assert rows[0]["battery_number"]              == 1
        assert rows[0]["description"]                 == "CNC Memory Backup"
        assert rows[0]["part_number"]                 == "CR2032"
        assert rows[0]["replacement_interval_days"]   == 365
        assert rows[1]["battery_number"]              == 2
        assert rows[1]["description"]                 == "Drive Encoder Backup"
        assert rows[1]["replacement_interval_days"]   == 730

    def test_update_battery_interval(self, engine, test_asset):
        """Changing the replacement interval is reflected correctly."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_batteries (asset_id, battery_number, description, part_number, replacement_interval_days)
                VALUES (:id, 1, 'Test Battery', 'CR2032', 365)
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE asset_batteries SET replacement_interval_days = 180
                WHERE asset_id = :id AND battery_number = 1
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT replacement_interval_days FROM asset_batteries WHERE asset_id = :id AND battery_number = 1"),
                {"id": test_asset}
            ).fetchone()
        assert row[0] == 180

    def test_delete_and_reinsert_batteries(self, engine, test_asset):
        """Edit Asset page's delete-all-then-reinsert pattern works correctly."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_batteries (asset_id, battery_number, description, part_number, replacement_interval_days)
                VALUES (:id, 1, 'Old Battery', 'AAA', 365)
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM asset_batteries WHERE asset_id = :id"), {"id": test_asset})
            conn.execute(text("""
                INSERT INTO asset_batteries (asset_id, battery_number, description, part_number, replacement_interval_days)
                VALUES (:id, 1, 'New Battery', 'CR2032', 180)
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM asset_batteries WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchall()
        assert len(rows) == 1
        assert rows[0][3] == "New Battery"

    def test_zero_interval_battery_stored(self, engine, test_asset):
        """An interval of 0 (not tracked) is stored without error."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_batteries (asset_id, battery_number, description, part_number, replacement_interval_days)
                VALUES (:id, 2, 'Untracked Battery', 'N/A', 0)
            """), {"id": test_asset})
            conn.commit()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT replacement_interval_days FROM asset_batteries WHERE asset_id = :id AND battery_number = 2"),
                {"id": test_asset}
            ).fetchone()
        assert row[0] == 0


# ══════════════════════════════════════════════════════════════════════════════
# PERIPHERAL EQUIPMENT — all fields (Sub-Equipment expander)
# ══════════════════════════════════════════════════════════════════════════════

class TestAssetPeripheralEquipment:
    def test_create_three_equipment_all_fields(self, engine, test_asset):
        """All three sub-equipment slots with all fields are stored and retrieved."""
        equipment = [
            (1, "Parts Catcher",     "Hydrafeed", "PC-100",  "PC-SN-001"),
            (2, "Bar Feeder",        "LNS",       "Turbo 65", "BF-SN-002"),
            (3, "Chip Conveyor",     "Hennig",    "CC-500",  "CC-SN-003"),
        ]
        with engine.connect() as conn:
            for n, name, make, model, serial in equipment:
                conn.execute(text("""
                    INSERT INTO asset_peripheral_equipment
                        (asset_id, equip_number, name, make, model, serial_number)
                    VALUES (:aid, :n, :name, :make, :model, :serial)
                """), {"aid": test_asset, "n": n, "name": name, "make": make,
                       "model": model, "serial": serial})
            conn.commit()

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM asset_peripheral_equipment WHERE asset_id = :id ORDER BY equip_number"),
                {"id": test_asset}
            ).mappings().fetchall()

        assert len(rows) == 3
        assert rows[0]["name"]          == "Parts Catcher"
        assert rows[0]["make"]          == "Hydrafeed"
        assert rows[0]["model"]         == "PC-100"
        assert rows[0]["serial_number"] == "PC-SN-001"
        assert rows[1]["name"]          == "Bar Feeder"
        assert rows[2]["name"]          == "Chip Conveyor"

    def test_update_equipment_name_and_serial(self, engine, test_asset):
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name, make, model, serial_number)
                VALUES (:id, 1, 'Old Name', 'OldMake', 'OldModel', 'OLD-SN')
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE asset_peripheral_equipment
                SET name = 'New Name', serial_number = 'NEW-SN'
                WHERE asset_id = :id AND equip_number = 1
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, serial_number FROM asset_peripheral_equipment WHERE asset_id = :id AND equip_number = 1"),
                {"id": test_asset}
            ).fetchone()
        assert row[0] == "New Name"
        assert row[1] == "NEW-SN"

    def test_partial_equipment_fields_allowed(self, engine, test_asset):
        """Name-only sub-equipment (no make/model/serial) is valid."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name, make, model, serial_number)
                VALUES (:id, 1, 'Probe System', NULL, NULL, NULL)
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, make FROM asset_peripheral_equipment WHERE asset_id = :id AND equip_number = 1"),
                {"id": test_asset}
            ).fetchone()
        assert row[0] == "Probe System"
        assert row[1] is None

    def test_delete_and_reinsert_equipment(self, engine, test_asset):
        """Edit Asset page's delete-all-then-reinsert pattern for equipment."""
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name)
                VALUES (:id, 1, 'Old Equip')
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM asset_peripheral_equipment WHERE asset_id = :id"), {"id": test_asset})
            conn.execute(text("""
                INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name, make, model, serial_number)
                VALUES (:id, 1, 'New Equip', 'NewMake', 'NewModel', 'NEW-001')
            """), {"id": test_asset})
            conn.commit()

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name FROM asset_peripheral_equipment WHERE asset_id = :id"),
                {"id": test_asset}
            ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "New Equip"
