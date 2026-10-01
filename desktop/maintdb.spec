# PyInstaller spec for the MaintDB desktop app (Mac .app / Windows .exe).
# Build:  pyinstaller desktop/maintdb.spec --noconfirm --clean
#
# app.py is RUN by Streamlit at runtime (loaded as data, not imported at freeze
# time), so its third-party deps must be force-collected and its own modules shipped
# as data + hidden imports.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).resolve().parent          # repo root (spec lives in desktop/)
PLAT = "windows" if sys.platform.startswith("win") else ("darwin" if sys.platform == "darwin" else "linux")

datas, binaries, hiddenimports = [], [], []

# Force-collect the heavy runtime deps app.py uses (Streamlit loads it dynamically).
for pkg in ["streamlit", "plotly", "pandas", "numpy",
            "sqlalchemy", "psycopg2", "openpyxl", "altair", "pyarrow",
            "tornado", "watchdog", "webview"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f"[spec] collect_all({pkg}) skipped: {e}")

for meta in ["streamlit", "plotly", "pandas", "numpy",
             "sqlalchemy", "openpyxl", "altair", "pyarrow", "pywebview"]:
    try:
        datas += copy_metadata(meta)
    except Exception:
        pass

# Project files the app reads/runs at runtime (resolved via app_paths.resource_root()).
def add(src, dest="."):
    p = ROOT / src
    if p.exists():
        datas.append((str(p), dest))

add("app.py")
add("migrate_service_reports.py")
add("schema.sql"); add("schema_fixes.sql"); add("service_reports_schema.sql"); add("maintdb_dump.sql")
add("utils", "utils")
add("static", "static")
add("Maintenance_DB", "Maintenance_DB")
add("desktop", "desktop")
add(f"runtime/{PLAT}", f"runtime/{PLAT}")           # bundled Postgres binaries

hiddenimports += ["utils", "utils.db", "utils.queries", "utils.theme", "utils.jobboss",
                  "migrate_service_reports", "desktop", "desktop.app_paths", "desktop.db_runtime",
                  "psycopg2", "plotly.graph_objects", "plotly.express"]

a = Analysis(
    [str(ROOT / "desktop" / "maintdb_desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MaintDB",
          console=False, disable_windowed_traceback=False, argv_emulation=True,
          target_arch=None, codesign_identity=None, entitlements_file=None)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MaintDB")

app = BUNDLE(coll, name="MaintDB.app", icon=None,
             bundle_identifier="com.maintdb.desktop",
             info_plist={
                 "CFBundleName": "MaintDB",
                 "CFBundleDisplayName": "MaintDB",
                 "NSHighResolutionCapable": True,
                 "LSApplicationCategoryType": "public.app-category.business",
             })
