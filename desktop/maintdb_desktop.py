"""MaintDB desktop app entry point.

One double-click → starts a private embedded Postgres (self-seeds on first run),
starts Streamlit headless, and shows the app in its own native window. No browser,
no Docker, no Homebrew, nothing for the user to install.

Two modes in one binary:
  * default               — orchestrate Postgres + Streamlit + the window
  * --maintdb-streamlit P — (re-launched by the orchestrator) run the Streamlit
                            server in-process on port P; lets one frozen binary host
                            both roles without a separate python/streamlit executable.
"""
import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

# Make bundled top-level modules (app.py, utils/, migrate_service_reports.py) importable
# whether frozen (added by PyInstaller) or running from source.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desktop import app_paths
from desktop.db_runtime import EmbeddedPostgres, SUPERUSER, DBNAME


# ── Streamlit server mode (child process) ──────────────────────────────────────
def _run_streamlit(port: int):
    from streamlit.web import bootstrap
    app_path = app_paths.resource_root() / "app.py"
    os.chdir(app_paths.resource_root())
    flag_options = {
        "server.address": "127.0.0.1",
        "server.port": int(port),
        "server.headless": True,
        "global.developmentMode": False,
        "browser.gatherUsageStats": False,
    }
    bootstrap.load_config_options(flag_options=flag_options)
    bootstrap.run(str(app_path), False, [], flag_options)


# ── Orchestrator mode (main process) ───────────────────────────────────────────
def _prepare_documents() -> Path:
    """Copy the bundled (read-only) Maintenance_DB into the writable per-user dir on
    first run. Atomic: build a temp copy and os.replace it into place, so an
    interrupted copy never leaves a half-populated folder. Returns the writable path."""
    dst = app_paths.doc_root()
    src = app_paths.resource_root() / "Maintenance_DB"
    if not dst.exists() and src.exists():
        tmp = dst.parent / (dst.name + ".partial")
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(src, tmp)
        os.replace(tmp, dst)            # atomic on the same filesystem
    dst.mkdir(parents=True, exist_ok=True)
    return dst


def _wait_health(port: int, timeout=60) -> bool:
    url = f"http://127.0.0.1:{port}/_stcore/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if urllib.request.urlopen(url, timeout=2).read().strip() == b"ok":
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _streamlit_command(port: int):
    cmd = [sys.executable]
    if not app_paths.is_frozen():
        cmd.append(os.path.abspath(__file__))
    cmd += ["--maintdb-streamlit", str(port)]
    return cmd


def _report_startup_error(exc: BaseException):
    """The windowed build has no console, so write the details to a log the user can
    find and pop a native dialog instead of failing silently."""
    log = app_paths.data_root() / "startup_error.log"
    try:
        log.write_text("".join(traceback.format_exception(exc)))
    except Exception:
        pass
    msg = f"MaintDB couldn't start.\n\n{exc}\n\nDetails were saved to:\n{log}"
    try:
        if sys.platform == "darwin":
            safe = msg.replace('"', "'")
            subprocess.run(["osascript", "-e",
                            f'display dialog "{safe}" with title "MaintDB" buttons {{"OK"}} default button "OK"'],
                           capture_output=True)
        elif os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "MaintDB", 0x10)
        else:
            print(msg, file=sys.stderr)
    except Exception:
        pass


def main():
    doc_root = _prepare_documents()
    os.environ["MAINTDB_DOC_ROOT"] = str(doc_root)

    pg = EmbeddedPostgres(app_paths.pg_bin_dir(), app_paths.pg_data_dir())
    server = None
    _done = {"cleaned": False}

    def cleanup(*_a):
        if _done["cleaned"]:
            return
        _done["cleaned"] = True
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=8)
            except Exception:
                try:
                    server.kill()
                except Exception:
                    pass
        try:
            pg.stop()
        except Exception:
            pass

    # Tear both children down on normal exit AND on Dock-Quit / logout / kill, so a
    # force-quit can't orphan Postgres or Streamlit.
    atexit.register(cleanup)
    for _sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if _sig is not None:
            try:
                signal.signal(_sig, lambda *_a: (cleanup(), sys.exit(0)))
            except Exception:
                pass

    try:
        pg.start()
        pg.seed_if_needed(app_paths.resource_root(), doc_root)
        os.environ.update({
            "PG_HOST": "127.0.0.1", "PG_PORT": str(pg.port),
            "PG_USER": SUPERUSER, "PG_DB": DBNAME, "PG_PASS": "",
        })

        s = socket.socket(); s.bind(("127.0.0.1", 0)); web_port = s.getsockname()[1]; s.close()
        server = subprocess.Popen(_streamlit_command(web_port), env=os.environ.copy())

        if not _wait_health(web_port):
            raise RuntimeError("The app did not start in time.")

        if os.environ.get("MAINTDB_NO_WINDOW"):   # headless self-test
            print(f"READY http://127.0.0.1:{web_port}")
            return

        import webview
        webview.create_window("MaintDB — Manufacturing Operation Database",
                              f"http://127.0.0.1:{web_port}",
                              width=1440, height=920, min_size=(1024, 700))
        webview.start()  # blocks until the window is closed
    except BaseException as exc:
        if not isinstance(exc, SystemExit):
            _report_startup_error(exc)
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--maintdb-streamlit":
        _run_streamlit(int(sys.argv[2]))
    else:
        main()
