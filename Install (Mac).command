#!/bin/bash
clear
echo ""
echo "  Manufacturing Operation Database — Installer"
echo "  ============================================="
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Step 1: Check for Docker Desktop ─────────────────────────────────────────
echo "  Checking for Docker Desktop..."

if [ -d "/Applications/Docker.app" ]; then
    echo "  Docker Desktop is already installed."
else
    echo ""
    echo "  Docker Desktop is not installed. It is required to run this app."
    echo ""
    echo "  Opening the Docker Desktop download page now."
    echo ""
    echo "  After installing Docker Desktop, run this installer again."
    echo ""
    read -p "  Press Enter to open the download page..."
    open "https://www.docker.com/products/docker-desktop"
    exit 1
fi

echo ""

# ── Step 2: Start Docker if not already running ───────────────────────────────
if ! docker info &>/dev/null 2>&1; then
    echo "  Starting Docker Desktop..."
    open -a Docker
    echo "  Waiting for Docker to be ready..."
    echo ""
    WAITED=0
    until docker info &>/dev/null 2>&1; do
        sleep 2
        WAITED=$((WAITED + 2))
        if [ $WAITED -ge 90 ]; then
            echo "  Docker is taking too long to start."
            echo "  Please open Docker Desktop manually and run this installer again."
            read -p "  Press Enter to close..."
            exit 1
        fi
    done
fi

echo "  Docker is ready."
echo ""

# ── Step 3: Make scripts executable ──────────────────────────────────────────
echo "  Setting up scripts..."
chmod +x "$PROJECT_DIR/Start App.command"
chmod +x "$PROJECT_DIR/Stop App.command"
chmod +x "$PROJECT_DIR/Install (Mac).command"
echo "  Done."
echo ""

# ── Step 4: Create a shortcut on the Desktop ─────────────────────────────────
echo "  Creating a shortcut on your Desktop..."

SHORTCUT="$HOME/Desktop/Start Manufacturing App.command"

# Write a small wrapper that delegates to the real script
printf '#!/bin/bash\nexec "%s/Start App.command"\n' "$PROJECT_DIR" > "$SHORTCUT"
chmod +x "$SHORTCUT"

echo "  Shortcut created: ~/Desktop/Start Manufacturing App.command"
echo ""

# ── Step 5: Build the app and load the database ───────────────────────────────
cd "$PROJECT_DIR"

echo "  Building the app and loading the database..."
echo "  (This may take a few minutes — please wait)"
echo ""

docker compose up --build -d

if [ $? -ne 0 ]; then
    echo ""
    echo "  Something went wrong during setup. Please contact your administrator."
    read -p "  Press Enter to close..."
    exit 1
fi

echo "  Waiting for the database to finish loading..."
WAITED=0
until curl -s http://localhost:8501 &>/dev/null; do
    sleep 3
    WAITED=$((WAITED + 3))
    if [ $WAITED -ge 180 ]; then
        echo "  Setup is taking too long. Please contact your administrator."
        docker compose down
        read -p "  Press Enter to close..."
        exit 1
    fi
done

echo "  Database loaded successfully."
echo ""
echo "  Stopping containers (your data is saved)..."
docker compose down

echo ""
echo "  ============================================="
echo "  Installation complete!"
echo ""
echo "  To start the app:"
echo "  Double-click 'Start Manufacturing App' on your Desktop."
echo ""
echo "  Mac security note:"
echo "  The first time you double-click the shortcut, macOS may show"
echo "  a security warning. Right-click the file, choose Open,"
echo "  then click Open again. You only need to do this once."
echo ""
read -p "  Press Enter to close..."
