"""Filesystem locations for the bundled desktop app.

A packaged .app/.exe is read-only, so all mutable state (the Postgres data dir and
the per-asset document folders) lives in a per-user writable directory:

    macOS:    ~/Library/Application Support/MaintDB
    Windows:  %LOCALAPPDATA%\\MaintDB
    other:    ~/.local/share/MaintDB

Bundled, read-only resources (app code, SQL seeds, the seed Maintenance_DB, the
Postgres binaries) are resolved relative to the PyInstaller bundle when frozen, or
the repo root when running from source.
"""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_root() -> Path:
    """Directory holding bundled read-only resources (app.py, utils/, *.sql,
    Maintenance_DB/, runtime/). PyInstaller unpacks these under sys._MEIPASS."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Per-user writable directory for the database and documents.
    Overridable with MAINTDB_DATA_DIR (used by tests / power users)."""
    override = os.getenv("MAINTDB_DATA_DIR")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    d = base / "MaintDB"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pg_data_dir() -> Path:
    return data_root() / "pgdata"


def doc_root() -> Path:
    """Writable copy of the per-asset document folders."""
    return data_root() / "Maintenance_DB"


def pg_bin_dir() -> Path:
    """Directory containing the bundled Postgres binaries (initdb, pg_ctl, postgres)."""
    plat = "windows" if os.name == "nt" else ("darwin" if sys.platform == "darwin" else "linux")
    return resource_root() / "runtime" / plat / "bin"
