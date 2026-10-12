# SVKML Stock Management

A web app for SVKML Electrical Works (Wipro Lighting service partner, Visakhapatnam) that replaces the stock spreadsheets. Staff record Stock IN, Stock OUT, transfers between locations and count adjustments with proper forms. Every entry goes into an append-only ledger and is never edited or deleted: a mistake is cancelled with an Undo entry. On top of the ledger the app shows current stock per location, each item's history, the movements register, low-stock warnings and a global search that also finds old spellings of item codes. Five reports download as neatly formatted Excel files.

Built with Django 5.2, PostgreSQL 16, Tabler and Tom Select. There is no Node build step.

## Run it with Docker

```bash
cp .env.example .env        # then set SECRET_KEY and a strong SEED_PASSWORD
docker compose up -d --build
make migrate
make demo                   # users admin + office, demo items and ~5 weeks of stock history
```

Open http://localhost:8000 and log in as `office` or `admin` with your `SEED_PASSWORD`.

`make demo` only loads stock history into an empty ledger. It refuses to run a second time. It also refuses when `DEBUG` is off (production settings); to load demo data into such an environment on purpose, run `python manage.py seed_stock_demo --force`.

## Run it without Docker

You need Python 3.12, [uv](https://docs.astral.sh/uv/) and a PostgreSQL 16 server.

```bash
uv sync
export DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/svkml"
uv run python manage.py migrate
SEED_PASSWORD="<a strong password>" uv run python manage.py seed_users
uv run python manage.py seed_stock_demo     # optional demo data
uv run python manage.py runserver 8000
```

`SEED_PASSWORD` must pass Django's password validators. Existing users keep their passwords when `seed_users` runs again.

## Tests

```bash
DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/postgres" uv run pytest -q
uv run ruff format --check . && uv run ruff check .
```

Pytest creates its own test database.

## Browser walkthrough

With the dev server running on demo data:

```bash
uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office "<SEED_PASSWORD>"
```

The password can also come from the `E2E_PASSWORD` environment variable. The walkthrough logs in and goes through global search, Stock IN with a new item created from the picker, a refused over-issue, a transfer, an adjustment, and sorting and exporting current stock. It then undoes the adjustment, the transfer and the Stock IN, so it can be run again without draining stock, and checks the phone menu. It exits 0 only if every step passes and the browser logs no JS errors. Screenshots are saved as `e2e/screen-*.png` (git-ignored); on a failure it saves `e2e/screen-<width>-FAIL.png` and prints the failing step. Run `uv run --with playwright playwright install chromium` once first.

## Roles

| Role   | Can do |
|--------|--------|
| Admin  | Everything: all stock screens, items, masters (locations, companies, fitting types, spare types), users and the Django admin back office. |
| Office | Every stock screen (IN, OUT, transfer, adjust, undo, lists, exports) and create or edit items. |

Adjustments need a reason and a note. An undo needs a reason.

## Production

Use `config.settings.prod`. It needs `SECRET_KEY`, `DATABASE_URL` and `ALLOWED_HOSTS`, and expects HTTPS behind a proxy that sets `X-Forwarded-Proto`. Check it with:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod uv run python manage.py check --deploy
```

Run `python manage.py migrate` on every deploy, before the new code starts serving, e.g. `docker compose run --rm web python manage.py migrate`.
