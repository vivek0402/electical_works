# CLAUDE.md

SVKML Electrical Works (Wipro Lighting service partner, Visakhapatnam). We are building a web app with three linked systems: **Stock management**, **Defective pieces tracking**, and **Complaint filing & tracking**.

**Project restarted from scratch on 2026-10-11, at the user's request.** The earlier work is archived in the git tags `archive/main-2026-10-11` and `archive/phase-2-2026-10-11`. It is reference only: do not restore it unless the user asks.

## Session start
1. Read `tasks/lessons.md` and follow every rule in it.
2. Read `tasks/todo.md`.

## Workflow
- Plan anything with 3+ steps in plan mode. Research prior art in a subagent first. Wait for approval.
- **Mock every screen** with proper input controls and get approval before building it. Every feature ships with demo data.
- **The Excel files in `data/legacy/` show what data exists. They are never a UI template.** Use proper forms: date pickers, dropdowns/searchable selects, number inputs, validation. Excel is only an "Export to Excel" download with clean app columns.
- Tick todo items only with evidence. After any correction, add a rule to `tasks/lessons.md`.

## Design direction (direction B "Bold and graphic", chosen by the user on 2026-11-15; replaces the 2026-10-11 sidebar dashboard)
- **Shell**: dark top bar (brand, five section pills Home / Stock / Complaints / Defectives / Setup, global search, low-stock bell, user menu), then a dark hero with the page title, one line of context, the section's actions and sub-tabs. Cream page (`#f3efe6`), white cards with 18px corners, pill buttons 44px high, inputs 48px high. On phones the top bar scrolls sideways (no hamburger). Form and detail pages show a back link instead of sub-tabs. Screens read in the order main actions, what needs attention, related groups, history.
- **Type**: Bricolage Grotesque (headings, figures), Instrument Sans (text), Geist Mono (codes), **vendored** as woff2 in `static/vendor/fonts/` (no Google Fonts). Exactly five sizes: 13/15/18/28/48px.
- **UI kit underneath**: Tabler 1.6.1 + Tabler Icons 3.49.0 (vendored, no build step) and Tom Select 2.6.2 stay loaded for grid, modals, dropdowns and pickers; `static/css/app.css` loads last and restyles them, and holds the new `b-*` components. Charts are server-rendered CSS bars (no ApexCharts on the new screens). The Django admin back-office will use **django-unfold**.
- IN/OUT colours are a colour-blind-safe validated pair: blue `#2a78d6` (IN) and orange `#eb6834` (OUT). Green and orange failed the CVD check.
- Gotchas found while building: do **not** set `data-bs-navbar-position` on `<html>` any more (the sidebar is gone). Tabler's `.page-header` is a column flex and `.page-title` is `display:flex`; `app.css` resets both for the hero. `.visually-hidden` inside a scrolling top-bar strip must sit in a `position: relative` parent or it widens the page on phones. Tom Select needs its own `tom-select.bootstrap5.css` underneath `tabler-vendors.css`. The section's default hero actions are dropped by `static/js/app.js` when the page already offers the same link.

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All colours, spacing, type and aesthetic direction are defined there (direction B).
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Build
Django 5.2 + PostgreSQL 16. Windows dev machine has no Docker, so use `uv` with a `DATABASE_URL`:
- Tests: `DATABASE_URL=<postgres url> uv run pytest -q`, then `uv run ruff format --check . && uv run ruff check .`
- Dev server: `uv run python manage.py migrate`, `SEED_PASSWORD=<strong> uv run python manage.py seed_users`, `uv run python manage.py seed_service_demo` (empty database only), `uv run python manage.py runserver 8000`
- Demo data: `make demo`, or `seed_users` then `seed_service_demo` on an empty database. `seed_service_demo` brings its own stock history plus complaints, visits, defective pieces and return batches, so it **replaces** `seed_stock_demo` (which loads stock only; never run both).
- Reseed `svkml_demo` (the review database) after any walkthrough run, since the walkthrough leaves data behind: `DROP DATABASE IF EXISTS svkml_demo WITH (FORCE)` + `CREATE DATABASE svkml_demo` (psycopg autocommit on the `postgres` database), then `migrate`, `seed_users`, `seed_service_demo`, and `rebuild_stock_balances`, which must print "Cache matches ledger."
- Browser walkthrough (on demo data): `PYTHONIOENCODING=utf-8 uv run --with playwright==1.63.0 python e2e/walkthrough.py http://127.0.0.1:8000 office <password>` must exit 0 with no JS errors. Pin Playwright 1.63.0: newer versions need a browser build that isn't installed here. It is re-runnable; its docstring lists what each run leaves behind.
- Prod check: `DJANGO_SETTINGS_MODULE=config.settings.prod uv run python manage.py check --deploy` (needs SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS).
- Docker: `docker compose up -d --build`, `make migrate`, `make demo`, `make test`, `make lint`.

Where the logic lives:
- `apps/inventory/services.py`: every write (items, post/adjust/undo entries, balance rebuild).
- `apps/inventory/selectors.py`: every read (stock matrix, lists, item history, dashboard).
- `apps/inventory/entry_lines.py`: parsing the item lines posted by the entry forms.
- `apps/complaints/` and `apps/defectives/`: the same split. `services.py` holds every write (complaints, visits, status moves, sites, technicians; pieces, marking, return batches, dispatch, settle), `selectors.py` every read (lists, dashboards, counts the menu badges and main dashboard reuse), `filters.py` the list filters, `exports.py` the four service exports (pending complaints, complaint list, defective list, a batch's dispatch list).
- `apps/core/excel.py`: the shared XlsxWriter report writer (`apps/inventory/exports.py` builds the five stock exports on it; the service exports use it too).
- `apps/core/tokens.py`: one-time form tokens. Every write view uses `guarded_post(request, run)`, and form pages get their token with `page_token(session, path)` (add `@never_cache`).
- `apps/core/numbers.py`: gap-free document numbers (DEF, RB, CMP, VIS) via `next_number` / `next_numbers`.
- **Lock order** is documented at the top of `apps/defectives/services.py` (Complaint row → VIS number → ReturnBatch row → pieces in tag order → `post_entry` → `next_number(s)`). Any new service that combines these must follow it.
- Demo data: `apps/complaints/demo/service-demo.json`, replayed through the services by `seed_service_demo`. (`apps/inventory/demo/demo-data.json` is the older stock-only set for `seed_stock_demo`.)

**Every write goes through a `services.py`.** Never write to StockEntry, StockLine or StockBalance outside `apps/inventory/services.py`, and never change a complaint, visit, piece or return batch outside its app's `services.py`; every stock effect of the service modules goes through `inventory.services.post_entry`. The ledger is append-only (database triggers block updates and deletes); mistakes are cancelled with `undo_entry` (or `undo_visit_parts` for a visit's parts given).

## Service modules (built 2026-10-12 to 10-15, plan `docs/superpowers/plans/2026-10-12-defectives-complaints.md`)
- The **Defective store** is the one `Location` with `is_defective_store=True`. Use `Location.objects.good()` for anything that means good stock (totals, low stock, pickers). Only the defectives services post to it, and their entries refuse Undo.
- No company is special: Wipro is one company among several (see `tasks/lessons.md`).
