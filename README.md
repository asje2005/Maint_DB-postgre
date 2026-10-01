# Manufacturing Operation Database

A maintenance and shop-floor management app for tracking machines, assets, service
history, jobs, and labor — built with Streamlit on PostgreSQL.

There are three ways to run it. Pick the one that matches you:

| You want to… | Use | Needs |
|--------------|-----|-------|
| Just open the app, nothing to install | **Desktop app** (one icon) | nothing |
| Run it on this Mac without Docker | **Native launcher** | Homebrew Postgres + Python 3.12 |
| Run it in containers | **Docker** | Docker Desktop |

In every case the database **sets itself up automatically** on first run — seed data,
schema upgrades, and the leftover Excel service drafts are all loaded for you. No manual
SQL, no migrations to run by hand.

---

## 1. Desktop app — the easy way (no install)

One icon. No Docker, no database, no Python. It carries its own private PostgreSQL and
opens in its own window.

**Download a ready-made build** from the repo's [**Releases**](../../releases) page
(`MaintDB-macOS.zip` or `MaintDB-Windows.zip`), unzip, then:

- **Mac:** double-click **`MaintDB.app`** (right-click → **Open** the first time).
- **Windows:** open the **`MaintDB`** folder and double-click **`MaintDB.exe`**
  (**More info → Run anyway** the first time).

The first-launch prompt appears because the app isn't code-signed yet; it's a one-time click.

### Building the desktop app

If you have the project and need to produce the app, double-click the builder — no terminal:

- **Mac:** **`Build Desktop App (Mac).command`** → makes `dist/MaintDB.app`
- **Windows:** **`Build Desktop App (Windows).bat`** → makes `dist\MaintDB\MaintDB.exe`

Or build both on CI by running the **Build desktop app** GitHub Actions workflow (or pushing
a `v*` tag). Full details: [`desktop/README.md`](desktop/README.md).

---

## 2. Native launcher — Mac, no Docker

Runs Streamlit directly against a local Homebrew PostgreSQL. Self-healing: it starts
Postgres, sets up the database, builds the Python environment, and imports the drafts on
first run.

- **Start:** double-click **`Start App (Native).command`**
- **Stop:** double-click **`Stop App (Native).command`**

First run needs Homebrew with `postgresql@17` and `python@3.12` installed.

---

## 3. Docker

Runs the app and PostgreSQL in containers.

**Requirement:** [Docker Desktop](https://www.docker.com/products/docker-desktop) — install it,
open it once, and wait for the whale icon to appear.

- **First time / install:** double-click **`Install (Mac).command`** or **`Install (Windows).bat`**
  (creates a Desktop shortcut and loads the database).
- **Start:** double-click **`Start App.command`** (Mac) / **`Start App.bat`** (Windows) — opens
  the app in your browser at <http://localhost:8501>.
- **Stop:** double-click **`Stop App.command`** / **`Stop App.bat`**. Your data is saved between sessions.

> **Mac, first time:** macOS may warn that a script came from the internet. Right-click it →
> **Open** → **Open**. Once only.

To reset the database to the seed: stop the app, then from the project folder run
`docker compose down -v && docker compose up -d`.

---

## Optional: live JobBoss / ECI M1 sync

The app can pull employees, jobs, and labor tickets from a JobBoss / ECI M1 SQL Server into
its own database, so those tables stay backed by the live shop system — while every page keeps
working when JobBoss is offline. It's **off by default** and shows as unavailable until a shop
configures it (it needs `pyodbc` + an ODBC driver and the `JOBBOSS_*` environment variables, on
a machine that can reach the server). Run it from **Advanced → Settings → "Sync from JobBoss"**
or `python sync_jobboss.py`. Setup details are in the **SQL Integration Guide** tab inside the app
and in [`utils/jobboss.py`](utils/jobboss.py).

---

## For developers

- **Run from source:** `pip install -r requirements.txt`, then `streamlit run app.py` against a
  local PostgreSQL (`PG_HOST` / `PG_PORT` / `PG_DB` / `PG_USER` / `PG_PASS` env vars; defaults
  `localhost:5432` / `maintdb`). Or use `docker compose -f docker-compose.local.yml up -d` for just the DB.
- **Tests:** `pytest` (runs against the live `maintdb`; uses disposable `Z`-prefixed test data).
- **Data dictionary:** [`DEFINITIONS.md`](DEFINITIONS.md).
- **Schema:** `schema.sql` (fresh install) and `schema_fixes.sql` (idempotent upgrades, auto-applied
  on boot and during Docker DB init).
