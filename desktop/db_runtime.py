"""Embedded PostgreSQL the bundled desktop app owns and manages — no system
Postgres, no Docker. Starts a private, localhost-only server, self-seeds on first
run, recovers from a prior crash, and shuts down cleanly."""
import io
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import psycopg2

SUPERUSER = "lukesevenish"  # matches the OWNER in maintdb_dump.sql so it loads clean
DBNAME = "maintdb"
_COPY_RE = re.compile(r'^\s*COPY\s+.*\bFROM stdin;\s*$', re.IGNORECASE)

# Keep the bundled Postgres tools from flashing a console window on the windowed
# Windows build. CREATE_NO_WINDOW exists only on Windows.
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _has_sql(text: str) -> bool:
    for ln in text.splitlines():
        t = ln.strip()
        if t and not t.startswith("--"):
            return True
    return False


def run_sql_script(conn, sql_text: str) -> None:
    """Execute a pg_dump/DDL script that may contain ``COPY ... FROM stdin;`` blocks
    and psql backslash meta-commands (\\restrict, \\unrestrict, …). Plain SQL is
    executed; COPY data is streamed via copy_expert (psycopg2 can't run COPY FROM
    stdin through execute). One fresh connection per file mirrors psql's behaviour."""
    cur = conn.cursor()
    lines = sql_text.splitlines(keepends=True)
    i, buf = 0, []

    def flush():
        chunk = "".join(buf)
        if _has_sql(chunk):
            cur.execute(chunk)
        buf.clear()

    while i < len(lines):
        if _COPY_RE.match(lines[i]):
            flush()
            stmt = lines[i].strip().rstrip(';')
            data = []
            i += 1
            while i < len(lines) and lines[i].rstrip("\n") != r"\.":
                data.append(lines[i])
                i += 1
            cur.copy_expert(stmt, io.StringIO("".join(data)))
            i += 1
        elif lines[i].lstrip().startswith("\\"):
            i += 1  # psql meta-command
        else:
            buf.append(lines[i])
            i += 1
    flush()
    conn.commit()


class EmbeddedPostgres:
    def __init__(self, bin_dir: Path, data_dir: Path):
        self.bin_dir = Path(bin_dir)
        self.data_dir = Path(data_dir)
        self.port = None

    def _exe(self, name: str) -> str:
        exe = self.bin_dir / (name + (".exe" if os.name == "nt" else ""))
        return str(exe)

    @property
    def initialized(self) -> bool:
        return (self.data_dir / "PG_VERSION").exists()

    def _initdb(self):
        self.data_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [self._exe("initdb"), "-D", str(self.data_dir), "-U", SUPERUSER,
             "-A", "trust", "--encoding=UTF8", "--locale=C"],
            check=True, capture_output=True, **_NO_WINDOW)

    def _running_port(self):
        """If a server is already running on this data dir (an orphan left by a
        force-quit/crash), return its port so we can adopt it instead of starting a
        second server that would collide; else None."""
        if not self.initialized:
            return None
        res = subprocess.run([self._exe("pg_ctl"), "-D", str(self.data_dir), "status"],
                             capture_output=True, text=True, **_NO_WINDOW)
        if res.returncode != 0:
            return None  # not running (pg_ctl self-heals a stale pid on the next start)
        try:  # postmaster.pid line 4 (1-based) is the port
            lines = (self.data_dir / "postmaster.pid").read_text().splitlines()
            if len(lines) >= 4 and lines[3].strip().lstrip("-").isdigit():
                return int(lines[3].strip())
        except Exception:
            pass
        return None

    def _pg_ctl_start(self, log: Path):
        return subprocess.run(
            [self._exe("pg_ctl"), "-D", str(self.data_dir), "-l", str(log),
             "-o", f"-p {self.port} -c listen_addresses=127.0.0.1", "start"],
            capture_output=True, text=True, **_NO_WINDOW)

    def _log_path(self) -> Path:
        return self.data_dir.parent / "postgres.log"

    def _log_tail(self, lines=40) -> str:
        try:
            text = self._log_path().read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        except Exception:
            return ""

    def _status_text(self) -> str:
        try:
            res = subprocess.run([self._exe("pg_ctl"), "-D", str(self.data_dir), "status"],
                                 capture_output=True, text=True, **_NO_WINDOW)
            return "\n".join(part.strip() for part in (res.stdout, res.stderr) if part.strip())
        except Exception as exc:
            return f"Could not check pg_ctl status: {exc}"

    def start(self) -> str:
        """Start the server and return the SQLAlchemy URL. initdb on first run; adopt
        an orphaned cluster from a prior crash; recover (one stop+retry) on a wedged
        start instead of crashing the launcher."""
        if not self.initialized:
            self._initdb()
        log = self._log_path()
        adopted = self._running_port()
        if adopted is not None:
            self.port = adopted
            try:
                self._wait_ready(timeout=8)
                return self.url(DBNAME)
            except RuntimeError:
                self.stop()
                time.sleep(0.5)

        last_error = None
        for _attempt in range(2):
            self.port = _free_port()
            res = self._pg_ctl_start(log)
            if res.returncode != 0:
                last_error = f"{res.stdout}\n{res.stderr}".strip()
                self.stop()
                time.sleep(0.5)
                continue
            try:
                self._wait_ready()
                return self.url(DBNAME)
            except RuntimeError as exc:
                last_error = str(exc)
                self.stop()
                time.sleep(0.5)

        raise RuntimeError("Could not start the embedded database after retrying.\n"
                           f"{last_error}\n\nRecent Postgres log:\n{self._log_tail()}")

    def _wait_ready(self, timeout=40):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                psycopg2.connect(host="127.0.0.1", port=self.port,
                                 user=SUPERUSER, dbname="postgres").close()
                return
            except Exception as e:
                last = e
                time.sleep(0.4)
        details = [f"Embedded Postgres did not become ready on port {self.port}: {last}"]
        status = self._status_text()
        if status:
            details.append(f"pg_ctl status:\n{status}")
        tail = self._log_tail()
        if tail:
            details.append(f"Recent Postgres log:\n{tail}")
        raise RuntimeError("\n\n".join(details))

    def stop(self):
        # pg_ctl stops by data dir, so it works regardless of the chosen port.
        if (self.data_dir / "PG_VERSION").exists():
            subprocess.run([self._exe("pg_ctl"), "-D", str(self.data_dir), "-m", "fast", "stop"],
                           capture_output=True, **_NO_WINDOW)

    def url(self, db: str) -> str:
        return f"postgresql+psycopg2://{SUPERUSER}@127.0.0.1:{self.port}/{db}"

    # ── seeding ────────────────────────────────────────────────────────────────
    def _admin_conn(self):
        return psycopg2.connect(host="127.0.0.1", port=self.port, user=SUPERUSER, dbname="postgres")

    def _database_exists(self) -> bool:
        conn = self._admin_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DBNAME,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def _database_complete(self) -> bool:
        """True only if the database exists AND looks fully seeded (key tables present
        and populated) — so a half-loaded DB from an interrupted seed is NOT mistaken
        for done."""
        if not self._database_exists():
            return False
        try:
            conn = psycopg2.connect(host="127.0.0.1", port=self.port, user=SUPERUSER, dbname=DBNAME)
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.assets'), to_regclass('public.service_reports')")
            assets_tbl, sr_tbl = cur.fetchone()
            ok = assets_tbl is not None and sr_tbl is not None
            if ok:
                cur.execute("SELECT COUNT(*) FROM assets")
                ok = cur.fetchone()[0] > 0
            conn.close()
            return ok
        except Exception:
            return False

    def _drop_database(self):
        try:
            conn = self._admin_conn()
            conn.autocommit = True
            conn.cursor().execute(f"DROP DATABASE IF EXISTS {DBNAME} WITH (FORCE)")
            conn.close()
        except Exception:
            pass

    def seed_if_needed(self, resource_root: Path, doc_root: Path):
        """Create + seed the database on first run. Self-healing: a ``.seed_complete``
        marker (written only after a FULL success) is the done-signal; an interrupted
        seed leaves no marker and is dropped + retried on the next launch, so a partial
        load can never permanently brick the app. ``doc_root`` is the writable
        Maintenance_DB the app reads."""
        marker = self.data_dir.parent / ".seed_complete"
        if marker.exists():
            return False
        if self._database_complete():   # good DB, just missing the marker → adopt it
            marker.write_text("ok")
            return False

        self._drop_database()           # clear any partial DB from a prior failed seed
        try:
            admin = self._admin_conn()
            admin.autocommit = True
            admin.cursor().execute(f"CREATE DATABASE {DBNAME}")
            admin.close()
            for fname in ("maintdb_dump.sql", "service_reports_schema.sql", "schema_fixes.sql"):
                conn = psycopg2.connect(host="127.0.0.1", port=self.port, user=SUPERUSER, dbname=DBNAME)
                run_sql_script(conn, (resource_root / fname).read_text(encoding="utf-8"))
                conn.close()

            from sqlalchemy import create_engine
            eng = create_engine(self.url(DBNAME))
            try:
                import migrate_service_reports as msr
                msr.migrate(eng, db_dir=doc_root, verbose=False)
                os.environ["MAINTDB_DOC_ROOT"] = str(doc_root)
                from utils import queries as q
                q.backfill_documents(eng)
            finally:
                eng.dispose()

            marker.write_text("ok")
            return True
        except Exception:
            self._drop_database()       # leave a clean slate so the next launch retries
            raise
