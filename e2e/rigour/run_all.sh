#!/bin/sh
# Run the whole rigour suite from an empty database and save each report to e2e/rigour/out/.
#
#   sh e2e/rigour/run_all.sh [port]        (default 8001; Postgres must be running on 52207, see README.md)
#
# Order matters: the model audit and consistency checks need the loaded data as the loader left it, so they run
# before the scenario / concurrency / browser checks add their own entries. A final ledger-only audit then
# proves the books still balance after all that abuse.
set -u
cd "$(dirname "$0")/../.."
PORT="${1:-8001}"
BASE="http://127.0.0.1:$PORT"
PW='Demo-pass-2026!'
export PYTHONIOENCODING=utf-8
export DATABASE_URL="postgresql://postgres:@127.0.0.1:52207/svkml_rigour"
OUT=e2e/rigour/out
mkdir -p "$OUT"
status=0

step() {
    name="$1"
    shift
    printf '%-22s' "$name"
    if "$@" >"$OUT/$name.txt" 2>&1; then echo "ok"; else echo "FAILED (exit $?) see $OUT/$name.txt"; status=1; fi
}

uv run --with openpyxl python -I e2e/rigour/build_scenarios.py >"$OUT/00-build.txt" 2>&1 || { echo "build failed"; exit 1; }
sh e2e/rigour/reset_db.sh >"$OUT/01-reset.txt" 2>&1 || { echo "reset failed"; exit 1; }
curl -s -o /dev/null "$BASE/login/" || { echo "no server on $BASE (start: runserver $PORT --noreload with DATABASE_URL set)"; exit 1; }

step 02-load        uv run --with requests python e2e/rigour/load_entries.py "$BASE" admin "$PW"
step 03-audit       uv run --with "psycopg[binary]" python e2e/rigour/audit.py
step 04-consistency uv run --with requests --with openpyxl python e2e/rigour/consistency.py "$BASE" admin "$PW"
step 05-performance uv run python e2e/rigour/perf.py
step 06-matrix      uv run --with requests --with "psycopg[binary]" python e2e/rigour/scenario_matrix.py "$BASE" admin office "$PW"
step 07-concurrency uv run --with requests --with "psycopg[binary]" python e2e/rigour/concurrency.py "$BASE" admin "$PW"
step 08-browser     uv run --with playwright==1.63.0 python e2e/rigour/ui_checks.py "$BASE" admin "$PW"
step 09-final-audit uv run --with "psycopg[binary]" python e2e/rigour/audit.py --no-model

echo
[ $status -eq 0 ] && echo "ALL RIGOUR STEPS PASSED" || echo "SOME STEPS FAILED: read the files in $OUT"
exit $status
