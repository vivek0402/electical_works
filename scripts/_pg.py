"""Run a throw-away local Postgres in .pgdata/ (using the Postgres already installed on this machine).

Used by scripts/dev.sh when no DATABASE_URL is set. Needs `initdb` and `pg_ctl` on PATH (or in
C:/Program Files/PostgreSQL/<version>/bin). Writes the connection URL to .pgdata/url once ready and
stops the server on Ctrl+C. (The pgserver wheel was tried first but its Windows build has no timezone
data, so Django could not connect.)

    python scripts/_pg.py [database-name] [port]
"""

import glob
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

DB = sys.argv[1] if len(sys.argv) > 1 else "svkml_demo"
PORT = sys.argv[2] if len(sys.argv) > 2 else "54329"
ROOT = Path(__file__).resolve().parent.parent / ".pgdata"
DATA = ROOT / "data"


def find(tool):
    path = shutil.which(tool)
    if path:
        return path
    for candidate in sorted(glob.glob(f"C:/Program Files/PostgreSQL/*/bin/{tool}.exe"), reverse=True):
        return candidate
    sys.exit(f"Could not find {tool}. Install PostgreSQL, or set DATABASE_URL to use your own database.")


initdb, pg_ctl, psql = find("initdb"), find("pg_ctl"), find("psql")
ROOT.mkdir(exist_ok=True)
(ROOT / "url").unlink(missing_ok=True)

if not (DATA / "PG_VERSION").exists():
    print("Creating the local Postgres cluster…", flush=True)
    subprocess.run(
        [initdb, "-D", str(DATA), "-U", "postgres", "--auth=trust", "-E", "UTF8", "--locale=C"],
        check=True,
        stdout=subprocess.DEVNULL,
    )

subprocess.run(  # a stale postmaster.pid from a crash would block the start
    [pg_ctl, "-D", str(DATA), "stop", "-m", "fast"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
subprocess.run(
    [
        pg_ctl,
        "-D",
        str(DATA),
        "-o",
        f"-p {PORT} -c listen_addresses=127.0.0.1",
        "-l",
        str(ROOT / "pg.log"),
        "-w",
        "start",
    ],
    check=True,
    stdout=subprocess.DEVNULL,
)


def stop(*_):
    subprocess.run([pg_ctl, "-D", str(DATA), "stop", "-m", "fast"], stdout=subprocess.DEVNULL)
    sys.exit(0)


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

base = [psql, "-h", "127.0.0.1", "-p", PORT, "-U", "postgres", "-d", "postgres", "-qtA"]
exists = subprocess.run(
    [*base, "-c", f"SELECT 1 FROM pg_database WHERE datname = '{DB}'"], capture_output=True, text=True
).stdout.strip()
if not exists:
    subprocess.run([*base, "-c", f'CREATE DATABASE "{DB}"'], check=True)
    print(f"created database {DB}")

url = f"postgres://postgres@127.0.0.1:{PORT}/{DB}"
(ROOT / "url").write_text(url)
print(f"Postgres ready: {url}")
print("Ctrl+C stops it. Data stays in .pgdata/ (delete that folder to start over).", flush=True)

while True:
    time.sleep(3600)
