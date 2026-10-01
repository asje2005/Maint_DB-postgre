#!/bin/bash
clear
echo ""
echo "  Manufacturing Operation Database"
echo "  ================================="
echo ""

# ── Check Docker is installed ─────────────────────────────────────────────────
if ! [ -d "/Applications/Docker.app" ] && ! command -v docker &>/dev/null; then
    echo "  Docker Desktop is not installed."
    echo ""
    echo "  Please download and install it from:"
    echo "  https://www.docker.com/products/docker-desktop"
    echo ""
    read -p "  Press Enter to open the download page..."
    open "https://www.docker.com/products/docker-desktop"
    exit 1
fi

# ── Start Docker if not already running ───────────────────────────────────────
if ! docker info &>/dev/null 2>&1; then
    echo "  Starting Docker Desktop..."
    open -a Docker
    echo "  Waiting for Docker to be ready (this may take up to 30 seconds)..."
    echo ""
    WAITED=0
    until docker info &>/dev/null 2>&1; do
        sleep 2
        WAITED=$((WAITED + 2))
        if [ $WAITED -ge 90 ]; then
            echo "  Docker is taking too long to start."
            echo "  Please open Docker Desktop manually and run this script again."
            read -p "  Press Enter to close..."
            exit 1
        fi
    done
fi

# ── Move to the project folder ────────────────────────────────────────────────
cd "$(dirname "$0")"

# ── Start the app ─────────────────────────────────────────────────────────────
echo "  Starting the app..."
echo ""
docker compose up -d 2>&1

if [ $? -ne 0 ]; then
    echo ""
    echo "  Something went wrong. Please contact your administrator."
    read -p "  Press Enter to close..."
    exit 1
fi

# ── Wait until the app responds ───────────────────────────────────────────────
echo ""
echo "  Waiting for the app to be ready..."
WAITED=0
until curl -s http://localhost:8501 &>/dev/null; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ $WAITED -ge 60 ]; then break; fi
done

# ── Open the browser ──────────────────────────────────────────────────────────
echo ""
echo "  All done! Opening the app in your browser."
echo ""
echo "  If it does not open, go to: http://localhost:8501"
echo ""
echo "  To stop the app, double-click 'Stop App'."
echo ""
sleep 1
open "http://localhost:8501"
