#!/bin/sh
# App-container entrypoint. Everything here is automatic and idempotent so a fresh
# install "just works" with no manual steps:
#   1. import any on-disk Excel service drafts (skips ones already in the DB)
#   2. start the app — its ensure_schema() applies schema_fixes.sql on boot too
set -e

echo "Importing on-disk service drafts (idempotent)…"
python migrate_service_reports.py || echo "  draft import skipped (continuing)"

exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501
