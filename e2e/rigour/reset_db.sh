#!/bin/sh
# Drop and recreate the rigour database: migrated, with the admin and office users, and nothing else.
# Needs Postgres running on port 52207 (see README). Never touches svkml_demo.
set -e
cd "$(dirname "$0")/../.."
uv run --with "psycopg[binary]" python -c "
import psycopg
with psycopg.connect('postgresql://postgres:@127.0.0.1:52207/postgres', autocommit=True, connect_timeout=5) as c:
    c.execute('DROP DATABASE IF EXISTS svkml_rigour WITH (FORCE)')
    c.execute('CREATE DATABASE svkml_rigour')
print('svkml_rigour recreated')
"
export DATABASE_URL="postgresql://postgres:@127.0.0.1:52207/svkml_rigour"
uv run python manage.py migrate -v 0
SEED_PASSWORD='Demo-pass-2026!' uv run python manage.py seed_users
