#!/bin/bash
# Build MaintDB.app (unsigned) on an Apple-Silicon Mac.
#   ./desktop/build_mac.sh
# Output: dist/MaintDB.app  (drag to /Applications, double-click to run)
set -e
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY="python3"

echo "1/4  Installing build deps (app deps + pyinstaller + pywebview)…"
"$PY" -m pip install --quiet -r requirements.txt
"$PY" -m pip install --quiet pyinstaller pywebview

echo "2/4  Fetching relocatable PostgreSQL binaries…"
"$PY" desktop/fetch_postgres.py darwin

echo "3/4  Building MaintDB.app (this takes a few minutes)…"
"$PY" -m PyInstaller desktop/maintdb.spec --noconfirm --clean

echo "4/4  Done → dist/MaintDB.app"
echo
echo "Unsigned build: the first launch shows a one-time Gatekeeper prompt —"
echo "right-click the app → Open → Open. (See desktop/README.md to sign it.)"
