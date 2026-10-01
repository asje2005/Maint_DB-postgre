#!/bin/bash
#
# Stops the natively-launched Manufacturing Operation Database app.
# (Leaves PostgreSQL running, since it's a shared system service.)
#
clear
echo ""
echo "  Manufacturing Operation Database (Native)"
echo "  ========================================="
echo ""
echo "  Stopping the app..."
echo ""

cd "$(dirname "$0")" || exit 1

if pkill -f "streamlit run app.py" 2>/dev/null; then
    echo "  The app has been stopped."
else
    echo "  The app was not running."
fi

echo ""
echo "  (PostgreSQL was left running. To stop it too: brew services stop postgresql@17)"
echo ""
read -r -p "  Press Enter to close this window..."
