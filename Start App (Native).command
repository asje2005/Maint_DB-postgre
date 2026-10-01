#!/bin/bash
#
# Native launcher for the Manufacturing Operation Database.
# Runs Streamlit directly against the local Homebrew PostgreSQL — no Docker.
# Self-healing: sets up the database and Python environment on first run.
#
clear
echo ""
echo "  Manufacturing Operation Database (Native)"
echo "  ========================================="
echo ""

cd "$(dirname "$0")" || exit 1

PG_BIN="/opt/homebrew/opt/postgresql@17/bin"
PSQL="$PG_BIN/psql"
PGREADY="$PG_BIN/pg_isready"
PY312="/opt/homebrew/bin/python3.12"
DB="maintdb"
URL="http://localhost:8501"

# ── Ensure PostgreSQL is running ──────────────────────────────────────────────
if ! "$PGREADY" -h localhost -q 2>/dev/null; then
    echo "  Starting PostgreSQL..."
    brew services start postgresql@17 >/dev/null 2>&1
    WAITED=0
    until "$PGREADY" -h localhost -q 2>/dev/null; do
        sleep 1; WAITED=$((WAITED + 1))
        if [ "$WAITED" -ge 30 ]; then
            echo "  PostgreSQL did not start. Start it manually with:"
            echo "    brew services start postgresql@17"
            read -r -p "  Press Enter to close..."
            exit 1
        fi
    done
fi

# ── Ensure the database exists and is seeded (first run only) ──────────────────
if ! "$PSQL" -h localhost -d "$DB" -tc "SELECT 1 FROM assets LIMIT 1" >/dev/null 2>&1; then
    echo "  Setting up the database (first run)..."
    "$PSQL" -h localhost -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='lukesevenish'" | grep -q 1 \
        || "$PSQL" -h localhost -d postgres -c "CREATE ROLE lukesevenish;" >/dev/null 2>&1
    "$PSQL" -h localhost -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1 \
        || "$PSQL" -h localhost -d postgres -c "CREATE DATABASE $DB;" >/dev/null 2>&1
    "$PSQL" -h localhost -d "$DB" -f maintdb_dump.sql >/dev/null 2>&1
    "$PSQL" -h localhost -d "$DB" -f service_reports_schema.sql >/dev/null 2>&1
    "$PSQL" -h localhost -d "$DB" -c "
        SELECT setval('labor_tickets_ticket_id_seq',            GREATEST((SELECT COALESCE(MAX(ticket_id),0) FROM labor_tickets),1));
        SELECT setval('asset_batteries_id_seq',                 GREATEST((SELECT COALESCE(MAX(id),0)        FROM asset_batteries),1));
        SELECT setval('asset_peripheral_equipment_id_seq',      GREATEST((SELECT COALESCE(MAX(id),0)        FROM asset_peripheral_equipment),1));
        SELECT setval('service_reports_report_id_seq',          GREATEST((SELECT COALESCE(MAX(report_id),0) FROM service_reports),1));
    " >/dev/null 2>&1
fi

# ── Ensure the Python environment exists (first run only) ──────────────────────
if [ ! -x ".venv/bin/streamlit" ]; then
    echo "  Setting up the Python environment (first run, this can take a minute)..."
    "$PY312" -m venv .venv
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -r requirements.txt
fi

# ── Import any on-disk Excel service drafts (idempotent; skips ones already in the
#    DB). Runs every launch but is a fast no-op once they're imported. ───────────
.venv/bin/python migrate_service_reports.py >/dev/null 2>&1 || true

# ── Already running? Just open it ─────────────────────────────────────────────
if curl -s "$URL/_stcore/health" 2>/dev/null | grep -q ok; then
    echo "  The app is already running."
    echo "  Opening $URL"
    open "$URL"
    exit 0
fi

# ── Launch (detached so it survives this window closing) ───────────────────────
echo "  Starting the app..."
nohup .venv/bin/streamlit run app.py --server.port=8501 --server.headless=true \
    > /tmp/maintdb_streamlit.log 2>&1 &

echo "  Waiting for the app to be ready..."
WAITED=0
until curl -s "$URL/_stcore/health" 2>/dev/null | grep -q ok; do
    sleep 1; WAITED=$((WAITED + 1))
    if [ "$WAITED" -ge 30 ]; then break; fi
done

echo ""
echo "  All done! Opening $URL"
echo "  If it does not open, go to: $URL"
echo "  To stop the app, double-click 'Stop App (Native)'."
echo ""
open "$URL"
