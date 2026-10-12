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

## Design direction (chosen by the user, 2026-10-11)
- **Modern admin dashboard**: left sidebar menu (hamburger on phones), top bar with global search, white cards, KPI tiles with icons, data tables with sorting and paging, modals and toasts.
- UI kit: **Tabler 1.6.1 + Tabler Icons 3.49.0** (vendored, no build step), **Tom Select 2.6.2** with its Bootstrap 5 CSS for searchable selects, ApexCharts (bundled with Tabler) for charts. The Django admin back-office will use **django-unfold**.
- IN/OUT colours are a colour-blind-safe validated pair: blue `#2a78d6` (IN) and orange `#eb6834` (OUT). Green and orange failed the CVD check.
- Gotchas found while building: Tabler needs `data-bs-navbar-position="vertical"` on `<html>`, and the top bar must sit inside `.page-wrapper`, otherwise the sidebar or top bar is hidden. Tom Select needs its own `tom-select.bootstrap5.css` underneath `tabler-vendors.css`.

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All colours, spacing and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Build
Django 5.2 + PostgreSQL 16. Windows dev machine has no Docker, so use `uv` with a `DATABASE_URL`:
- Tests: `DATABASE_URL=<postgres url> uv run pytest -q`, then `uv run ruff format --check . && uv run ruff check .`
- Dev server: `uv run python manage.py migrate`, `SEED_PASSWORD=<strong> uv run python manage.py seed_users`, `uv run python manage.py seed_stock_demo` (empty ledger only), `uv run python manage.py runserver 8000`
- Browser walkthrough (on demo data): `uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office <password>` must exit 0 with no JS errors.
- Prod check: `DJANGO_SETTINGS_MODULE=config.settings.prod uv run python manage.py check --deploy` (needs SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS).
- Docker: `docker compose up -d --build`, `make migrate`, `make demo`, `make test`, `make lint`.

Where the logic lives:
- `apps/inventory/services.py`: every write (items, post/adjust/undo entries, balance rebuild).
- `apps/inventory/selectors.py`: every read (stock matrix, lists, item history, dashboard).
- `apps/inventory/entry_lines.py`: parsing the item lines posted by the entry forms.
- `apps/core/excel.py`: the shared XlsxWriter report writer (`apps/inventory/exports.py` builds the five exports on it).
- Demo data: `apps/inventory/demo/demo-data.json`, loaded by `seed_stock_demo`.

**Never write to StockEntry, StockLine or StockBalance outside `services.py`.** The ledger is append-only (database triggers block updates and deletes); mistakes are cancelled with `undo_entry`.
