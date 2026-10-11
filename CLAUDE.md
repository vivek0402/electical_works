# CLAUDE.md

Spares inventory (fresh + defective, multi-location), Wipro defective returns, and service complaints for SVKML Electrical Works, Visakhapatnam (a Wipro Lighting service partner). It replaces three Excel files. Samples are in `data/legacy/`: they are **reference + demo data, not the production dataset**. They are committed to this private repo and contain real customer contacts, so never make the repo public. The importer must stay generic: nothing is hardcoded to these specific rows.

## Session start
1. Read `tasks/lessons.md`, then `tasks/todo.md`.
2. Approved plan: `C:\Users\vivek\.claude\plans\pasted-content-id-3f22-0-your-jazzy-pancake.md`.
3. Workflow: plan anything with 3+ steps first (research prior art in a subagent), wait for approval, tick todo items only with evidence. After any user correction, add a rule to `tasks/lessons.md`.
4. **Always build mocks:** every screen gets a clickable HTML mockup in `mockups/` (fake data, app styling) approved by the user *before* the real view is built, and every feature ships demo data loaded by `make demo`.

## Stack
- Python 3.12, Django 5.2 LTS, PostgreSQL 16, Django templates + HTMX 2.0.4 + Pico CSS 2.0.6 (vendored in `static/vendor/`, no build step).
- Docker Compose: `db` + `web` in dev. Prod adds Caddy (Phase 7, `deploy/`). Gunicorn + WhiteNoise.
- Dependencies are pinned in `pyproject.toml` and locked in `uv.lock` (uv).

## Commands (need Docker Desktop + GNU make; on Windows use Git Bash)
| Task | Command |
|---|---|
| Start (http://localhost:8000) | `make up` |
| Migrate | `make migrate` |
| Seed groups + users | `make seed` (needs `SEED_PASSWORD` in `.env`) |
| Tests | `make test` (`ARGS="-k name"` to filter) |
| Lint / format | `make lint` / `make fmt` |
| Django shell | `make shell` |
| Legacy import review | `make import-review` → `data/legacy/import_review.xlsx` (Phase 2) |
| Legacy import apply | `make import-apply` (Phase 2) |

Without Docker (lint and checks only): `uv sync`, then `uv run ruff check .` and `uv run python manage.py check`.
The host Postgres for compose is on **port 5433**, because a native Postgres may own 5432.

## Layout
```
config/settings/{base,dev,test,prod}.py   env-driven (django-environ); manage.py defaults to dev, wsgi to prod
config/formats/en/formats.py              DD-MM-YYYY everywhere (overrides Django's locale formats)
apps/core          base layout views, /healthz (checks DB), later: attachments
apps/accounts      roles (Groups ADMIN/OFFICE/TECHNICIAN), Profile.home_location, seed_demo
apps/inventory     Location (Phase 1); Item, aliases, stock ledger (Phase 2+)
apps/complaints    Phase 4 · apps/defectives Phase 5 · apps/legacy_import Phase 2 · apps/reports Phase 5/6
templates/         base.html, registration/, per-app folders
tests/             pytest; mirrors apps/; factories.py; fixtures/ for fake legacy xlsx
tasks/             todo.md, lessons.md
```

## Conventions
- **Business logic lives only in `services.py` (writes) and `selectors.py` (reads).** Never in views, forms, templates or `save()`. Views stay thin.
- Stock: an append-only ledger (`StockMovement`, protected by pgtrigger). Fix mistakes with reversing documents. `StockBalance` is a rebuildable cache. Writes use `transaction.atomic()` + `select_for_update()`, with locks taken in sorted (item, location, bucket) order.
- Roles are enforced server-side with `apps.accounts.decorators.role_required(...)`. ADMIN passes every check. Map model permissions per role in `apps/accounts/roles.py::ROLE_PERMISSIONS`; they are re-synced after every `migrate`.
- Master data is deactivated (`is_active=False`), never deleted, once it has history.
- Times are stored in UTC and displayed in IST. Dates show as DD-MM-YYYY. Quantities are integers (NOS).
- Any business rule marked OPEN QUESTION uses a clearly labelled default in one place (see `tasks/todo.md`) until the user confirms it.
- Licences: OCA/ERPNext (AGPL/GPL) are reference for designs only, never copy their code. InvenTree (MIT) is fine.
- Migrations must be reviewed and reversible (data migrations get a reverse function). CI runs `makemigrations --check`.
- Errors shown to users are friendly and specific, e.g. "Only 7 NOS of EIO6006 (Fresh) at Vizag Office".

## Dependencies (one-line justification each)
| Package | Why |
|---|---|
| django 5.2.18 | LTS framework (decided) |
| psycopg[binary] | Postgres driver |
| django-environ | `.env` / 12-factor config |
| django-htmx | `request.htmx` helpers for partial responses |
| django-template-partials | one template serves the full page + HTMX fragment (built into Django 6) |
| django-tables2 + django-filter | Excel-like sortable/filterable list pages with little code |
| django-pgtrigger | DB-level append-only guard on the stock ledger |
| openpyxl | Excel import/export in the client's layouts |
| rapidfuzz | fuzzy duplicate clustering of part codes during legacy import |
| gunicorn, whitenoise | WSGI server; static files without nginx |
| dev: pytest, pytest-django, pytest-cov, factory-boy, ruff, pre-commit | tests against real Postgres, factories, lint/format |
Planned: Pillow (Phase 4 uploads), django-pghistory (Phase 3 audit), sentry-sdk (Phase 7).
