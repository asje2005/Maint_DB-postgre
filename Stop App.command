#!/bin/bash
clear
echo ""
echo "  Manufacturing Operation Database"
echo "  ================================="
echo ""
echo "  Stopping the app..."
echo ""

cd "$(dirname "$0")"
docker compose down

echo ""
echo "  The app has been stopped."
echo ""
read -p "  Press Enter to close this window..."
