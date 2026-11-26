# SVKML Service

A web app for **SVKML Electrical Works**, a lighting service partner in Visakhapatnam. It replaces the office's stock, defective-pieces and complaint spreadsheets with one system built on a single, append-only stock ledger.

Built with Django 5.2 and PostgreSQL 16. The front end is server-rendered templates with vendored Tabler and Tom Select, so there is **no Node build step**.

---

## Contents

1. [What it does](#what-it-does)
2. [How the three systems link](#how-the-three-systems-link)
3. [Tech stack](#tech-stack)
4. [Getting started](#getting-started)
5. [Configuration](#configuration)
6. [Demo data and management commands](#demo-data-and-management-commands)
7. [Users and roles](#users-and-roles)
8. [Screens and URLs](#screens-and-urls)
9. [Excel reports](#excel-reports)
10. [Architecture](#architecture)
11. [Domain rules](#domain-rules)
12. [Project layout](#project-layout)
13. [Design system](#design-system)
14. [Testing](#testing)
15. [Production](#production)
16. [Troubleshooting](#troubleshooting)
17. [Project history and docs](#project-history-and-docs)
18. [License](#license)

---

## What it does

### Stock management
- Staff record **Stock IN** (from a supplier, returned unused from a site, or opening stock), **Stock OUT** (to a site, a technician or other), **Transfers** between locations and **Adjustments** (physical count, damaged, lost, found, other).
- Every entry is written to an **append-only ledger** and is never edited or deleted. A mistake is cancelled with an **Undo** entry that reverses it.
- Stock can never go negative: an over-issue is refused and nothing is saved.
- On top of the ledger: current stock per location, each item's full history, the movements register, low-stock warnings (against each item's reorder level) and a **global search** that also finds old spellings of item codes (item aliases).

### Complaints
- Logs customer-site complaints against saved **sites** (mobile or STD landline phone numbers) and **technicians**.
- A **visit** can give parts (a real Stock OUT) and collect failed parts (each becomes a tagged defective piece).
- Each complaint moves only through allowed statuses: *Not attended → Attended → Material need to check / Awaiting material → Resolved → Closed*, or it is closed as **Not covered** with a reason.

### Defective pieces
- Every failed part gets its own tag (`DEF-0001`, `DEF-0002`, …), whether it was collected at a visit or marked defective from stock.
- Pieces sit in a separate **Defective store**. It is shown next to stock but never counted as good stock.
- Pieces go back to their company in a **return batch** (draft, then dispatched with courier and docket number). The company's answer settles each piece: **replaced** or **repaired** (a Stock IN back into good stock) or **rejected** (returned to the store, or scrapped).

**No company is special.** Wipro Lighting is one company among several (Havells, Finolex and so on). Returns go to the item's company, and a complaint records whose product it is. `DEFAULT_COMPANY` is only a configurable default.

---

## How the three systems link

```
                 ┌───────────────────────────────┐
                 │  Stock ledger (append-only)   │
                 │  StockEntry + StockLine       │
                 │  → StockBalance (cache)       │
                 └──────▲────────▲────────▲──────┘
          Stock OUT     │        │        │   Stock IN (replacement / repair)
   (parts given at visit)        │        │
┌───────────────┐       │        │        │       ┌──────────────────────┐
│  Complaints   │───────┘        │        └───────│  Return batches      │
│  site, visit, │  failed parts  │                │  draft → dispatched  │
│  status moves │──────────────► │ Defective store│  → settled per piece │
└───────────────┘   collected    │  (DEF tags)    └──────────▲───────────┘
                                 │                           │
                   "Mark defective" from good stock ─────────┘
```

Every stock effect of the complaints and defectives modules is a normal ledger entry posted through `inventory.services.post_entry`. The stock screens therefore always agree with the service screens.

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | Django 5.2 (`django-environ` for settings) |
| Database | PostgreSQL 16 (`psycopg` 3). Append-only rules use database triggers via `django-pgtrigger`. |
| UI | Django templates, Tabler 1.6.1, Tabler Icons 3.49.0, Tom Select 2.6.2, all **vendored** in `static/vendor/`. `static/css/app.css` holds the app's own `b-*` components. |
| Fonts | Bricolage Grotesque, Instrument Sans, Geist Mono, vendored as woff2 (no Google Fonts) |
| Back office | Django admin themed with `django-unfold` |
| Excel | XlsxWriter (exports), openpyxl (tests read them back) |
| Serving | gunicorn + WhiteNoise for static files |
| Tooling | `uv` (dependencies and running), `ruff` (lint and format), `pytest` + `pytest-django`, Playwright 1.63.0 (browser walkthrough) |

---

## Getting started

Pick whichever fits your machine. Every option ends at http://127.0.0.1:8000 (or http://localhost:8000), where you log in as `office` or `admin`.

### Option 1: one-click demo (Windows)

Double-click **`start-demo.cmd`**. It needs [uv](https://docs.astral.sh/uv/) and an installed PostgreSQL 16.

It opens a small window (`scripts/launcher.py`) that starts a local Postgres, migrates, loads the demo data the first time, starts the server and opens the browser. The window has buttons to reset the demo data and stop everything. Closing it stops everything.

- Default password: `Demo-Pass-2026`, unless you set `SEED_PASSWORD`.
- If `DATABASE_URL` is set (in the environment or `.env`), the launcher uses that database instead, and **Reset demo data** is disabled because it wipes the database.
- Self-test without a window: `uv run python scripts/launcher.py --selftest`.

### Option 2: terminal panes (`scripts/dev.sh`)

```bash
scripts/dev.sh          # start, or re-attach to, the session
scripts/dev.sh reset    # wipe the demo database, reload the demo data, then start
scripts/dev.sh stop     # stop the server and the local Postgres
```

It runs in tmux. Without tmux (for example in Git Bash on Windows) it opens Windows Terminal split panes instead. The panes are:

- **server**: migrate, load the demo data once, `runserver` on port 8000
- **db**: a local Postgres in `.pgdata/` on port 54329, database `svkml_demo` (only when `DATABASE_URL` is not set)
- **shell**: a shell with the same environment for tests, lint and `manage.py`
- **e2e**: the browser walkthrough, typed in and waiting for Enter

### Option 3: Docker

```bash
cp .env.example .env        # then set SECRET_KEY and a strong SEED_PASSWORD
docker compose up -d --build
make migrate
make demo                   # users admin + office, plus the full demo data set
```

Compose starts `postgres:16-alpine` (exposed on host port **5433**) and the web container running `runserver` with dev settings. The source folder is mounted, so code edits reload.

Other `make` targets: `make test`, `make lint`, `make fmt`, `make shell`, `make down`.

### Option 4: by hand with uv

You need Python 3.12, [uv](https://docs.astral.sh/uv/) and a PostgreSQL 16 server.

```bash
uv sync
export DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/svkml"
uv run python manage.py migrate
SEED_PASSWORD="<a strong password>" uv run python manage.py seed_users
uv run python manage.py seed_service_demo   # optional demo data, empty database only
uv run python manage.py runserver 8000
```

`manage.py` uses `config.settings.dev` by default. `SEED_PASSWORD` must pass Django's password validators: at least 8 characters, not a common password, not all digits.

---

## Configuration

Settings are read from the environment and from a `.env` file in the project root (copy `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | empty (dev uses an insecure fallback) | Django secret key. **Required** in production. |
| `DEBUG` | `False` (`True` in dev settings) | Debug mode. |
| `ALLOWED_HOSTS` | dev: `localhost,127.0.0.1,0.0.0.0` | Comma-separated host names. **Required** in production. |
| `CSRF_TRUSTED_ORIGINS` | empty | Comma-separated origins such as `https://svkml.example.com` (production). |
| `DATABASE_URL` | `postgres://svkml:svkml@localhost:5433/svkml` | Database connection. **Required** in production. |
| `SEED_PASSWORD` | none | Password for the `admin` and `office` users created by `seed_users`. |
| `DEFAULT_COMPANY` | `Wipro Lighting` | Company offered first where a default is harmless. |
| `COURIERS` | `DTDC,Professional Couriers,ST Courier,VRL Logistics,By hand` | Suggestions in the courier box when a return batch is dispatched. Any other name can be typed. |
| `LOG_LEVEL` | `INFO` | Root log level (logs go to the console). |
| `SECURE_SSL_REDIRECT` | `True` | Production only: redirect HTTP to HTTPS. |
| `SECURE_HSTS_SECONDS` | 30 days | Production only: HSTS max age. |

Locale: English UI (`en-in`), times shown in IST (`Asia/Kolkata`) and stored in UTC, and dates shown as DD-MM-YYYY everywhere (`config/formats/`).

Settings modules: `config.settings.base` (shared), `dev`, `test` (used by pytest) and `prod`.

---

## Demo data and management commands

Every feature ships with realistic demo data, so the app can be shown without real client data.

| Command | What it does |
|---|---|
| `seed_users` | Creates the `admin` (Admin role, superuser) and `office` (Office role) users with `SEED_PASSWORD`. Safe to run again: existing users keep their passwords. |
| `seed_service_demo` | Loads the full demo set from `apps/complaints/demo/service-demo.json` by **replaying it through the app's own services**: about 5 weeks of stock history, 26 complaints with their visits, 60 defective pieces and 3 return batches. Runs only on an empty database and refuses to run twice. Refuses when `DEBUG` is off unless you pass `--force`. |
| `seed_stock_demo` | The older, stock-only demo set (`apps/inventory/demo/demo-data.json`). Use either this or `seed_service_demo`, **never both**. |
| `rebuild_stock_balances` | Rebuilds the `StockBalance` cache from the ledger and checks it. On a healthy database it prints **"Cache matches ledger."** |

### Resetting the review database

After a browser walkthrough run, reseed `svkml_demo`, because the walkthrough leaves data behind:

1. Connect to the `postgres` database (autocommit) and run `DROP DATABASE IF EXISTS svkml_demo WITH (FORCE)`, then `CREATE DATABASE svkml_demo`.
2. `migrate`, `seed_users`, `seed_service_demo`.
3. `rebuild_stock_balances`, which must print "Cache matches ledger."

`scripts/dev.sh reset` and the launcher's **Reset demo data** button do this for the local demo database.

---

## Users and roles

There are two roles, stored as Django groups and enforced in views with `role_required`.

| Role | Can do |
|---|---|
| **Admin** | Everything: all stock, complaints and defectives screens, masters (locations, companies, fitting types, spare types), hiding sites and technicians, reopening a closed complaint, users, and the Django admin back office at `/admin/`. |
| **Office** | Every stock screen (IN, OUT, transfer, adjust, undo, lists, exports), every complaints and defectives screen (file complaints, record visits, mark defective, return batches, settle, exports), and adding and editing items, sites and technicians. |

- Members of the Admin group automatically get `is_staff`, so they can open `/admin/`.
- An adjustment needs a reason and a note. An undo needs a reason.

---

## Screens and URLs

The top bar has five sections: **Home, Stock, Complaints, Defectives, Setup**, plus global search, the low-stock bell and the user menu.

### Home and search
| URL | Screen |
|---|---|
| `/` | Dashboard: what needs attention across all three systems |
| `/search/` | JSON endpoint behind the top-bar search: items (code, old spellings, description, fitting), entry numbers, complaints, sites and defective pieces |
| `/login/`, `/logout/` | Sign in and out |
| `/healthz` | Health check for load balancers (exempt from the HTTPS redirect) |

### Stock
| URL | Screen |
|---|---|
| `/stock/` | Current stock: items × locations, with the Defective store column shown but left out of the total |
| `/stock/in/`, `/stock/out/`, `/stock/transfer/`, `/stock/adjust/` | Entry forms |
| `/movements/` | Movements register (every ledger entry) |
| `/entries/<number>/` | Entry detail, with `/undo/` to cancel it |
| `/low-stock/` | Items at or below their reorder level |
| `/items/`, `/items/new/`, `/items/<id>/`, `/items/<id>/edit/` | Item list, form and item card with full history |
| `/masters/` | Locations, companies, fitting types, spare types (Admin) |

### Complaints
| URL | Screen |
|---|---|
| `/complaints/` | Complaints dashboard |
| `/complaints/list/` | Filterable complaint list |
| `/complaints/new/` | File a complaint |
| `/complaints/<number>/` | Complaint detail and timeline |
| `/complaints/<number>/visit/` | Record a visit (parts given, failed parts collected) |
| `/complaints/<number>/status/`, `/not-covered/` | Status moves |
| `/sites/`, `/sites/<id>/` | Sites |
| `/technicians/` | Technicians |

### Defectives
| URL | Screen |
|---|---|
| `/defectives/` | Defectives dashboard |
| `/defectives/mark/` | Mark good stock as defective |
| `/defectives/pieces/`, `/defectives/pieces/<tag>/` | Piece list (with bulk actions) and piece detail |
| `/defectives/batches/`, `/defectives/batches/new/` | Return batches |
| `/defectives/batches/<number>/` | Batch detail: add or remove pieces, dispatch, settle |

---

## Excel reports

Nine reports download as neatly formatted `.xlsx` files with clean app columns (never the old spreadsheet layouts). All are built on the shared writer in `apps/core/excel.py`.

| Report | URL | Built in |
|---|---|---|
| Current stock | `/stock/export/` | `apps/inventory/exports.py` |
| Movements | `/movements/export/` | `apps/inventory/exports.py` |
| Item list | `/items/export/` | `apps/inventory/exports.py` |
| Low stock | `/low-stock/export/` | `apps/inventory/exports.py` |
| One item's history | `/items/<id>/export/` | `apps/inventory/exports.py` |
| Pending complaints | `/complaints/pending/export/` | `apps/complaints/exports.py` |
| Complaint list | `/complaints/export/` | `apps/complaints/exports.py` |
| Defective list | `/defectives/export/` | `apps/defectives/exports.py` |
| A return batch's dispatch list | `/defectives/batches/<number>/export/` | `apps/defectives/exports.py` |

---

## Architecture

### Services and selectors

Each domain app splits its logic the same way:

- **`services.py`** holds **every write**. Views and management commands call these functions and never change models directly.
- **`selectors.py`** holds **every read**: lists, dashboards, and the counts reused by the menu badges and the main dashboard.
- `filters.py` holds list filters, `exports.py` the Excel reports and `forms.py` the form validation.

| App | Writes in `services.py` |
|---|---|
| `apps/inventory` | Items; posting, adjusting and undoing entries; balance rebuild. `entry_lines.py` parses the item lines posted by the entry forms. |
| `apps/complaints` | Complaints, visits, status moves, sites, technicians |
| `apps/defectives` | Pieces, marking defective, return batches, dispatch, settle |

**Hard rule:** never write to `StockEntry`, `StockLine` or `StockBalance` outside `apps/inventory/services.py`, and never change a complaint, visit, piece or return batch outside its own app's `services.py`.

### The ledger

- A `StockEntry` (numbered `IN-0001`, `OUT-0001`, `TRF-…`, `ADJ-…`, `REV-…`) has one or more `StockLine`s, each a signed quantity of one item at one location.
- `StockEntry` and `StockLine` are **append-only**: PostgreSQL triggers (`pgtrigger.Protect`) block every `UPDATE` and `DELETE`. A mistake is cancelled with `undo_entry`, which posts a reversing `REV` entry. A visit's parts given are cancelled with `undo_visit_parts`.
- `StockBalance` is a cache of the current quantity per item and location. `post_entry` updates it under row locks in the same transaction, and refuses any entry that would make a balance negative. `rebuild_stock_balances` recomputes it from the ledger to prove they match.
- Entries posted by the defectives screens refuse Undo, because a piece's state depends on them.

### The Defective store

There is exactly one `Location` with `is_defective_store=True`. Only the defectives services post to it. Anything that means *good stock* (totals, low stock, location pickers) uses `Location.objects.good()`, which leaves it out.

### Document numbers

`apps/core/numbers.py` hands out **gap-free** numbers with `next_number` and `next_numbers`, from a locked `Counter` row per prefix:

| Prefix | Document |
|---|---|
| `CMP-` | Complaint |
| `VIS-` | Visit |
| `DEF-` | Defective piece tag |
| `RB-` | Return batch |

Ledger entries have their own `EntryCounter` per entry kind.

### One-time form tokens

`apps/core/tokens.py` stops double submits. Every form page gets a token from `page_token(session, path)` (and is marked `@never_cache`), and every write view runs through `guarded_post(request, run)`. Saving spends the token and remembers what it saved:

- A second submit of the same form (double click, or Back then Save) is sent to what was already saved instead of saving twice.
- A different action sent with a spent token is treated as expired: nothing is saved, and the page comes back with a fresh token and what was typed.
- Two requests that arrive at the same instant are serialised by a `TokenClaim` row in the database, so the second waits for the first and is sent to its result.

### Lock order

Services that combine complaints, defectives and stock take row locks in one fixed order, so two transactions can never deadlock:

```
Complaint row → VIS number → ReturnBatch row → pieces in tag order → post_entry → next_number(s)
```

The full reasoning, including the two documented exceptions, is at the top of `apps/defectives/services.py`. Any new service that combines these must follow it.

---

## Domain rules

### Stock entry kinds

| Kind | Types a user can choose |
|---|---|
| Stock IN | From supplier, Returned unused from site, Opening stock |
| Stock OUT | Site / customer, Technician, Other |
| Transfer | (between two good locations) |
| Adjustment | Physical count, Damaged, Lost, Found, Other (reason and note required) |
| Undo | (reverses one earlier entry; reason required) |

The complaints and defectives services also post entries with their own types, which never appear on the stock forms: parts given at a visit, failed parts collected at site, mark defective, defectives returned to company, replacement or repaired piece from company, rejected piece back from company, and defective pieces scrapped.

### Entry form rules
- Never preselect a supplier, company or location (source or destination) on an entry form. Fields start on "Choose…" with a clear "required" message. Only harmless defaults, such as today's date, are filled in.
- Every date is a date picker, every known value a dropdown or searchable select, every quantity a number input.

### Complaint statuses

| From | Allowed moves |
|---|---|
| Not attended | Attended, Not covered |
| Attended | Material need to check, Awaiting material, Resolved, Not covered |
| Material need to check | Attended, Awaiting material, Resolved, Not covered |
| Awaiting material | Attended, Material need to check, Resolved, Not covered |
| Resolved | Closed, Attended, Not covered |
| Closed | none (only Admin can reopen, which moves it back to Attended) |
| Not covered | none |

- A visit can leave a complaint at Attended, Material need to check, Awaiting material or Resolved. It never closes one: closing is a separate status change.
- **Not covered** needs a reason: Not our product, Out of warranty, Customer cancelled or Other.
- Priority is Normal, High or Urgent. Every move is recorded as a `ComplaintEvent` in the complaint's timeline.

### Defective piece statuses

| From | Allowed moves |
|---|---|
| In store | In draft batch, Scrapped |
| In draft batch | In store (removed from batch), Sent to company (batch dispatched) |
| Sent to company | Settled, In store (rejected and sent back) |
| Settled | none |
| Scrapped | none |

- A piece is collected at a site visit or found in stock.
- Settle outcomes: **Replaced** or **Repaired** (a Stock IN into the good location you pick), **Rejected (returned)** or **Rejected (scrapped)**.
- A return batch belongs to one company: a piece from another company is refused. The batch shows Draft, Dispatched, Partly settled or Settled, worked out from how many of its lines the company has answered.

---

## Project layout

```
.
├── apps/
│   ├── accounts/      roles (Admin, Office), login, seed_users
│   ├── core/          numbers, one-time tokens, Excel writer, tables, healthz
│   ├── inventory/     items, masters, ledger, stock forms, stock exports
│   ├── complaints/    sites, technicians, complaints, visits, seed_service_demo
│   └── defectives/    pieces, return batches, defectives exports
├── config/
│   ├── settings/      base, dev, test, prod
│   ├── formats/       DD-MM-YYYY date formats
│   └── urls.py
├── templates/         Django templates (shell, pages, partials)
├── static/
│   ├── css/app.css    the app's styles and b-* components (loads last)
│   ├── js/app.js
│   └── vendor/        Tabler, Tabler Icons, Tom Select, fonts
├── tests/             pytest suite, one folder per app, plus integration and permission tests
├── e2e/
│   ├── walkthrough.py the Playwright browser walkthrough
│   └── rigour/        stress and scenario tests driven by the legacy Excel files
├── scripts/           dev.sh (terminal panes), launcher.py (demo window), _pg.py (local Postgres helper)
├── mockups/           approved clickable HTML mockups (design references, no backend)
├── docs/superpowers/  design specs and implementation plans
├── data/legacy/       the client's original Excel files (evidence of what data exists, never a UI template)
├── tasks/             todo.md and lessons.md
├── DESIGN.md          the design system
├── start-demo.cmd     double-click demo launcher (Windows)
├── compose.yaml, Dockerfile, Makefile
└── pyproject.toml, uv.lock
```

---

## Design system

The look is **direction B, "Bold and graphic"**, chosen on 2026-11-15. **Read [DESIGN.md](DESIGN.md) before making any visual change.** In short:

- A dark top bar with five section pills, then a dark hero with the page title, one line of context, the section's actions and sub-tabs. On phones the top bar scrolls sideways (no hamburger menu).
- A cream page (`#f3efe6`), white cards with 18px corners, pill buttons 44px high, inputs 48px high.
- Exactly five type sizes: 13, 15, 18, 28 and 48px.
- IN and OUT use a colour-blind-safe pair: blue `#2a78d6` for IN and orange `#eb6834` for OUT.
- Charts are server-rendered CSS bars.

New screens are mocked in `mockups/` and approved before they are built.

---

## Testing

### Unit and integration tests

```bash
DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/postgres" uv run pytest -q
uv run ruff format --check . && uv run ruff check .
```

- Pytest uses `config.settings.test` and creates its own test database, so point `DATABASE_URL` at any server you can create databases on.
- The suite has about 650 tests, including concurrency tests (two threads trying to oversell the same stock, racing form tokens) and constraint tests that prove the database triggers block edits.
- With Docker: `make test` (with coverage) and `make lint`.

### Browser walkthrough

With the dev server running on demo data (`seed_service_demo`):

```bash
uv run --with playwright==1.63.0 playwright install chromium     # once
PYTHONIOENCODING=utf-8 uv run --with playwright==1.63.0 python e2e/walkthrough.py http://127.0.0.1:8000 office "<SEED_PASSWORD>"
```

Playwright is pinned to 1.63.0 because newer releases need a newer browser build. The password can also come from the `E2E_PASSWORD` environment variable.

On a desktop-sized window the walkthrough covers:
- **Stock:** global search, Stock IN with a new item created from the picker, a refused over-issue, a transfer, an adjustment, and sorting and exporting current stock.
- **Complaints:** marks a piece defective; files a complaint at a new site created from the site picker; records a visit that gives a part and collects two failed pieces; undoes the parts given. It then shows a disallowed status move being refused and moves the complaint through Awaiting material, Resolved and Closed. It files a second complaint and closes it as Not covered.
- **Search and stock:** global search for the complaint number and the new defective tag. Current stock shows the Defective store column, and its total leaves the column out.
- **Return batch:** creates a batch for one company, where a piece from another company is refused, and dispatches it. It settles one piece as Replaced (its Stock IN raises good stock) and one as Rejected (returned).
- **Reports and clean-up:** downloads the pending complaints, complaint list, defective list and dispatch list reports, then undoes the stock entries it can.

At 390px wide it checks that Home and Current stock don't scroll sideways, that the top bar has no hamburger (its section pills scroll sideways instead) and that Stock opens from its pill, then current stock, a complaint page, its Record visit page and the defective pieces list.

It can be run again and again. Each run works on its own new item, complaints and batch, and its docstring lists what a run leaves behind (reseed afterwards for clean demo data). It exits 0 only if every step passes and the browser logs no JS errors. Screenshots are saved as `e2e/screen-*.png` (git-ignored). On a failure it saves `e2e/screen-<width>-FAIL.png` and prints the failing step.

### Rigour suite

`e2e/rigour/` is a repeatable stress and scenario test driven by the legacy Excel files: it builds about 475 operations with an independent stock model, replays them through the real forms over HTTP, then audits the ledger (cache matches ledger, no negative stock, gap-free numbers, Defective store equals pieces) and runs concurrency, performance and UI checks. It drops and recreates its own `svkml_rigour` database. See [e2e/rigour/README.md](e2e/rigour/README.md) for how to run it.

---

## Production

Use `config.settings.prod` (the Docker image sets it by default). It refuses to start without `SECRET_KEY`, `DATABASE_URL` and `ALLOWED_HOSTS`, and it expects HTTPS behind a proxy that sets `X-Forwarded-Proto`. It turns on secure cookies, HSTS and the HTTPS redirect, and serves compressed, hashed static files with WhiteNoise.

Check the settings:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod uv run python manage.py check --deploy
```

The production image (`Dockerfile`) installs without dev dependencies, runs `collectstatic` at build time, runs as a non-root user and starts gunicorn with 2 workers on port 8000.

On every deploy, run migrations **before** the new code starts serving:

```bash
docker compose run --rm web python manage.py migrate
```

Then create the users with `seed_users` (first deploy only). Do not load demo data into production; `seed_service_demo` refuses unless you pass `--force`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `seed_users` rejects the password | `SEED_PASSWORD` must pass Django's validators: 8+ characters, not common, not all digits. |
| `seed_service_demo` refuses to run | It loads only into an empty database, only once, and only with `DEBUG` on. Reset the database first (see [Resetting the review database](#resetting-the-review-database)). |
| Stock totals look wrong | Run `uv run python manage.py rebuild_stock_balances`. It must print "Cache matches ledger." |
| "Can't edit or delete an entry" | By design: the ledger is append-only. Use **Undo** on the entry instead. |
| Undo is refused on an entry | Entries posted by the defectives screens can't be undone. Fix the piece or batch through the Defectives screens. |
| Walkthrough fails to launch a browser | Use Playwright **1.63.0** exactly and run `playwright install chromium` once. |
| Docker can't reach Postgres from the host | Compose publishes Postgres on host port **5433**, not 5432. |
| `ImproperlyConfigured` on start in production | Set `SECRET_KEY`, `DATABASE_URL` and `ALLOWED_HOSTS`. |

---

## Project history and docs

- The project restarted from scratch on 2026-10-11. The earlier work is kept, for reference only, in the git tags `archive/main-2026-10-11` and `archive/phase-2-2026-10-11`.
- Plans: `docs/superpowers/plans/` (stock system, defectives and complaints, design B).
- Specs: `docs/superpowers/specs/` (defectives and complaints design, smart features design).
- `tasks/todo.md` tracks progress, and `tasks/lessons.md` records the working rules learned along the way.
- `CLAUDE.md` holds the working notes for AI-assisted development.

---

## License

MIT. See [LICENSE](LICENSE).
