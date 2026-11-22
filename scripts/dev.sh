#!/usr/bin/env bash
# One command to run SVKML locally in a tmux session.
#
#   scripts/dev.sh            start (or re-attach to) the session
#   scripts/dev.sh reset      wipe the demo database and reload the demo data, then start
#   scripts/dev.sh stop       kill the session (stops the server and the local Postgres)
#
# Windows tabs:   run it from Git Bash or MSYS2. tmux is not in Git Bash; in an MSYS2 shell run
#                 `pacman -S tmux`. Without tmux the script opens Windows Terminal split panes instead.
# Needs: uv, bash. Postgres: set DATABASE_URL to use your own; otherwise a local one is started (the installed PostgreSQL)
#        in .pgdata/ on port 54329 (database svkml_demo).
#
# Panes
#   run  window:  [server]  migrate, load demo data once, runserver on :8000
#                 [db]      local Postgres (only when DATABASE_URL is not set)
#   work window:  [shell]   a shell with the same environment (tests, lint, manage.py)
#                 [e2e]     the browser walkthrough, typed in and waiting for Enter
# There is no frontend build step: Tabler, Tom Select and the fonts are vendored in static/, so a
# CSS or template edit shows on refresh.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="${SVKML_SESSION:-svkml}"
PORT="${PORT:-8000}"
cd "$ROOT"

# ---- settings shared by every pane (an existing environment or .env value wins) ----------------
export DEBUG="${DEBUG:-True}"
export SECRET_KEY="${SECRET_KEY:-dev-only-not-a-secret-$(printf '%s' "$ROOT" | cksum | cut -d' ' -f1)}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-localhost,127.0.0.1}"
export SEED_PASSWORD="${SEED_PASSWORD:-Demo-Pass-2026}"
export PYTHONIOENCODING=utf-8
export DEMO_URL="http://127.0.0.1:$PORT"

say() { printf '\033[1;36m[svkml]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[svkml]\033[0m %s\n' "$*" >&2; exit 1; }

if [[ -z "${DATABASE_URL:-}" && -f .env ]] && grep -qE '^DATABASE_URL=' .env; then
  USE_OWN_DB=1  # Django reads it from .env itself
elif [[ -n "${DATABASE_URL:-}" ]]; then
  USE_OWN_DB=1
else
  USE_OWN_DB=0
fi

# ---- pane bodies (this script calls itself as `dev.sh _db|_server|_shell`) ---------------------
pane_db() {
  [[ "$USE_OWN_DB" == 1 ]] && { say "Using your own DATABASE_URL, nothing to start here."; exec sleep infinity; }
  exec uv run python scripts/_pg.py svkml_demo
}

load_db_url() {
  [[ "$USE_OWN_DB" == 1 ]] && return 0
  say "Waiting for the local Postgres…"
  for _ in $(seq 1 90); do
    [[ -s .pgdata/url ]] && { DATABASE_URL="$(cat .pgdata/url)"; export DATABASE_URL; return 0; }
    sleep 1
  done
  die "The local Postgres did not start. Look at the [db] pane."
}

pane_server() {
  load_db_url
  say "Migrating…"
  uv run python manage.py migrate --noinput
  if [[ "${SVKML_RESET:-0}" == 1 ]]; then
    say "Reset requested: dropping every table so the demo reloads."
    uv run python manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
"
    uv run python manage.py migrate --noinput
  fi
  uv run python manage.py seed_users
  if uv run python manage.py shell -c "import sys; from apps.inventory.models import Item; sys.exit(1 if Item.objects.exists() else 0)"; then
    say "Empty database: loading the demo data."
    uv run python manage.py seed_service_demo
    uv run python manage.py rebuild_stock_balances
  else
    say "Database already has data, leaving it alone (use: scripts/dev.sh reset)."
  fi
  say "Open $DEMO_URL   login: admin or office   password: $SEED_PASSWORD"
  exec uv run python manage.py runserver "0.0.0.0:$PORT"
}

pane_shell() {
  load_db_url
  say "Ready. Run these one at a time:"
  printf '    uv run pytest -q
    uv run ruff check .
    uv run python manage.py shell
'
  exec "${SHELL:-bash}"
}

pane_e2e() {
  load_db_url
  say "Walkthrough (it leaves data behind; run \`scripts/dev.sh reset\` before a client demo)."
  say "Press Enter to run the command below, or Ctrl+C to skip."
  CMD="uv run --with playwright==1.63.0 python e2e/walkthrough.py $DEMO_URL office '$SEED_PASSWORD'"
  printf '$ %s ' "$CMD"; read -r _
  eval "$CMD" || true
  exec "${SHELL:-bash}"
}

case "${1:-}" in
  _db) pane_db ;;
  _server) pane_server ;;
  _shell) pane_shell ;;
  _e2e) pane_e2e ;;
  stop)
    tmux kill-session -t "$SESSION" 2>/dev/null && say "Stopped." || say "No session to stop."
    exit 0 ;;
  reset)
    [[ "$USE_OWN_DB" == 1 ]] && die "reset only works on the local demo database. Your DATABASE_URL is set, so nothing was touched."
    export SVKML_RESET=1 ;;
  ""|start) ;;
  *) die "Unknown command: $1 (use: start | reset | stop)" ;;
esac

# ---- launcher ----------------------------------------------------------------------------------
command -v uv >/dev/null || die "uv is not installed. See https://docs.astral.sh/uv/"
SELF="$ROOT/scripts/dev.sh"

if command -v tmux >/dev/null; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    if [[ "${SVKML_RESET:-0}" == 1 ]]; then
      tmux kill-session -t "$SESSION"
    else
      say "Session '$SESSION' is already running, attaching."
      exec tmux attach -t "$SESSION"
    fi
  fi
  [[ "$USE_OWN_DB" == 0 ]] && rm -f .pgdata/url
  tmux new-session -d -s "$SESSION" -n run -c "$ROOT" "SVKML_RESET=${SVKML_RESET:-0} PORT=$PORT bash '$SELF' _server"
  tmux set-option -t "$SESSION" -g mouse on
  tmux set-option -t "$SESSION" -g pane-border-status top
  tmux set-option -t "$SESSION" -g pane-border-format ' #{pane_title} '
  tmux select-pane -t "$SESSION:run.0" -T "server  (http://127.0.0.1:$PORT)"
  tmux split-window -t "$SESSION:run" -h -c "$ROOT" "PORT=$PORT bash '$SELF' _db"
  tmux select-pane -t "$SESSION:run.1" -T "db"
  tmux new-window -t "$SESSION" -n work -c "$ROOT" "PORT=$PORT bash '$SELF' _shell"
  tmux select-pane -t "$SESSION:work.0" -T "shell"
  tmux split-window -t "$SESSION:work" -h -c "$ROOT" "PORT=$PORT bash '$SELF' _e2e"
  tmux select-pane -t "$SESSION:work.1" -T "e2e walkthrough"
  tmux select-window -t "$SESSION:run"
  say "Session '$SESSION' started. Ctrl+b then 0/1 switches window, d detaches, 'scripts/dev.sh stop' ends it."
  exec tmux attach -t "$SESSION"
fi

# ---- no tmux: Windows Terminal split panes ----------------------------------------------------
if command -v wt.exe >/dev/null 2>&1 || command -v wt >/dev/null 2>&1; then
  say "tmux not found, opening Windows Terminal panes instead (install tmux in MSYS2: pacman -S tmux)."
  BASH_EXE="$(command -v bash)"
  [[ "$USE_OWN_DB" == 0 ]] && rm -f .pgdata/url
  WT="$(command -v wt.exe || command -v wt)"
  # wt reads ';' as its own separator, so every argument below is passed as a separate word.
  "$WT" new-tab --title server -d "$ROOT" "$BASH_EXE" "$SELF" _server \; \
        split-pane -V --title db -d "$ROOT" "$BASH_EXE" "$SELF" _db \; \
        new-tab --title shell -d "$ROOT" "$BASH_EXE" "$SELF" _shell \; \
        split-pane -V --title e2e -d "$ROOT" "$BASH_EXE" "$SELF" _e2e
  say "Opened in a new Windows Terminal window. Close it to stop everything."
  exit 0
fi

die "Neither tmux nor Windows Terminal (wt) found. Install tmux (Linux/macOS: your package manager; MSYS2: pacman -S tmux)."
