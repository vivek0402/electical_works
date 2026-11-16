# SVKML Service

A web app for SVKML Electrical Works (a lighting service partner in Visakhapatnam) that replaces its stock, defective-pieces and complaint spreadsheets. It has three linked systems on one stock ledger:

- **Stock management.** Staff record Stock IN, Stock OUT, transfers between locations and count adjustments with proper forms. Every entry goes into an append-only ledger and is never edited or deleted: a mistake is cancelled with an Undo entry. On top of the ledger the app shows current stock per location, each item's history, the movements register, low-stock warnings and a global search that also finds old spellings of item codes.
- **Complaints.** Logs customer-site complaints with saved sites (mobile or landline phones) and technicians. A visit gives parts (a real Stock OUT) and collects failed parts. Each complaint moves through allowed statuses only (Not attended, Attended, Material need to check, Awaiting material, Resolved, Closed) or is closed as Not covered with a reason.
- **Defective pieces.** Every failed part gets its own tag (DEF-0001…), whether it is collected at a visit or marked defective from stock. It sits in a separate Defective store that is shown next to stock but never counted as good stock, and is tracked through a return batch for one company (draft, dispatched with courier and docket) to the company's answer: replaced or repaired (a Stock IN back into good stock), or rejected.

No company is special: Wipro Lighting is one company among several. Nine reports download as neatly formatted Excel files: five for stock (current stock, movements, item list, low stock, an item's history) and four for the service side (pending complaints, the complaint list, the defective list, a return batch's dispatch list).

Built with Django 5.2, PostgreSQL 16, Tabler and Tom Select. There is no Node build step.

## Run it with Docker

```bash
cp .env.example .env        # then set SECRET_KEY and a strong SEED_PASSWORD
docker compose up -d --build
make migrate
make demo                   # users admin + office; demo stock, complaints, visits, defective pieces, return batches
```

Open http://localhost:8000 and log in as `office` or `admin` with your `SEED_PASSWORD`.

`make demo` runs `seed_users`, then `seed_service_demo`, which replays the demo data through the app's own services: ~5 weeks of stock history, 26 complaints with their visits, 60 defective pieces and 3 return batches. It only loads into an empty database and refuses to run a second time. It also refuses when `DEBUG` is off (production settings); to load demo data into such an environment on purpose, run `python manage.py seed_service_demo --force`. (`seed_stock_demo` is the older stock-only demo; use one or the other, never both.)

## Run it without Docker

You need Python 3.12, [uv](https://docs.astral.sh/uv/) and a PostgreSQL 16 server.

```bash
uv sync
export DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/svkml"
uv run python manage.py migrate
SEED_PASSWORD="<a strong password>" uv run python manage.py seed_users
uv run python manage.py seed_service_demo   # optional demo data (stock + complaints + defectives), empty database only
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

With the dev server running on demo data (`seed_service_demo`):

```bash
PYTHONIOENCODING=utf-8 uv run --with playwright==1.63.0 python e2e/walkthrough.py http://127.0.0.1:8000 office "<SEED_PASSWORD>"
```

Playwright is pinned to 1.63.0 because newer releases need a newer browser build; run `uv run --with playwright==1.63.0 playwright install chromium` once first. The password can also come from the `E2E_PASSWORD` environment variable.

On a desktop-sized window the walkthrough goes through:
- **Stock:** global search, Stock IN with a new item created from the picker, a refused over-issue, a transfer, an adjustment, and sorting and exporting current stock.
- **Complaints:** marks a piece defective; files a complaint at a new site created from the site picker; records a visit that gives a part and collects two failed pieces; undoes the parts given. It then shows a disallowed status move being refused and moves the complaint through Awaiting material, Resolved and Closed. It files a second complaint and closes it as Not covered.
- **Search and stock:** global search for the complaint number and the new defective tag. Current stock shows the Defective store column, and its total leaves the column out.
- **Return batch:** creates a batch for one company, where a piece from another company is refused, and dispatches it. It settles one piece as Replaced (its Stock IN raises good stock) and one as Rejected (returned).
- **Reports and clean-up:** downloads the pending complaints, complaint list, defective list and dispatch list reports, then undoes the stock entries it can.

At 390px wide it checks that Home and Current stock don't scroll sideways, that the top bar has no hamburger (its section pills scroll sideways instead) and that Stock opens from its pill, then current stock, a complaint page, its Record visit page and the defective pieces list (no sideways scrolling).

It can be run again and again. Each run works on its own new item, complaints and batch, and its docstring lists what a run leaves behind. Re-seed the demo database afterwards if you want clean demo data. It exits 0 only if every step passes and the browser logs no JS errors. Screenshots are saved as `e2e/screen-*.png` (git-ignored). On a failure it saves `e2e/screen-<width>-FAIL.png` and prints the failing step.

## Roles

| Role   | Can do |
|--------|--------|
| Admin  | Everything: all stock, complaints and defectives screens, masters (locations, companies, fitting types, spare types), hiding sites and technicians, reopening a closed complaint, users and the Django admin back office. |
| Office | Every stock screen (IN, OUT, transfer, adjust, undo, lists, exports), every complaints and defectives screen (file complaints, record visits, mark defective, return batches, settle, exports), and adding and editing items, sites and technicians. |

Adjustments need a reason and a note. An undo needs a reason.

## Production

Use `config.settings.prod`. It needs `SECRET_KEY`, `DATABASE_URL` and `ALLOWED_HOSTS`, and expects HTTPS behind a proxy that sets `X-Forwarded-Proto`. Check it with:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod uv run python manage.py check --deploy
```

Run `python manage.py migrate` on every deploy, before the new code starts serving, e.g. `docker compose run --rm web python manage.py migrate`.
