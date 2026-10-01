#!/bin/bash
# Double-click to build the MaintDB desktop app (Mac). No terminal commands needed.
clear
echo ""
echo "  Build the MaintDB Desktop App (Mac)"
echo "  ==================================="
echo ""
echo "  This makes a double-clickable app (dist/MaintDB.app) that runs with nothing"
echo "  else installed. It takes a few minutes the first time. You can watch below."
echo ""

cd "$(dirname "$0")" || exit 1

# ── Find Python 3.12 ──────────────────────────────────────────────────────────
PY312="/opt/homebrew/bin/python3.12"
if [ ! -x "$PY312" ]; then
    PY312="$(command -v python3.12 || command -v python3 || true)"
fi
if [ -z "$PY312" ]; then
    echo "  Python 3.12 isn't installed."
    echo "  Install it with Homebrew:  brew install python@3.12"
    echo "  then double-click this again."
    echo ""
    read -r -p "  Press Enter to close..."
    exit 1
fi

# ── Build environment ─────────────────────────────────────────────────────────
if [ ! -x ".venv/bin/python" ]; then
    echo "  Setting up the build environment (first time only)…"
    "$PY312" -m venv .venv || { echo "  Could not create the environment."; read -r -p "  Press Enter to close..."; exit 1; }
fi

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
if PYTHON=".venv/bin/python" ./desktop/build_mac.sh; then
    echo ""
    echo "  ✅  Done!  Your app is:  dist/MaintDB.app"
    echo "  Opening the folder — drag MaintDB.app into Applications to install it."
    echo "  First launch: right-click MaintDB.app → Open → Open (one time only)."
    open dist 2>/dev/null
else
    echo ""
    echo "  ❌  The build hit a problem. The messages above explain what happened."
fi

echo ""
read -r -p "  Press Enter to close..."
