"""A throw-away local Postgres in .pgdata/, using the PostgreSQL already installed on this machine.

Needs `initdb`, `pg_ctl` and `psql` on PATH (or in C:/Program Files/PostgreSQL/<version>/bin).
Used by scripts/launcher.py (the demo window) and, as a script, by scripts/dev.sh:

    python scripts/_pg.py [database-name] [port]     # runs until Ctrl+C, writes .pgdata/url when ready

(The pgserver wheel was tried first, but its Windows build has no timezone data, so Django could not connect.)
"""

import glob
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / ".pgdata"
DATA = ROOT / "data"
QUIET = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
if sys.platform == "win32":
    QUIET["creationflags"] = subprocess.CREATE_NO_WINDOW  # no console flashes when the GUI starts these


class PostgresMissing(RuntimeError):
    """PostgreSQL is not installed (or not on PATH)."""


def find(tool):
    path = shutil.which(tool)
    if path:
        return path
    for candidate in sorted(glob.glob(f"C:/Program Files/PostgreSQL/*/bin/{tool}.exe"), reverse=True):
        return candidate
    raise PostgresMissing(
        f"Could not find {tool}. Install PostgreSQL, or set DATABASE_URL to use your own database."
    )


def stop():
    """Stop the local cluster (fine if it isn't running)."""
    subprocess.run([find("pg_ctl"), "-D", str(DATA), "stop", "-m", "fast"], **QUIET)


def start(db="svkml_demo", port="54329"):
    """Create the cluster and database if needed, start it, and return its connection URL."""
    initdb, pg_ctl, psql = find("initdb"), find("pg_ctl"), find("psql")
    ROOT.mkdir(exist_ok=True)
    (ROOT / "url").unlink(missing_ok=True)
    if not (DATA / "PG_VERSION").exists():
        subprocess.run(
            [initdb, "-D", str(DATA), "-U", "postgres", "--auth=trust", "-E", "UTF8", "--locale=C"],
            check=True,
            **QUIET,
        )
    stop()  # a stale postmaster.pid from a crash would block the start
    subprocess.run(
        [
            pg_ctl,
            "-D",
            str(DATA),
            "-o",
            f"-p {port} -c listen_addresses=127.0.0.1",
            "-l",
            str(ROOT / "pg.log"),
            "-w",
            "start",
        ],
        check=True,
        **QUIET,
    )
    base = [psql, "-h", "127.0.0.1", "-p", port, "-U", "postgres", "-d", "postgres", "-qtA"]
    exists = subprocess.run(
        [*base, "-c", f"SELECT 1 FROM pg_database WHERE datname = '{db}'"], capture_output=True, text=True
    ).stdout.strip()
    if not exists:
        subprocess.run([*base, "-c", f'CREATE DATABASE "{db}"'], check=True, **QUIET)
    url = f"postgres://postgres@127.0.0.1:{port}/{db}"
    (ROOT / "url").write_text(url)
    return url


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "svkml_demo"
    port = sys.argv[2] if len(sys.argv) > 2 else "54329"
    try:
        url = start(name, port)
    except PostgresMissing as exc:
        sys.exit(str(exc))

    def _quit(*_):
        stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _quit)
    signal.signal(signal.SIGTERM, _quit)
    print(f"Postgres ready: {url}")
    print("Ctrl+C stops it. Data stays in .pgdata/ (delete that folder to start over).", flush=True)
    while True:
        time.sleep(3600)
