# MaintDB — bundled desktop app

One icon. No Docker, no Homebrew, no Python, no database to install. Double-click and
the app opens in its own window. It carries its **own private PostgreSQL** (started,
self-seeded, and shut down automatically) and the whole Streamlit app inside a single
bundle.

## How it works

```
maintdb_desktop.py (entry)
 ├─ app_paths.py      where bundled resources live + a per-user writable data dir
 │                      macOS:   ~/Library/Application Support/MaintDB
 │                      Windows: %LOCALAPPDATA%\MaintDB
 ├─ db_runtime.py     starts a private Postgres on a random localhost port; on first
 │                      run creates the DB, loads the seed + migrations, imports drafts
 ├─ (subprocess of self) runs the Streamlit server headless on a random port
 └─ pywebview         shows that server in a native window; closing it stops everything
```

The Postgres binaries are **relocatable** (downloaded at build time from the
zonky.io embedded-postgres set) and run with no system dependencies. The app reads
everything from this embedded Postgres, so all existing features work unchanged.

## Build

You build on the OS you're targeting — PyInstaller can't cross-compile.

**Easiest — double-click (no terminal):** in the project folder, double-click
**`Build Desktop App (Mac).command`** or **`Build Desktop App (Windows).bat`**. It sets
everything up, builds, and opens the folder with the finished app.

Or from a terminal:

**macOS (Apple Silicon)**
```bash
./desktop/build_mac.sh            # → dist/MaintDB.app
```

**Windows**
```bat
desktop\build_windows.bat         REM → dist\MaintDB\MaintDB.exe
```

**Both, via CI (no local toolchain needed):** push a `v*` tag or run the
*Build desktop app* workflow (`.github/workflows/build-desktop.yml`) — it builds the
Mac `.app` and Windows `.exe` and uploads them as artifacts.

The build (1) installs `pyinstaller` + `pywebview`, (2) runs `fetch_postgres.py` to
download the relocatable Postgres into `runtime/<platform>/` (git-ignored), then
(3) runs PyInstaller against `desktop/maintdb.spec`.

> The bundle includes whatever is in `Maintenance_DB/` at build time. That folder is
> git-ignored (private shop docs/drafts), so a clean CI build ships **without** those
> files; a local build on a machine that has them includes them. The core database
> seed (`maintdb_dump.sql`) is always included.

## Releasing (tag → published installers)

Pushing a version tag builds both installers and publishes them on a **GitHub Release**
automatically:

```bash
git tag v1.0
git push origin v1.0
```

The **Build desktop app** workflow then builds the Mac `.app` and Windows `.exe`, zips
them (`MaintDB-macOS.zip`, `MaintDB-Windows.zip`), and attaches them to a Release named
after the tag — so anyone can download and double-click, no toolchain required.

> One-time repo setting: **Settings → Actions → General → Workflow permissions** must be
> **Read and write** for the release step to create the Release. (The workflow already
> requests `contents: write`.)

## First launch (unsigned)

These builds are **not code-signed**, so the OS shows a one-time warning:

- **macOS**: right-click the app → **Open** → **Open**. (Once per install.)
- **Windows**: **More info** → **Run anyway**.

## Adding code-signing later (removes the warning)

- **macOS** — needs an Apple Developer account ($99/yr). After building:
  ```bash
  codesign --deep --force --options runtime --sign "Developer ID Application: NAME (TEAMID)" dist/MaintDB.app
  xcrun notarytool submit dist/MaintDB.app --apple-id <id> --team-id <TEAMID> --password <app-pw> --wait
  xcrun stapler staple dist/MaintDB.app
  ```
  (Or set `codesign_identity=` in `maintdb.spec` and add a notarize step to the CI workflow.)
- **Windows** — needs a code-signing certificate (OV/EV). After building:
  ```bat
  signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 dist\MaintDB\MaintDB.exe
  ```

## Resetting / moving the data

All mutable state lives in the per-user data dir (above). Delete it to start fresh; the
app re-seeds on the next launch. Override the location with the `MAINTDB_DATA_DIR`
environment variable.

## JobBoss sync in the desktop app

The optional JobBoss sync needs `pyodbc` + the SQL Server ODBC driver, which aren't
in the base bundle. It stays auto-disabled (Settings shows it as unavailable) unless a
shop adds those and sets the `JOBBOSS_*` env vars — it never blocks the simple path.
