"""Download relocatable PostgreSQL 17 binaries for bundling, at build time.

Uses the zonky.io embedded-postgres-binaries (Maven Central) — purpose-built to be
extracted and run from anywhere (dylib/DLL paths are self-contained). Extracts into
``desktop/runtime/<platform>/`` (bin/ lib/ share/), which the PyInstaller spec bundles
and which app_paths.pg_bin_dir() resolves at runtime.

    python desktop/fetch_postgres.py            # current platform
    python desktop/fetch_postgres.py darwin     # or: windows / linux
"""
import io
import os
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PG_VERSION = "17.10.0"
HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parent / "runtime"   # repo-root/runtime/<platform> (matches app_paths + spec)

# platform -> (maven classifier, txz name inside the jar)
TARGETS = {
    "darwin":  ("darwin-arm64v8", "postgres-darwin-arm_64.txz"),
    "windows": ("windows-amd64",  "postgres-windows-x86_64.txz"),
    "linux":   ("linux-amd64",    "postgres-linux-x86_64.txz"),
}


def _current() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if os.name == "nt":
        return "windows"
    return "linux"


def fetch(platform: str) -> Path:
    if platform not in TARGETS:
        raise SystemExit(f"Unknown platform {platform!r}; choose from {list(TARGETS)}")
    classifier, txz_name = TARGETS[platform]
    out = RUNTIME / platform
    if (out / "bin").exists():
        print(f"  {platform}: already present at {out}")
        return out

    url = ("https://repo1.maven.org/maven2/io/zonky/test/postgres/"
           f"embedded-postgres-binaries-{classifier}/{PG_VERSION}/"
           f"embedded-postgres-binaries-{classifier}-{PG_VERSION}.jar")
    print(f"  downloading {platform} Postgres {PG_VERSION} …")
    jar_bytes = urllib.request.urlopen(url, timeout=120).read()

    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as jar:
        names = [n for n in jar.namelist() if n.endswith(".txz")]
        if not names:
            raise SystemExit(f"No .txz found in jar for {platform}")
        txz = jar.read(names[0])

    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(txz), mode="r:xz") as tar:
        tar.extractall(out)

    # Drop contrib extension modules that link external language runtimes
    # (PL/Python, PL/Perl, PL/Tcl). The app uses no extensions, and these break
    # PyInstaller's binary processing because their interpreter isn't bundled.
    ext_dir = out / "lib" / "postgresql"
    removed = 0
    if ext_dir.exists():
        for f in ext_dir.iterdir():
            if any(k in f.name for k in ("plpython", "plperl", "pltcl")):
                f.unlink()
                removed += 1
    print(f"  extracted -> {out}  (bin: {len(list((out / 'bin').iterdir()))} files, "
          f"pruned {removed} external-language modules)")
    return out


if __name__ == "__main__":
    fetch(sys.argv[1] if len(sys.argv) > 1 else _current())
