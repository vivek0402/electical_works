# SVKML Stock Management System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the real, database-backed SVKML Stock Management web app that matches the approved clickable mockup (`mockups/stock/`) and `DESIGN.md`. It covers Stock IN / OUT / Transfer / Adjust, Undo, current stock, items, item history, movements, low stock, masters, global search, and four neatly formatted Excel exports.

**Architecture:** Django 5.2 LTS server-rendered app with function views. All business rules live in `apps/inventory/services.py` (writes) and `apps/inventory/selectors.py` (reads); views stay thin. Stock is an append-only ledger (`StockEntry` + `StockLine`, protected by database triggers via django-pgtrigger) with a rebuildable `StockBalance` cache that may never go negative (CHECK constraint plus row locks). The UI is Tabler (vendored) using the Navy & Amber palette from `DESIGN.md`. The item picker is Tom Select and charts are ApexCharts. There is no Node build step.

**Tech Stack:** Python 3.12, Django 5.2.18, PostgreSQL 16, psycopg 3, django-environ, django-pgtrigger, django-unfold (admin), XlsxWriter (exports), Tabler 1.6.1 + Tabler Icons 3.49.0 + Tom Select 2.6.2 + ApexCharts (vendored), pytest + pytest-django, ruff, uv.

---

## Decisions locked in (do not revisit while executing)

- **Users and roles:** two roles, `ADMIN` and `OFFICE` (Django Groups). Superusers count as ADMIN.
  - ADMIN can do everything.
  - OFFICE can use every stock screen and create or edit items.
  - **Masters (locations, companies, fitting types, spare types) and users are ADMIN-only.**
  - Adjustments are allowed for both roles, but a reason and a note are required.
- **No HTMX in v1.** Sorting, paging and filters are plain GET links and forms. Entry forms use a small vanilla JS file for the item lines. (YAGNI: the approved screens don't need partial swaps.)
- **No Postgres extensions.** Item search uses a stored look-alike key (`search_key`) plus `icontains`. Data is a few hundred items. This keeps tests runnable on a plain Postgres.
- **Units:** NOS, MTR, ROLL, BOX, PKT. Quantities are whole numbers.
- **Entry numbers:**
  - `IN-0001`, `OUT-0001`, `TRF-0001`, `ADJ-0001`, `REV-0001` (REV = Undo), allocated from an `EntryCounter` row locked inside the posting transaction.
  - Entries and lines are never edited or deleted. Undo posts a REV entry with a reason.
- **Dates** are DD-MM-YYYY everywhere (Django format module); the time zone is Asia/Kolkata. PKD is stored as the first day of the month and shown as MM-YYYY.
- **Colours (DESIGN.md):**
  - IN buttons `#2268c0`, OUT buttons `#c2410c`.
  - Chart pair: IN `#2a78d6`, OUT `#eb6834`.
  - Brand: primary `#1f5fbf`, sidebar `#0f2744`, amber logo `#f5b301`.

## Local test environment (this Windows machine has no Docker)

The controller provides a running PostgreSQL 16 and passes its URL to every subagent as `DATABASE_URL`, e.g. `postgresql://postgres:@127.0.0.1:5xxxx/postgres`. Run tests with:

```bash
DATABASE_URL="<url from controller>" uv run pytest -q
```

CI and Docker Compose use the `postgres:16-alpine` image, and `Makefile` targets wrap Docker Compose. On this machine, use the `uv run` commands above.

## File structure

```
pyproject.toml / uv.lock              dependencies (pinned), ruff + pytest config
.env.example / .gitignore / .gitattributes
Dockerfile / compose.yaml / Makefile / .github/workflows/ci.yml
manage.py
config/
  settings/base.py dev.py test.py prod.py
  formats/en/formats.py               DD-MM-YYYY formats
  urls.py wsgi.py
apps/
  core/
    views.py                          healthz
    tables.py                         sort + page helper for list screens
    excel.py                          shared XlsxWriter report writer
    templatetags/core_tags.py         url_with (keeps query params), qty filters
  accounts/
    roles.py decorators.py context_processors.py
    admin.py                          django-unfold User/Group admin
    management/commands/seed_users.py
  inventory/
    normalise.py                      code clean-up + look-alike key
    models.py                         masters, Item, ItemAlias, ledger, balances
    services.py                       ALL writes: items, entries, undo, rebuild
    selectors.py                      ALL reads: stock matrix, lists, history, dashboard
    forms.py                          header forms + line parsing
    views.py urls.py exports.py
    management/commands/seed_stock_demo.py
templates/
  base.html  registration/login.html
  core/_sort_th.html _pagination.html
  inventory/*.html
static/
  vendor/ (tabler, tom-select, apexcharts, icons)
  css/app.css
  js/entry-form.js  js/dashboard.js  js/app.js
tests/
  conftest.py factories.py
  core/ accounts/ inventory/
```

---

### Task 1: Project skeleton (settings, healthz, Docker, CI)

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.gitattributes`, `.env.example`, `manage.py`
- Create: `config/__init__.py`, `config/settings/__init__.py`, `config/settings/base.py`, `config/settings/dev.py`, `config/settings/test.py`, `config/settings/prod.py`
- Create: `config/formats/__init__.py`, `config/formats/en/__init__.py`, `config/formats/en/formats.py`
- Create: `config/urls.py`, `config/wsgi.py`
- Create: `apps/__init__.py`, `apps/core/__init__.py`, `apps/core/apps.py`, `apps/core/views.py`, `apps/core/urls.py`
- Create: `Dockerfile`, `compose.yaml`, `Makefile`, `.github/workflows/ci.yml`
- Test: `tests/__init__.py`, `tests/conftest.py`, `tests/core/__init__.py`, `tests/core/test_core.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "svkml"
version = "0.1.0"
description = "SVKML Electrical Works: stock management"
requires-python = ">=3.12,<3.13"
dependencies = [
    "django==5.2.18",
    "psycopg[binary]==3.3.6",
    "django-environ==0.14.0",
    "django-pgtrigger==4.17.0",
    "django-unfold==0.108.0",
    "xlsxwriter==3.2.9",
    "gunicorn==26.2.0",
    "whitenoise==6.12.0",
]

[dependency-groups]
dev = [
    "pytest==9.1.1",
    "pytest-django==4.14.0",
    "pytest-cov==7.1.0",
    "openpyxl==3.1.5",
    "ruff==0.17.0",
]

[tool.uv]
package = false

[tool.ruff]
line-length = 110
target-version = "py312"
extend-exclude = ["**/migrations/*", "mockups/*"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "DJ", "SIM"]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"
python_files = ["test_*.py"]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 2: Create `.gitignore`, `.gitattributes`, `.env.example`**

`.gitignore`:
```
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.env
.env.*
!.env.example
/media/
/staticfiles/
data/legacy/import_review*.xlsx
```

`.gitattributes`:
```
* text=auto eol=lf
*.xlsx binary
*.png binary
*.woff binary
*.woff2 binary
```

`.env.example`:
```
SECRET_KEY=change-me-to-a-long-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSRF_TRUSTED_ORIGINS=
DATABASE_URL=postgres://svkml:svkml@localhost:5433/svkml
SEED_PASSWORD=change-me
LOG_LEVEL=INFO
```

- [ ] **Step 3: Create `manage.py` and the settings package**

`manage.py`:
```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`config/__init__.py`, `config/settings/__init__.py`, `config/formats/__init__.py`, `config/formats/en/__init__.py`, `apps/__init__.py`, `apps/core/__init__.py`, `tests/__init__.py`, `tests/core/__init__.py`: empty files.

`config/settings/base.py`:
```python
"""Settings shared by every environment. Per-deploy values come from env / .env."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "pgtrigger",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL", default="postgres://svkml:svkml@localhost:5433/svkml")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# English UI, IST display, UTC storage, DD-MM-YYYY everywhere.
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
FORMAT_MODULE_PATH = ["config.formats"]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
```

`config/settings/dev.py`:
```python
from .base import *  # noqa: F403
from .base import SECRET_KEY, env

DEBUG = env.bool("DEBUG", default=True)
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-use-in-prod"
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])
```

`config/settings/test.py`:
```python
from .base import *  # noqa: F403
from .base import SECRET_KEY

DEBUG = False
SECRET_KEY = SECRET_KEY or "test-only-insecure-key"
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
WHITENOISE_AUTOREFRESH = True
```

`config/settings/prod.py`:
```python
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SECRET_KEY, STORAGES, env

DEBUG = False
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in production.")

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
```

`config/formats/en/formats.py`:
```python
# The client works in DD-MM-YYYY. Overrides Django's built-in "en" locale formats.
DATE_FORMAT = "d-m-Y"
SHORT_DATE_FORMAT = "d-m-Y"
DATETIME_FORMAT = "d-m-Y H:i"
SHORT_DATETIME_FORMAT = "d-m-Y H:i"
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]
DATETIME_INPUT_FORMATS = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M"]
FIRST_DAY_OF_WEEK = 1
```
(`%Y-%m-%d` comes first because `<input type="date">` posts ISO dates.)

- [ ] **Step 4: Create core app, URLs and WSGI**

`apps/core/apps.py`:
```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
```

`apps/core/views.py`:
```python
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def healthz(request):
    """Uptime probe: 200 if the app can reach the database, 503 otherwise."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "db": "unreachable"}, status=503)
    return JsonResponse({"status": "ok"})
```

`apps/core/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [path("healthz", views.healthz, name="healthz")]
```

`config/urls.py`:
```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
]
```

`config/wsgi.py`:
```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
application = get_wsgi_application()
```

- [ ] **Step 5: Write the failing tests**

`tests/conftest.py`:
```python
# Shared fixtures are added by later tasks.
```

`tests/core/test_core.py`:
```python
import datetime

import pytest
from django.template import Context, Template

pytestmark = pytest.mark.django_db


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dates_render_dd_mm_yyyy():
    out = Template("{{ d|date }}|{{ d|date:'SHORT_DATE_FORMAT' }}").render(Context({"d": datetime.date(2026, 5, 25)}))
    assert out == "25-05-2026|25-05-2026"
```

- [ ] **Step 6: Lock deps and run tests**

Run:
```bash
uv lock && uv sync
DATABASE_URL="<url>" uv run pytest -q
```
Expected: `2 passed`.

- [ ] **Step 7: Docker, Makefile and CI**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/opt/venv/bin:$PATH"
WORKDIR /app
ARG INSTALL_DEV=false
COPY pyproject.toml uv.lock ./
RUN if [ "$INSTALL_DEV" = "true" ]; then uv sync --frozen; else uv sync --frozen --no-dev; fi
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=collectstatic-only \
    python manage.py collectstatic --noinput \
 && useradd --create-home --uid 1000 app && mkdir -p /app/media \
 && chown -R app:app /app/media /app/staticfiles
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
```

`compose.yaml`:
```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: svkml
      POSTGRES_USER: svkml
      POSTGRES_PASSWORD: svkml
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U svkml -d svkml"]
      interval: 3s
      timeout: 3s
      retries: 20
  web:
    build:
      context: .
      args:
        INSTALL_DEV: "true"
    command: python manage.py runserver 0.0.0.0:8000
    env_file:
      - path: .env
        required: false
    environment:
      DATABASE_URL: postgres://svkml:svkml@db:5432/svkml
      COVERAGE_FILE: /tmp/.coverage
      PYTEST_ADDOPTS: -p no:cacheprovider
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
volumes:
  pgdata:
```

`Makefile` (recipe lines start with a TAB):
```make
COMPOSE = docker compose
RUN = $(COMPOSE) run --rm web

.PHONY: up down migrate seed demo test lint fmt shell

up:
	$(COMPOSE) up -d --build
down:
	$(COMPOSE) down
migrate:
	$(RUN) python manage.py migrate
seed:
	$(RUN) python manage.py seed_users
demo:
	$(RUN) python manage.py seed_users
	$(RUN) python manage.py seed_stock_demo
test:
	$(RUN) pytest --cov=apps --cov-report=term-missing $(ARGS)
lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .
fmt:
	$(RUN) ruff check --fix .
	$(RUN) ruff format .
shell:
	$(RUN) python manage.py shell
```

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-24.04
    services:
      db:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: svkml
          POSTGRES_USER: svkml
          POSTGRES_PASSWORD: svkml
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U svkml -d svkml"
          --health-interval 3s --health-timeout 3s --health-retries 20
    env:
      DATABASE_URL: postgres://svkml:svkml@localhost:5432/svkml
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          version: "0.11.16"
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run python manage.py makemigrations --check --dry-run
      - run: uv run pytest --cov=apps --cov-report=term-missing
```

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff format . && uv run ruff check .
git add -A -- pyproject.toml uv.lock .gitignore .gitattributes .env.example manage.py config apps tests Dockerfile compose.yaml Makefile .github
git commit -m "feat: Django 5.2 project skeleton with healthz, Docker, CI"
```

---

### Task 2: Accounts, roles, login page, static assets, admin

**Files:**
- Create: `apps/accounts/__init__.py`, `apps/accounts/apps.py`, `apps/accounts/roles.py`, `apps/accounts/decorators.py`, `apps/accounts/context_processors.py`, `apps/accounts/urls.py`, `apps/accounts/admin.py`
- Create: `apps/accounts/management/__init__.py`, `apps/accounts/management/commands/__init__.py`, `apps/accounts/management/commands/seed_users.py`
- Create: `templates/registration/login.html`
- Create (copy): `static/vendor/*` from `mockups/stock/vendor/*` (all files including `fonts/`), and `static/css/app.css` (content below)
- Modify: `config/settings/base.py` (INSTALLED_APPS, context processor), `config/urls.py`
- Test: `tests/accounts/__init__.py`, `tests/accounts/test_accounts.py`, `tests/factories.py`, `tests/conftest.py`

- [ ] **Step 1: Copy vendored front-end files**

```bash
mkdir -p static/vendor static/css static/js
cp -r mockups/stock/vendor/* static/vendor/
```
Expected files: `static/vendor/tabler.min.css`, `tabler.min.js`, `tabler-vendors.min.css`, `tabler-icons.min.css`, `fonts/tabler-icons.woff2`, `fonts/tabler-icons.woff`, `tom-select.complete.min.js`, `tom-select.bootstrap5.min.css`, `apexcharts.min.js`.

- [ ] **Step 2: Create `static/css/app.css`** (the approved mockup styles plus the Navy & Amber palette, without mockup-only parts)

```css
/* SVKML app styles on top of Tabler. Palette: DESIGN.md (Navy & Amber). */
:root {
  --c-in: #2a78d6; --c-out: #eb6834;
  --brand-sidebar: #0f2744; --brand-sidebar-text: #c9d6e8; --brand-sidebar-muted: #8ea3bf; --brand-sidebar-active: rgba(255,255,255,.10);
  --brand-mark-bg: #f5b301; --brand-mark-fg: #0f2744;
  --tblr-primary: #1f5fbf; --tblr-primary-rgb: 31, 95, 191; --tblr-primary-darken: #1a51a3; --tblr-primary-lt: #e8eef8;
  --tblr-link-color: #1f5fbf; --tblr-link-color-rgb: 31, 95, 191; --tblr-link-hover-color: #1a51a3;
  --tblr-body-bg: #f4f6fa; --tblr-bg-surface-secondary: #f4f6fa;
}
/* Sidebar */
.navbar-vertical { background: var(--brand-sidebar) !important; }
.navbar-vertical .nav-link, .navbar-vertical .navbar-brand, .navbar-vertical .brand-sub { color: var(--brand-sidebar-text) !important; }
.navbar-vertical .nav-link .nav-link-icon { color: var(--brand-sidebar-muted); }
.navbar-vertical .nav-section { padding: 1rem 1rem .35rem; font-size: .68rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--brand-sidebar-muted); list-style: none; }
.navbar-vertical .nav-link.active { background: var(--brand-sidebar-active); border-radius: .4rem; font-weight: 600; }
.brand { display: flex; align-items: center; gap: .5rem; font-weight: 700; font-size: 1.15rem; }
.brand-mark { width: 2rem; height: 2rem; border-radius: .5rem; display: inline-flex; align-items: center; justify-content: center; background: var(--brand-mark-bg); color: var(--brand-mark-fg); }
.brand-sub { font-weight: 400; opacity: .7; }
.text-in, .text-in i { color: #7fb3f0 !important; } .text-out, .text-out i { color: #f5a07c !important; }
/* Top bar + global search */
.topbar { border-bottom: 1px solid var(--tblr-border-color); }
.global-search { position: relative; width: min(30rem, 100%); }
.gresults { width: 100%; max-height: 24rem; overflow-y: auto; }
.gresults.show { display: block; }
.gresults .dropdown-item { white-space: normal; }
.bell-count { font-size: .65rem; min-width: 1.1rem; height: 1.1rem; padding: 0 .3rem; line-height: 1.1rem; top: .15rem; right: .1rem; }
.bell-count:empty { display: none; }
/* Buttons: colour only means something (IN blue, OUT orange, red = attention); everything else quiet */
.btn-primary { --tblr-btn-bg: var(--tblr-primary); --tblr-btn-border-color: var(--tblr-primary); --tblr-btn-hover-bg: var(--tblr-primary-darken); --tblr-btn-hover-border-color: var(--tblr-primary-darken); }
.btn-outline-primary { --tblr-btn-color: var(--tblr-primary); --tblr-btn-border-color: var(--tblr-primary); --tblr-btn-hover-bg: var(--tblr-primary); --tblr-btn-hover-border-color: var(--tblr-primary); }
.btn-in { --tblr-btn-bg: #2268c0; --tblr-btn-border-color: #2268c0; --tblr-btn-hover-bg: #1b56a0; --tblr-btn-hover-border-color: #1b56a0; --tblr-btn-color: #fff; --tblr-btn-hover-color: #fff; }
.btn-out { --tblr-btn-bg: #c2410c; --tblr-btn-border-color: #c2410c; --tblr-btn-hover-bg: #a3360a; --tblr-btn-hover-border-color: #a3360a; --tblr-btn-color: #fff; --tblr-btn-hover-color: #fff; }
.btn-quiet { --tblr-btn-bg: #fff; --tblr-btn-color: #1f2937; --tblr-btn-border-color: #d5dbe3; --tblr-btn-hover-bg: var(--tblr-primary-lt); --tblr-btn-hover-color: var(--tblr-primary); --tblr-btn-hover-border-color: var(--tblr-primary); }
.btn-quiet .ti { color: var(--tblr-primary); }
.btn > .ti, .page-title > .ti, .card-title > .ti, .alert .ti, .dropdown-item > .ti { margin-right: .35rem; }
.page-item.active .page-link { background: var(--tblr-primary); border-color: var(--tblr-primary); }
.form-selectgroup-input:checked + .form-selectgroup-label { border-color: var(--tblr-primary); color: var(--tblr-primary); background: var(--tblr-primary-lt); }
/* KPI icons */
.kpi-brand { background: var(--tblr-primary-lt); color: var(--tblr-primary); }
.kpi-alert { background: #fde8e8; color: #b42318; }
.kpi-ok { background: #e7f6ec; color: #1e7e34; }
/* Entry-type badges */
.badge-k { font-weight: 600; }
.k-IN { background: rgba(42,120,214,.12); color: #1f5fae; } .k-OUT { background: rgba(235,104,52,.14); color: #a8441b; }
.k-TRF { background: rgba(71,85,105,.12); color: #334155; } .k-ADJ { background: rgba(71,85,105,.12); color: #334155; }
.k-REV { background: #fde8e8; color: #b42318; }
.qty-in { color: #1f5fae; font-weight: 600; } .qty-out { color: #a8441b; font-weight: 600; }
/* Tables */
.code { font-family: var(--tblr-font-monospace); font-weight: 600; white-space: nowrap; }
.table td.num, .table th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.nowrap { white-space: nowrap; }
.zero { color: var(--tblr-gray-300); }
tr.undone td { text-decoration: line-through; opacity: .5; }
th a.sort { color: inherit; text-decoration: none; }
th a.sort::after { content: "↕"; opacity: .3; margin-left: .3rem; font-size: .75rem; }
th a.sort.asc::after { content: "↑"; opacity: .9; } th a.sort.desc::after { content: "↓"; opacity: .9; }
.quick a { min-height: 4.5rem; font-size: 1.05rem; }
.quick small { display: block; font-weight: 400; opacity: .85; font-size: .78rem; }
/* Entry lines: table on desktop, stacked cards on phones */
.lines-wrap { overflow: visible; }
.lines-table td { vertical-align: top; }
.lines-table .ts-wrapper { min-width: 18rem; }
.lines-table .ts-dropdown { min-width: 22rem; }
.lines-table .avail { padding-top: .45rem; font-size: .875rem; }
.line-meta { display: block; margin-top: .3rem; }
.ts-dropdown { z-index: 1065; }
.ts-dropdown .opt-code { font-weight: 700; font-family: var(--tblr-font-monospace); }
.ts-dropdown .opt-meta { display: block; font-size: .78rem; color: var(--tblr-secondary); }
.ts-dropdown .create { color: var(--c-in); font-weight: 600; }
@media (max-width: 767.98px) {
  .lines-table thead { display: none; }
  .lines-table tr { display: grid; grid-template-columns: 1fr 1fr; gap: .25rem .75rem; padding: .75rem 0; border-bottom: 1px solid var(--tblr-border-color); position: relative; }
  .lines-table td { display: block; border: 0 !important; padding: .15rem 0 !important; }
  .lines-table td.c-item { grid-column: 1 / -1; padding-right: 3rem !important; }
  .lines-table td.c-n { display: none; }
  .lines-table td.c-rm { position: absolute; top: .6rem; right: 0; }
  .lines-table td[data-label]::before { content: attr(data-label); display: block; font-size: .72rem; font-weight: 600; text-transform: uppercase; color: var(--tblr-secondary); }
  .lines-table .ts-wrapper { min-width: 0; }
  .global-search { width: 100%; }
}
.chart-box { min-height: 260px; }
.login-wrap { min-height: 100vh; display: flex; align-items: center; }
```

- [ ] **Step 3: Write the failing tests**

`tests/factories.py`:
```python
from django.contrib.auth.models import Group, User

PASSWORD = "test-pass-123"


def make_user(username, role=None, superuser=False):
    user = User.objects.create_user(username=username, password=PASSWORD, first_name=username.title())
    if superuser:
        user.is_staff = user.is_superuser = True
        user.save()
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user
```

`tests/conftest.py`:
```python
import pytest

from tests.factories import make_user


@pytest.fixture
def admin_user(db):
    return make_user("admin_t", "ADMIN", superuser=True)


@pytest.fixture
def office_user(db):
    return make_user("office_t", "OFFICE")


@pytest.fixture
def office_client(client, office_user):
    client.force_login(office_user)
    return client


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client
```

`tests/accounts/__init__.py`: empty.

`tests/accounts/test_accounts.py`:
```python
import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import PermissionDenied
from django.core.management import CommandError, call_command
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE, has_role
from tests.factories import PASSWORD

pytestmark = pytest.mark.django_db


@role_required(ADMIN)
def admin_only(request):
    return HttpResponse("ok")


def call(view, user):
    request = RequestFactory().get("/x")
    request.user = user
    return view(request)


def test_role_groups_exist():
    assert set(Group.objects.values_list("name", flat=True)) >= {"ADMIN", "OFFICE"}


def test_has_role(admin_user, office_user):
    assert has_role(office_user, OFFICE)
    assert not has_role(office_user, ADMIN)
    assert has_role(admin_user, OFFICE)  # admin may do everything
    assert not has_role(AnonymousUser(), OFFICE)


def test_role_required(admin_user, office_user):
    assert call(admin_only, admin_user).status_code == 200
    with pytest.raises(PermissionDenied):
        call(admin_only, office_user)
    response = call(admin_only, AnonymousUser())
    assert response.status_code == 302 and "/login/" in response.url


def test_seed_users_requires_password(monkeypatch):
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="SEED_PASSWORD"):
        call_command("seed_users")


def test_seed_users_idempotent(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "first-pass")
    call_command("seed_users")
    monkeypatch.setenv("SEED_PASSWORD", "second-pass")
    call_command("seed_users")
    assert User.objects.count() == 2
    admin = User.objects.get(username="admin")
    assert admin.is_superuser and admin.check_password("first-pass")
    assert User.objects.get(username="office").groups.filter(name="OFFICE").exists()


def test_login_page_and_flow(client, office_user):
    page = client.get("/login/")
    assert page.status_code == 200 and b"Sign in" in page.content
    bad = client.post("/login/", {"username": office_user.username, "password": "nope"})
    assert b"Wrong username or password" in bad.content
    good = client.post("/login/", {"username": office_user.username, "password": PASSWORD})
    assert good.status_code == 302


def test_admin_site_admin_only(admin_client, office_client):
    assert admin_client.get("/admin/").status_code == 200
    assert office_client.get("/admin/").status_code == 302
```

Run: `DATABASE_URL="<url>" uv run pytest tests/accounts -q`. Expected: FAIL (ImportError: apps.accounts).

- [ ] **Step 4: Implement accounts**

`apps/accounts/__init__.py`, `apps/accounts/management/__init__.py`, `apps/accounts/management/commands/__init__.py`: empty.

`apps/accounts/apps.py`:
```python
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from .roles import sync_role_groups

        # Re-applied after every migrate so permissions of new models are attached automatically.
        post_migrate.connect(sync_role_groups, sender=self)
```

`apps/accounts/roles.py`:
```python
"""The two roles, as Django Groups. Views enforce them with `role_required`."""

from django.contrib.auth.models import Group, Permission

ADMIN = "ADMIN"
OFFICE = "OFFICE"
ROLES = (ADMIN, OFFICE)


def sync_role_groups(**kwargs):
    """Create the role groups. ADMIN gets every model permission (for the Django admin). Idempotent."""
    for role in ROLES:
        group, _ = Group.objects.get_or_create(name=role)
        if role == ADMIN:
            group.permissions.set(Permission.objects.all())


def user_roles(user):
    if not user.is_authenticated:
        return set()
    if not hasattr(user, "_role_cache"):
        roles = set(user.groups.filter(name__in=ROLES).values_list("name", flat=True))
        if user.is_superuser:
            roles.add(ADMIN)
        user._role_cache = roles
    return user._role_cache


def has_role(user, *roles):
    """True if the user holds any of `roles`. ADMIN may do everything."""
    held = user_roles(user)
    return ADMIN in held or bool(held.intersection(roles))
```

`apps/accounts/decorators.py`:
```python
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .roles import has_role


def role_required(*roles):
    """Only logged-in users holding one of `roles` (ADMIN always passes)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, *roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
```

`apps/accounts/context_processors.py`:
```python
from .roles import ADMIN, has_role


def roles(request):
    return {"is_admin": has_role(request.user, ADMIN)}
```

`apps/accounts/urls.py`:
```python
from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
```

`apps/accounts/admin.py`:
```python
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

admin.site.site_header = "SVKML Stock · Admin"
admin.site.site_title = "SVKML Admin"
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ["username", "first_name", "last_name", "is_active"]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
```

`apps/accounts/management/commands/seed_users.py`:
```python
import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.roles import ADMIN, OFFICE, sync_role_groups

SEED_USERS = [("admin", "Admin", ADMIN, True), ("office", "Office", OFFICE, False)]


class Command(BaseCommand):
    help = "Create the role groups and the default users. Re-runnable: existing passwords are kept."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise CommandError("Set SEED_PASSWORD in the environment (.env) before seeding.")
        sync_role_groups()
        for username, first_name, role, superuser in SEED_USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"first_name": first_name})
            if created:
                user.set_password(password)
            user.is_staff = user.is_superuser = superuser
            user.save()
            user.groups.add(Group.objects.get(name=role))
            self.stdout.write(f"{username:<8} {role:<7} {'created' if created else 'exists'}")
```

`templates/registration/login.html`:
```html
{% load static %}<!doctype html>
<html lang="en-IN">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in · SVKML Stock</title>
  <link rel="stylesheet" href="{% static 'vendor/tabler.min.css' %}">
  <link rel="stylesheet" href="{% static 'vendor/tabler-icons.min.css' %}">
  <link rel="stylesheet" href="{% static 'css/app.css' %}">
</head>
<body>
  <div class="page page-center login-wrap"><div class="container container-tight py-4">
    <div class="text-center mb-4"><span class="brand justify-content-center"><span class="brand-mark"><i class="ti ti-bulb"></i></span> SVKML <span class="brand-sub">Stock</span></span></div>
    <div class="card card-md"><div class="card-body">
      <h2 class="h2 text-center mb-4">Sign in to your account</h2>
      {% if form.non_field_errors %}<div class="alert alert-danger" role="alert"><i class="ti ti-alert-circle"></i> Wrong username or password. Please try again.</div>{% endif %}
      <form method="post" autocomplete="off" novalidate>{% csrf_token %}
        <div class="mb-3"><label class="form-label" for="id_username">Username</label>
          <input id="id_username" name="username" class="form-control" autocomplete="username" autocapitalize="none" required autofocus value="{{ form.username.value|default:'' }}"></div>
        <div class="mb-3"><label class="form-label" for="id_password">Password</label>
          <input id="id_password" type="password" name="password" class="form-control" autocomplete="current-password" required></div>
        <input type="hidden" name="next" value="{{ next }}">
        <button type="submit" class="btn btn-primary w-100">Sign in</button>
      </form>
    </div></div>
  </div></div>
</body>
</html>
```

Modify `config/settings/base.py`: put `"unfold"` **first** in INSTALLED_APPS, add `"apps.accounts"` after `"apps.core"`, and add `"apps.accounts.context_processors.roles"` to the context processors list.

Modify `config/urls.py`:
```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
]
```

- [ ] **Step 5: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q          # expected: all pass (9 tests)
uv run ruff format . && uv run ruff check .
git add apps/accounts templates static config tests
git commit -m "feat: ADMIN/OFFICE roles, login page, unfold admin, vendored Tabler assets"
```

---

### Task 3: Inventory masters, Item model, code normalisation

**Files:**
- Create: `apps/inventory/__init__.py`, `apps/inventory/apps.py`, `apps/inventory/normalise.py`, `apps/inventory/models.py`
- Create: `apps/inventory/migrations/__init__.py`, generated `0001_initial.py`, hand-written `0002_seed_masters.py`
- Modify: `config/settings/base.py` (add `"apps.inventory"` after `"apps.accounts"`)
- Test: `tests/inventory/__init__.py`, `tests/inventory/test_normalise.py`, `tests/inventory/test_masters.py`

- [ ] **Step 1: Write failing tests**

`tests/inventory/test_normalise.py`:
```python
import pytest

from apps.inventory.normalise import normalise_code, search_key


@pytest.mark.parametrize("raw, expected", [
    ("  lg26-048-0720 ", "LG26-048-0720"), ("`EIO6006", "EIO6006"),
    ("ISENSE  8BUTTON  SWITCH", "ISENSE 8BUTTON SWITCH"), ("15WATT (190Ma)", "15WATT (190MA)"), (None, ""),
])
def test_normalise_code(raw, expected):
    assert normalise_code(raw) == expected


@pytest.mark.parametrize("a, b", [
    ("LG26-048-0720", "LG26-048-720"), ("R1103-092-PA", "RI103-092-PA"),
    ("EIO8437", "EI08437"), ("LL20-111-XXX-65NE3", "LL20-111-XXX-65-NE3"),
])
def test_lookalikes_share_key(a, b):
    assert search_key(a) == search_key(b)


@pytest.mark.parametrize("a, b", [("LG76-150-700", "LG76-150-700FH"), ("EUM-240S105D13", "EUM-240S105DB")])
def test_distinct_codes_keep_distinct_keys(a, b):
    assert search_key(a) != search_key(b)
```

`tests/inventory/test_masters.py`:
```python
import pytest
from django.db import IntegrityError, transaction

from apps.inventory.models import Company, FittingType, Item, Location, SpareType

pytestmark = pytest.mark.django_db


def test_masters_seeded():
    assert set(Location.objects.values_list("name", flat=True)) == {"Vizag Office", "Svkml", "TV Shop", "Kartika Class"}
    assert Company.objects.filter(name="Wipro Lighting").exists()
    assert SpareType.objects.filter(name="Driver").exists()
    assert FittingType.objects.filter(name="Flood light").exists()


def test_item_code_must_be_upper_and_unique():
    st, co = SpareType.objects.get(name="Driver"), Company.objects.get(name="Wipro Lighting")
    Item.objects.create(code="LG78-150-700", search_key="LG78150700", spare_type=st, company=co)
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="lg78-150-701", search_key="x", spare_type=st, company=co)
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="LG78-150-700", search_key="y", spare_type=st, company=co)
```

`tests/inventory/__init__.py`: empty. Run: expected FAIL (ImportError).

- [ ] **Step 2: Implement `normalise.py`**

```python
"""Pure helpers to clean item codes typed in many ways (old spellings, typos)."""

import re

LEADING_ZEROS = re.compile(r"(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)")
NON_ALNUM = re.compile(r"[^A-Z0-9]")
LOOKALIKES = str.maketrans({"O": "0", "I": "1"})


def normalise_code(raw) -> str:
    """Stored form of a code: upper-case, trimmed, single spaces, no quote/backtick junk."""
    if raw is None:
        return ""
    code = str(raw).upper().replace("`", "").replace("'", "").replace('"', "")
    return re.sub(r"\s+", " ", code).strip(" .,;:")


def search_key(code) -> str:
    """Look-alike key: O->0, I->1, leading zeros dropped per number, symbols removed.

    EIO8437 == EI08437, LG26-048-0720 == LG26-048-720. Used for duplicate detection and search only.
    """
    key = normalise_code(code).translate(LOOKALIKES)
    key = LEADING_ZEROS.sub(r"\1\2", key)
    return NON_ALNUM.sub("", key)
```

- [ ] **Step 3: Implement models (masters + Item + ItemAlias)**

`apps/inventory/apps.py`:
```python
from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = "apps.inventory"
    label = "inventory"
```

`apps/inventory/models.py`:
```python
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Upper


class Master(models.Model):
    """Simple named list managed by admins. Deactivate, never delete, once used."""

    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Location(Master):
    pass


class Company(Master):
    """Supplier / manufacturer / brand (Wipro Lighting, Finolex Cables, local traders...)."""

    class Meta(Master.Meta):
        verbose_name_plural = "companies"


class FittingType(Master):
    pass


class SpareType(Master):
    pass


class Unit(models.TextChoices):
    NOS = "NOS", "NOS"
    MTR = "MTR", "MTR"
    ROLL = "ROLL", "ROLL"
    BOX = "BOX", "BOX"
    PKT = "PKT", "PKT"


class Item(models.Model):
    """A spare (driver, PCB, lens, complete fitting, wire...) with its own code, and the fitting it belongs to."""

    code = models.CharField(max_length=80, unique=True)
    search_key = models.CharField(max_length=80, db_index=True)
    spare_type = models.ForeignKey(SpareType, on_delete=models.PROTECT)
    description = models.CharField(max_length=200, blank=True)
    cat_ref = models.CharField("used in fitting (product cat ref)", max_length=80, blank=True)
    fitting_type = models.ForeignKey(FittingType, on_delete=models.PROTECT, null=True, blank=True)
    wattage_w = models.PositiveSmallIntegerField(null=True, blank=True)
    current_ma = models.PositiveSmallIntegerField(null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    unit = models.CharField(max_length=4, choices=Unit.choices, default=Unit.NOS)
    reorder_level = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(condition=Q(code=Upper(F("code"))) & ~Q(code=""), name="item_code_normalised"),
        ]

    def __str__(self):
        return self.code


class ItemAlias(models.Model):
    """Another spelling of an item's code (e.g. EI08437 for EIO8437)."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=80, unique=True)
    search_key = models.CharField(max_length=80, db_index=True)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "item aliases"

    def __str__(self):
        return self.alias
```
(`settings` import is used by Task 4; keep it.)

- [ ] **Step 4: Generate migration and write the seed migration**

```bash
DATABASE_URL="<url>" uv run python manage.py makemigrations inventory -n initial
```

`apps/inventory/migrations/0002_seed_masters.py`:
```python
from django.db import migrations

SEED = {
    "Location": ["Vizag Office", "Svkml", "TV Shop", "Kartika Class"],
    "Company": ["Wipro Lighting", "Finolex Cables", "Havells", "Sri Sai Electricals", "Lakshmi Traders"],
    "FittingType": ["Flood light", "Linear / batten", "Street light", "High bay", "Downlight", "Well glass",
                    "Bulkhead", "Panel"],
    "SpareType": ["Driver", "PCB / LED module", "Lens", "Complete fitting", "Controller", "Switch",
                  "Wire / cable", "Accessory", "Other"],
}


def seed(apps, schema_editor):
    for model, names in SEED.items():
        Model = apps.get_model("inventory", model)
        for name in names:
            Model.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    for model, names in SEED.items():
        apps.get_model("inventory", model).objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
```

- [ ] **Step 5: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q     # expected: all pass
uv run ruff format . && uv run ruff check .
git add apps/inventory config tests
git commit -m "feat: inventory masters, Item/ItemAlias models, code normalisation"
```

---
### Task 4: Stock ledger models and posting services

**Files:**
- Modify: `apps/inventory/models.py` (append ledger models)
- Create: generated migration `0003_ledger.py`, hand-written `0004_seed_counters.py`
- Create: `apps/inventory/services.py`, `apps/inventory/management/__init__.py`, `apps/inventory/management/commands/__init__.py`, `apps/inventory/management/commands/rebuild_stock_balances.py`
- Modify: `tests/factories.py` (add `make_item`, `loc`)
- Test: `tests/inventory/test_stock_services.py`

- [ ] **Step 1: Append ledger models to `apps/inventory/models.py`**

Add `import pgtrigger` at the top with the other imports, then append:
```python
class EntryKind(models.TextChoices):
    IN = "IN", "Stock IN"
    OUT = "OUT", "Stock OUT"
    TRF = "TRF", "Transfer"
    ADJ = "ADJ", "Adjustment"
    REV = "REV", "Undo"


class InSource(models.TextChoices):
    SUPPLIER = "SUPPLIER", "From supplier"
    RETURN = "RETURN", "Returned unused from site"
    OPENING = "OPENING", "Opening stock"


class OutTarget(models.TextChoices):
    SITE = "SITE", "Site / customer"
    TECH = "TECH", "Technician"
    OTHER = "OTHER", "Other"


class AdjustReason(models.TextChoices):
    COUNT = "COUNT", "Physical count"
    DAMAGED = "DAMAGED", "Damaged"
    LOST = "LOST", "Lost"
    FOUND = "FOUND", "Found"
    OTHER = "OTHER", "Other"


class EntryCounter(models.Model):
    """Last number used per entry kind (IN-0007 ...). Locked while posting."""

    kind = models.CharField(max_length=3, primary_key=True, choices=EntryKind.choices)
    last = models.PositiveIntegerField(default=0)


IMMUTABLE = pgtrigger.Protect(name="append_only", operation=pgtrigger.Update | pgtrigger.Delete)


class StockEntry(models.Model):
    """One stock event (a receipt, an issue, a transfer, a count correction, an undo). Never edited."""

    number = models.CharField(max_length=12, unique=True)
    kind = models.CharField(max_length=3, choices=EntryKind.choices)
    subtype = models.CharField(max_length=10, blank=True)  # InSource for IN, OutTarget for OUT
    entry_date = models.DateField()
    party = models.CharField("supplier / issued to", max_length=120, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, null=True, blank=True)
    ref = models.CharField("DC / ref no.", max_length=60, blank=True)
    reason = models.CharField(max_length=10, choices=AdjustReason.choices, blank=True)
    note = models.TextField(blank=True)
    reverses = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-id"]
        indexes = [models.Index(fields=["kind", "entry_date"], name="entry_kind_date_idx")]
        triggers = [IMMUTABLE]

    def __str__(self):
        return self.number

    @property
    def details(self):
        """Short human description, e.g. 'From supplier', 'To site / customer', 'Damaged', 'Undo of OUT-0003'."""
        if self.kind == EntryKind.IN:
            return InSource(self.subtype).label if self.subtype else ""
        if self.kind == EntryKind.OUT:
            return f"To {OutTarget(self.subtype).label.lower()}" if self.subtype else ""
        if self.kind == EntryKind.TRF:
            return "Between locations"
        if self.kind == EntryKind.ADJ:
            return self.get_reason_display()
        return f"Undo of {self.reverses.number}" if self.reverses_id else "Undo"


class StockLine(models.Model):
    """Signed quantity of an item into (+) or out of (-) a location. Never edited."""

    entry = models.ForeignKey(StockEntry, on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="lines")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="lines")
    qty = models.IntegerField()
    batch_code = models.CharField(max_length=40, blank=True)
    pkd = models.DateField("packed (month)", null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=~Q(qty=0), name="line_qty_nonzero")]
        indexes = [models.Index(fields=["item", "location"], name="line_item_loc_idx")]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.qty:+d} {self.item} @ {self.location}"


class StockBalance(models.Model):
    """Cached stock per item and location. Rebuildable from StockLine; can never go negative."""

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="balances")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="balances")
    qty = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "location"], name="one_balance_row"),
            models.CheckConstraint(condition=Q(qty__gte=0), name="balance_never_negative"),
        ]

    def __str__(self):
        return f"{self.item} @ {self.location}: {self.qty}"
```

- [ ] **Step 2: Migrations**

```bash
DATABASE_URL="<url>" uv run python manage.py makemigrations inventory -n ledger
```

`apps/inventory/migrations/0004_seed_counters.py`:
```python
from django.db import migrations

KINDS = ["IN", "OUT", "TRF", "ADJ", "REV"]


def seed(apps, schema_editor):
    Counter = apps.get_model("inventory", "EntryCounter")
    for kind in KINDS:
        Counter.objects.get_or_create(kind=kind)


def unseed(apps, schema_editor):
    apps.get_model("inventory", "EntryCounter").objects.filter(kind__in=KINDS).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_ledger")]
    operations = [migrations.RunPython(seed, unseed)]
```

- [ ] **Step 3: Extend `tests/factories.py`** (append)

```python
from apps.inventory.models import Company, Item, Location, SpareType  # noqa: E402
from apps.inventory.normalise import search_key  # noqa: E402


def loc(name="Vizag Office"):
    return Location.objects.get(name=name)


def make_item(code, unit="NOS", reorder=0, spare_type="Driver", company="Wipro Lighting", **extra):
    return Item.objects.create(code=code, search_key=search_key(code), unit=unit, reorder_level=reorder,
                               spare_type=SpareType.objects.get(name=spare_type),
                               company=Company.objects.get(name=company), **extra)
```

- [ ] **Step 4: Write the failing tests** — `tests/inventory/test_stock_services.py`

```python
import datetime
import io
import threading

import pytest
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from apps.inventory.models import AdjustReason, EntryKind, StockBalance, StockEntry, StockLine
from apps.inventory.services import Line, StockError, adjust_counts, balance_drift, post_entry, undo_entry
from tests.factories import loc, make_item, make_user

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def user(db):
    return make_user("clerk", "OFFICE")


@pytest.fixture
def pcb(db):
    return make_item("EIO6006", spare_type="PCB / LED module")


def qty(item, name="Vizag Office"):
    row = StockBalance.objects.filter(item=item, location=loc(name)).first()
    return row.qty if row else 0


def post(kind, *lines, user, **kw):
    return post_entry(kind=kind, entry_date=TODAY, lines=list(lines), user=user, **kw)


def test_stock_in_and_numbering(pcb, user):
    first = post(EntryKind.IN, Line(pcb, loc(), 11), user=user, subtype="OPENING")
    second = post(EntryKind.IN, Line(pcb, loc(), 7), user=user, subtype="SUPPLIER")
    assert (first.number, second.number) == ("IN-0001", "IN-0002")
    assert qty(pcb) == 18


def test_out_cannot_go_negative_and_saves_nothing(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 7), user=user)
    with pytest.raises(StockError) as err:
        post(EntryKind.OUT, Line(pcb, loc(), -8), user=user)
    assert err.value.message == "Only 7 NOS of EIO6006 at Vizag Office."
    assert qty(pcb) == 7 and StockEntry.objects.count() == 1


def test_unit_appears_in_message(user):
    wire = make_item("WIRE 1.5 SQMM", unit="MTR", spare_type="Wire / cable")
    post(EntryKind.IN, Line(wire, loc(), 40), user=user)
    with pytest.raises(StockError, match="Only 40 MTR of WIRE 1.5 SQMM at Vizag Office."):
        post(EntryKind.OUT, Line(wire, loc(), -50), user=user)


@pytest.mark.parametrize("kind, sign, message", [
    (EntryKind.IN, -1, "Stock IN can only add"),
    (EntryKind.OUT, 1, "Stock OUT can only remove"),
])
def test_sign_rules(pcb, user, kind, sign, message):
    with pytest.raises(StockError, match=message):
        post(kind, Line(pcb, loc(), 3 * sign), user=user)


def test_future_date_refused(pcb, user):
    with pytest.raises(StockError, match="future"):
        post_entry(kind=EntryKind.IN, entry_date=TODAY + datetime.timedelta(days=1), lines=[Line(pcb, loc(), 1)], user=user)


def test_transfer_rules(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="exactly what it puts in"):
        post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 3), user=user)
    with pytest.raises(StockError, match="two different locations"):
        post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc(), 4), user=user)
    post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    assert (qty(pcb), qty(pcb, "TV Shop")) == (6, 4)


def test_adjust_counts_needs_reason_and_note(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="reason"):
        adjust_counts(entry_date=TODAY, location=loc(), counts=[(pcb, 9)], reason="", note="x", user=user)
    with pytest.raises(StockError, match="note"):
        adjust_counts(entry_date=TODAY, location=loc(), counts=[(pcb, 9)], reason=AdjustReason.DAMAGED, note=" ", user=user)
    with pytest.raises(StockError, match="match the system"):
        adjust_counts(entry_date=TODAY, location=loc(), counts=[(pcb, 10)], reason=AdjustReason.COUNT, note="ok", user=user)
    entry = adjust_counts(entry_date=TODAY, location=loc(), counts=[(pcb, 9)], reason=AdjustReason.DAMAGED,
                          note="1 cracked", user=user)
    assert entry.number == "ADJ-0001" and qty(pcb) == 9 and entry.lines.get().qty == -1


def test_undo_rules(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    with pytest.raises(StockError, match="reason"):
        undo_entry(entry=receipt, reason=" ", user=user)
    rev = undo_entry(entry=receipt, reason="wrong item", user=user)
    assert rev.number == "REV-0001" and rev.reverses == receipt and qty(pcb) == 0
    assert receipt.reversed_by == rev
    with pytest.raises(StockError, match="already undone"):
        undo_entry(entry=receipt, reason="again", user=user)
    with pytest.raises(StockError, match="can't be undone"):
        undo_entry(entry=rev, reason="x", user=user)


def test_undo_refused_when_stock_already_used(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    post(EntryKind.OUT, Line(pcb, loc(), -3), user=user)
    with pytest.raises(StockError, match="already been used"):
        undo_entry(entry=receipt, reason="mistake", user=user)


def test_ledger_is_append_only(pcb, user):
    entry = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    line = entry.lines.get()
    for sql, pk in [(f"UPDATE {StockLine._meta.db_table} SET qty = 50 WHERE id = %s", line.pk),
                    (f"DELETE FROM {StockLine._meta.db_table} WHERE id = %s", line.pk),
                    (f"UPDATE {StockEntry._meta.db_table} SET ref = 'x' WHERE id = %s", entry.pk)]:
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, [pk])


def test_balance_check_constraint(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 1), user=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        StockBalance.objects.filter(item=pcb).update(qty=-1)


def test_rebuild_matches_cache(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    assert balance_drift() == []
    StockBalance.objects.filter(location=loc("TV Shop")).update(qty=99)
    assert len(balance_drift()) == 1
    out = io.StringIO()
    call_command("rebuild_stock_balances", "--fix", stdout=out)
    assert "Rebuilt" in out.getvalue() and balance_drift() == [] and qty(pcb, "TV Shop") == 4


@pytest.mark.django_db(transaction=True)
def test_two_people_cannot_oversell():
    clerk = make_user("clerk2", "OFFICE")
    item = make_item("EIO9326", spare_type="PCB / LED module")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(item, loc(), 7)], user=clerk)
    barrier, results = threading.Barrier(2), []

    def issue():
        try:
            barrier.wait()
            post_entry(kind=EntryKind.OUT, entry_date=TODAY, lines=[Line(item, loc(), -5)], user=clerk)
            results.append("ok")
        except StockError:
            results.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=issue) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "refused"]
    assert StockBalance.objects.get(item=item).qty == 2
```

Run: `DATABASE_URL="<url>" uv run pytest tests/inventory/test_stock_services.py -q`. Expected: FAIL (ImportError: services).

- [ ] **Step 5: Implement `apps/inventory/services.py`**

```python
"""All writes to items and stock. Views, forms and commands call these; nothing else touches the ledger."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from functools import reduce
from operator import or_

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import EntryCounter, EntryKind, Item, Location, StockBalance, StockEntry, StockLine


class StockError(ValidationError):
    """A stock rule was broken. The message is safe to show to staff as-is."""


@dataclass(frozen=True)
class Line:
    item: Item
    location: Location
    qty: int  # + into the location, - out of it
    batch_code: str = ""
    pkd: date | None = None


def _validate(kind, entry_date, lines, reason, note):
    if not lines:
        raise StockError("Add at least one item.")
    if entry_date > timezone.localdate():
        raise StockError("The date can't be in the future.")
    for line in lines:
        if not isinstance(line.qty, int) or line.qty == 0:
            raise StockError(f"Quantity for {line.item.code} must be a whole number, not zero.")
    label = EntryKind(kind).label
    if kind == EntryKind.IN and any(line.qty < 0 for line in lines):
        raise StockError(f"{label} can only add stock.")
    if kind == EntryKind.OUT and any(line.qty > 0 for line in lines):
        raise StockError(f"{label} can only remove stock.")
    if kind == EntryKind.TRF:
        net = defaultdict(int)
        for line in lines:
            net[line.item.pk] += line.qty
        if any(net.values()):
            raise StockError("A transfer must take out exactly what it puts in.")
        if len({line.location.pk for line in lines}) < 2:
            raise StockError("A transfer needs two different locations.")
    if kind == EntryKind.ADJ:
        if not reason:
            raise StockError("Choose the reason for the adjustment.")
        if not note.strip():
            raise StockError("Write a short note explaining the adjustment.")


def _lock_balances(keys):
    """Make sure balance rows exist, then lock them in a fixed order (avoids deadlocks)."""
    StockBalance.objects.bulk_create(
        [StockBalance(item_id=i, location_id=loc, qty=0) for i, loc in keys], ignore_conflicts=True
    )
    match = reduce(or_, (Q(item_id=i, location_id=loc) for i, loc in keys))
    rows = StockBalance.objects.select_for_update().filter(match).order_by("item_id", "location_id")
    return {(r.item_id, r.location_id): r for r in rows}


def _next_number(kind):
    counter = EntryCounter.objects.select_for_update().get(kind=kind)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"{kind}-{counter.last:04d}"


@transaction.atomic
def post_entry(*, kind, entry_date, lines, user, subtype="", party="", company=None, ref="", reason="", note="",
               reverses=None) -> StockEntry:
    """Post a stock entry. Raises StockError (and saves nothing) if a rule is broken or stock would go negative."""
    if kind != EntryKind.REV:
        _validate(kind, entry_date, lines, reason, note)
    deltas = defaultdict(int)
    for line in lines:
        deltas[(line.item.pk, line.location.pk)] += line.qty
    keys = sorted(deltas)
    balances = _lock_balances(keys)
    items = {line.item.pk: line.item for line in lines}
    places = {line.location.pk: line.location for line in lines}
    for key in keys:
        new_qty = balances[key].qty + deltas[key]
        if new_qty < 0:
            item, place = items[key[0]], places[key[1]]
            raise StockError(f"Only {balances[key].qty} {item.unit} of {item.code} at {place.name}.")
        balances[key].qty = new_qty
    entry = StockEntry.objects.create(
        number=_next_number(kind), kind=kind, subtype=subtype, entry_date=entry_date, party=party.strip(),
        company=company, ref=ref.strip(), reason=reason, note=note.strip(), reverses=reverses, created_by=user,
    )
    StockLine.objects.bulk_create(
        StockLine(entry=entry, item=line.item, location=line.location, qty=line.qty, batch_code=line.batch_code,
                  pkd=line.pkd)
        for line in lines
    )
    StockBalance.objects.bulk_update([balances[k] for k in keys], ["qty", "updated_at"])
    return entry


@transaction.atomic
def adjust_counts(*, entry_date, location, counts, reason, note, user) -> StockEntry:
    """Set the counted quantity for each (item, counted) at one location; posts only the differences."""
    if not reason:
        raise StockError("Choose the reason for the adjustment.")
    if not note.strip():
        raise StockError("Write a short note explaining the adjustment.")
    keys = sorted({(item.pk, location.pk) for item, _ in counts})
    if not keys:
        raise StockError("Add at least one item.")
    balances = _lock_balances(keys)
    lines = [Line(item, location, counted - balances[(item.pk, location.pk)].qty) for item, counted in counts]
    lines = [line for line in lines if line.qty]
    if not lines:
        raise StockError("The counted quantities match the system. Nothing to adjust.")
    return post_entry(kind=EntryKind.ADJ, entry_date=entry_date, lines=lines, user=user, reason=reason, note=note)


@transaction.atomic
def undo_entry(*, entry, reason, user, entry_date=None) -> StockEntry:
    """Cancel an entry by posting its exact opposite. Both stay on record."""
    entry = StockEntry.objects.select_for_update().get(pk=entry.pk)
    if entry.kind == EntryKind.REV:
        raise StockError("An undo can't be undone. Make a new entry instead.")
    if StockEntry.objects.filter(reverses=entry).exists():
        raise StockError("This entry was already undone.")
    if not reason.strip():
        raise StockError("Please give a reason.")
    lines = [Line(line.item, line.location, -line.qty, line.batch_code, line.pkd)
             for line in entry.lines.select_related("item", "location")]
    try:
        return post_entry(kind=EntryKind.REV, entry_date=entry_date or timezone.localdate(), lines=lines, user=user,
                          party=entry.party, ref=entry.ref, note=reason, reverses=entry)
    except StockError as exc:
        raise StockError(f"{exc.message} That stock has already been used, so this entry can't be undone.") from exc


@transaction.atomic
def rebuild_balances() -> int:
    """Recompute the StockBalance cache from the ledger. Returns the number of rows."""
    with connection.cursor() as cursor:
        cursor.execute(f"LOCK TABLE {StockBalance._meta.db_table} IN EXCLUSIVE MODE")
    StockBalance.objects.all().delete()
    totals = list(StockLine.objects.values("item_id", "location_id").annotate(total=Sum("qty")))
    StockBalance.objects.bulk_create(
        StockBalance(item_id=t["item_id"], location_id=t["location_id"], qty=t["total"]) for t in totals
    )
    return len(totals)


def balance_drift():
    """[(item_id, location_id, cached, ledger)] where the cache disagrees with the ledger."""
    ledger = {(t["item_id"], t["location_id"]): t["total"]
              for t in StockLine.objects.values("item_id", "location_id").annotate(total=Sum("qty"))}
    cached = {(b.item_id, b.location_id): b.qty for b in StockBalance.objects.all()}
    return [(*key, cached.get(key, 0), ledger.get(key, 0)) for key in sorted(set(ledger) | set(cached))
            if cached.get(key, 0) != ledger.get(key, 0)]
```

`apps/inventory/management/__init__.py`, `apps/inventory/management/commands/__init__.py`: empty.

`apps/inventory/management/commands/rebuild_stock_balances.py`:
```python
from django.core.management.base import BaseCommand

from apps.inventory.services import balance_drift, rebuild_balances


class Command(BaseCommand):
    help = "Report (and with --fix, rebuild) the stock balance cache from the ledger."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true")

    def handle(self, *args, fix=False, **options):
        drift = balance_drift()
        for item_id, location_id, cached, ledger in drift:
            self.stdout.write(f"item={item_id} location={location_id}: cache {cached} != ledger {ledger}")
        if not drift:
            self.stdout.write(self.style.SUCCESS("Cache matches ledger."))
        elif fix:
            self.stdout.write(self.style.SUCCESS(f"Rebuilt {rebuild_balances()} balance rows."))
        else:
            self.stdout.write(self.style.WARNING(f"{len(drift)} mismatches. Re-run with --fix."))
```

- [ ] **Step 6: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q     # expected: all pass
uv run ruff format . && uv run ruff check .
git add apps/inventory tests
git commit -m "feat: append-only stock ledger with posting, adjust, undo and rebuild services"
```

---

### Task 5: Item services (find, save with look-alike checks, search)

**Files:**
- Modify: `apps/inventory/services.py` (append item services)
- Test: `tests/inventory/test_item_services.py`

- [ ] **Step 1: Write failing tests** — `tests/inventory/test_item_services.py`

```python
import pytest
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, ItemAlias, SpareType
from apps.inventory.services import ItemError, Line, find_item_by_code, post_entry, save_item, search_items
from tests.factories import loc, make_user

pytestmark = pytest.mark.django_db


def data(**over):
    base = {"code": "EIO8437", "spare_type": SpareType.objects.get(name="PCB / LED module"), "description": "LED module",
            "cat_ref": "ld81-171-xxx-60-xx", "fitting_type": None, "wattage_w": None, "current_ma": None,
            "company": Company.objects.get(name="Wipro Lighting"), "unit": "NOS", "reorder_level": 5,
            "aliases": ["ei08437"], "is_active": True}
    base.update(over)
    return base


def test_save_item_normalises_and_stores_aliases():
    item = save_item(data=data(code=" eio8437 "))
    assert item.code == "EIO8437" and item.cat_ref == "LD81-171-XXX-60-XX" and item.search_key == "E108437"
    assert list(item.aliases.values_list("alias", flat=True)) == ["EI08437"]


def test_find_by_code_exact_alias_and_lookalike():
    item = save_item(data=data())
    assert find_item_by_code("eio8437") == item
    assert find_item_by_code("EI08437") == item          # stored alias
    assert find_item_by_code("EI0-8437") == item         # look-alike key
    assert find_item_by_code("NOPE") is None


def test_duplicate_and_lookalike_refused():
    save_item(data=data())
    with pytest.raises(ItemError, match="already exists"):
        save_item(data=data(code="EIO8437", aliases=[]))
    with pytest.raises(ItemError, match="looks the same as EIO8437"):
        save_item(data=data(code="EI0-8437", aliases=[]))


def test_alias_belonging_to_other_item_refused():
    save_item(data=data())
    with pytest.raises(ItemError, match="belongs to EIO8437"):
        save_item(data=data(code="EIO6006", aliases=["EI08437"]))


def test_edit_keeps_own_code_and_replaces_aliases():
    item = save_item(data=data())
    item = save_item(item=item, data=data(description="LED module 9W", aliases=["EIO-8437-X"]))
    assert item.description == "LED module 9W"
    assert list(ItemAlias.objects.values_list("alias", flat=True)) == ["EIO-8437-X"]


def test_code_change_blocked_once_used():
    item = save_item(data=data())
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(item, loc(), 1)],
               user=make_user("u1", "OFFICE"))
    with pytest.raises(ItemError, match="can't be changed"):
        save_item(item=item, data=data(code="EIO8438"))


def test_required_fields():
    with pytest.raises(ItemError, match="Item code is required"):
        save_item(data=data(code="  "))


def test_search_items_by_code_alias_desc_and_cat_ref():
    item = save_item(data=data())
    for q in ["8437", "ei08437", "led mod", "LD81-171", "EIO8437"]:
        assert item in search_items(q), q
    assert search_items("zzz") == []
```

Run: expected FAIL (ImportError: ItemError).

- [ ] **Step 2: Append to `apps/inventory/services.py`**

Add `ItemAlias` to the models import and add `from .normalise import normalise_code, search_key`. Then append:
```python
class ItemError(ValidationError):
    """An item rule was broken. The message is safe to show to staff as-is."""


def find_item_by_code(text, exclude=None):
    """Exact code, then a stored other spelling, then a look-alike code (O/0, I/1, hyphens, leading zeros)."""
    code, key = normalise_code(text), search_key(text)
    if not code:
        return None
    items = Item.objects.exclude(pk=exclude.pk) if exclude else Item.objects.all()
    aliases = ItemAlias.objects.exclude(item=exclude) if exclude else ItemAlias.objects.all()
    hit = items.filter(code=code).first()
    if hit:
        return hit
    alias = aliases.filter(alias=code).select_related("item").first() or (
        aliases.filter(search_key=key).select_related("item").first() if key else None)
    if alias:
        return alias.item
    return items.filter(search_key=key).first() if key else None


@transaction.atomic
def save_item(*, data, item=None) -> Item:
    """Create (item=None) or update an item from cleaned form data. Raises ItemError with a friendly message."""
    code = normalise_code(data["code"])
    if not code:
        raise ItemError("Item code is required.")
    clash = find_item_by_code(code, exclude=item)
    if clash:
        raise ItemError(f"{code} already exists." if clash.code == code
                        else f"{code} looks the same as {clash.code}. Use that item instead.")
    if item and item.code != code and item.lines.exists():
        raise ItemError("This item already has stock entries, so its code can't be changed. "
                        "Add the new spelling under 'Other spellings'.")
    aliases = []
    for raw in data.get("aliases", []):
        alias = normalise_code(raw)
        if not alias or alias == code or alias in aliases:
            continue
        owner = find_item_by_code(alias, exclude=item)
        if owner and owner.code != code:
            raise ItemError(f"Other spelling {alias} belongs to {owner.code}.")
        aliases.append(alias)
    item = item or Item()
    item.code, item.search_key = code, search_key(code)
    item.spare_type, item.company = data["spare_type"], data["company"]
    item.description = (data.get("description") or "").strip()
    item.cat_ref = normalise_code(data.get("cat_ref"))
    item.fitting_type = data.get("fitting_type")
    item.wattage_w, item.current_ma = data.get("wattage_w"), data.get("current_ma")
    item.unit = data["unit"]
    item.reorder_level = data.get("reorder_level") or 0
    item.is_active = data.get("is_active", True)
    item.save()
    item.aliases.all().delete()
    ItemAlias.objects.bulk_create(ItemAlias(item=item, alias=a, search_key=search_key(a)) for a in aliases)
    return item


def search_items(text, limit=8, active_only=False):
    """Items matching any code, other spelling, description or fitting cat ref (typo-tolerant on codes)."""
    raw, code, key = (text or "").strip(), normalise_code(text), search_key(text)
    if len(raw) < 2:
        return []
    match = (Q(code__icontains=code) | Q(description__icontains=raw) | Q(cat_ref__icontains=code)
             | Q(aliases__alias__icontains=code))
    if len(key) > 2:
        match |= Q(search_key__contains=key) | Q(aliases__search_key__contains=key)
    items = Item.objects.filter(match)
    if active_only:
        items = items.filter(is_active=True)
    return list(items.select_related("spare_type", "company").distinct().order_by("code")[:limit])
```

- [ ] **Step 3: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q
uv run ruff format . && uv run ruff check .
git add apps/inventory tests
git commit -m "feat: item services with look-alike duplicate checks and typo-tolerant search"
```

---

### Task 6: App layout (Tabler) and dashboard

**Files:**
- Create: `apps/inventory/selectors.py`, `apps/inventory/context_processors.py`, `apps/inventory/views.py`, `apps/inventory/urls.py`
- Create: `apps/core/templatetags/__init__.py`, `apps/core/templatetags/core_tags.py`
- Create: `templates/base.html`, `templates/inventory/dashboard.html`, `templates/inventory/_entries_table.html`, `static/js/dashboard.js`
- Modify: `config/settings/base.py` (context processor), `config/urls.py`
- Test: `tests/inventory/test_dashboard.py`

- [ ] **Step 1: Write failing tests** — `tests/inventory/test_dashboard.py`

```python
import pytest
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.selectors import dashboard_stats, weekly_in_out
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def stocked(office_user):
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module")
    wire = make_item("WIRE 1.5 SQMM", unit="MTR", reorder=0, spare_type="Wire / cable")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 8), Line(wire, loc(), 90)], user=office_user)
    post_entry(kind=EntryKind.OUT, entry_date=TODAY, lines=[Line(a, loc(), -2)], user=office_user, subtype="SITE",
               party="Dr Reddys")
    return a, wire


def test_dashboard_stats(stocked):
    stats = dashboard_stats(TODAY)
    assert stats["active_items"] == 2
    assert stats["nos_in_stock"] == 6          # MTR items are not added to NOS
    assert stats["low_count"] == 1             # 6 <= reorder 10
    assert stats["entries_week"] == 2 and stats["entries_today"] == 2


def test_weekly_in_out_counts_nos_only(stocked):
    weeks = weekly_in_out(TODAY)
    assert len(weeks) == 5
    assert weeks[-1]["qty_in"] == 8 and weeks[-1]["qty_out"] == 2


def test_dashboard_page(office_client, stocked):
    page = office_client.get("/")
    assert page.status_code == 200
    html = page.content.decode()
    for text in ["Stock dashboard", "Stock IN", "Stock OUT", "Recent entries", "OUT-0001", "Vizag Office", "chart-weekly"]:
        assert text in html


def test_dashboard_requires_login(client):
    assert client.get("/").status_code == 302
```

Run: expected FAIL.

- [ ] **Step 2: Implement `apps/inventory/selectors.py`** (first part; later tasks append)

```python
"""All reads for the stock screens. Views call these; no queries in templates."""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Sum

from .models import EntryKind, Item, Location, StockBalance, StockEntry, StockLine


def balance_map():
    """{(item_id, location_id): qty} for every non-zero balance."""
    return {(b["item_id"], b["location_id"]): b["qty"]
            for b in StockBalance.objects.exclude(qty=0).values("item_id", "location_id", "qty")}


def item_totals():
    return {r["item_id"]: r["total"] for r in StockBalance.objects.values("item_id").annotate(total=Sum("qty"))}


def is_low(item, total):
    return item.reorder_level > 0 and total <= item.reorder_level


def low_stock_items():
    totals = item_totals()
    return [i for i in Item.objects.filter(is_active=True).select_related("spare_type", "company")
            if is_low(i, totals.get(i.pk, 0))]


def location_unit_totals():
    """[(location, {unit: qty})] for the 'Stock by location' card."""
    totals = defaultdict(lambda: defaultdict(int))
    for row in StockBalance.objects.exclude(qty=0).values("location_id", "item__unit").annotate(q=Sum("qty")):
        totals[row["location_id"]][row["item__unit"]] += row["q"]
    return [(place, dict(totals[place.pk])) for place in Location.objects.filter(is_active=True)]


def dashboard_stats(today):
    nos = StockBalance.objects.filter(item__unit="NOS").aggregate(t=Sum("qty"))["t"] or 0
    return {
        "active_items": Item.objects.filter(is_active=True).count(),
        "nos_in_stock": nos,
        "low_count": len(low_stock_items()),
        "entries_week": StockEntry.objects.filter(entry_date__gt=today - timedelta(days=7)).count(),
        "entries_today": StockEntry.objects.filter(entry_date=today).count(),
    }


def weekly_in_out(today, weeks=5):
    """Quantity (NOS items only) received and issued per 7-day window, oldest first; undone entries excluded."""
    windows = [(today - timedelta(days=7 * w + 6), today - timedelta(days=7 * w)) for w in range(weeks - 1, -1, -1)]
    lines = (StockLine.objects.filter(entry__kind__in=[EntryKind.IN, EntryKind.OUT], item__unit="NOS",
                                      entry__entry_date__gte=windows[0][0], entry__entry_date__lte=today,
                                      entry__reversed_by__isnull=True)
             .values_list("entry__entry_date", "qty"))
    out = [{"start": s, "end": e, "label": f"{s:%d-%m}–{e:%d-%m}", "qty_in": 0, "qty_out": 0} for s, e in windows]
    for day, qty in lines:
        for week in out:
            if week["start"] <= day <= week["end"]:
                week["qty_in" if qty > 0 else "qty_out"] += abs(qty)
    return out


def entries_with_lines(queryset):
    return queryset.select_related("reverses", "reversed_by", "created_by").prefetch_related("lines__item", "lines__location")


def recent_entries(limit=8):
    return list(entries_with_lines(StockEntry.objects.order_by("-entry_date", "-id"))[:limit])
```

- [ ] **Step 3: Template tags** — `apps/core/templatetags/__init__.py` (empty) and `apps/core/templatetags/core_tags.py`:

```python
from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def url_with(context, **changes):
    """Current URL's query string with some params replaced (None removes). Keeps filters across sort/page links."""
    params = context["request"].GET.copy()
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return "?" + params.urlencode()


@register.filter
def qty(value):
    """Zero shows as a faint 0 so real numbers stand out."""
    return format_html('<span class="zero">0</span>') if not value else value


@register.filter
def lines_summary(entry):
    """'EIO6006 × 3' for single-item entries, else 'N items'."""
    lines = list(entry.lines.all())
    codes = {line.item.code for line in lines}
    if len(codes) == 1:
        moved = sum(line.qty for line in lines if line.qty > 0) if entry.kind == "TRF" else sum(abs(line.qty) for line in lines)
        return format_html('<span class="code">{}</span> × {}', next(iter(codes)), moved)
    return f"{len(codes)} items"


@register.filter
def entry_locations(entry):
    seen = []
    for line in entry.lines.all():
        if line.location.name not in seen:
            seen.append(line.location.name)
    return " → ".join(seen)


@register.filter
def get_item(mapping, key):
    return mapping.get(key, 0) if mapping else 0
```


- [ ] **Step 4: Nav context processor, view, urls**

The sidebar is built from one Python list. Each menu entry resolves its URL by name. Entries whose view doesn't exist yet (built in later tasks) render disabled automatically, so later tasks never edit the layout.

`apps/inventory/context_processors.py`:
```python
from django.urls import NoReverseMatch, reverse

from .selectors import low_stock_items

# (section, [(url_name, label, tabler icon, icon css class, admin_only)])
NAV = [
    ("Overview", [("dashboard", "Dashboard", "layout-dashboard", "", False)]),
    ("Stock", [("stock_in", "Stock IN", "package-import", "text-in", False),
               ("stock_out", "Stock OUT", "package-export", "text-out", False),
               ("transfer", "Transfer", "arrows-exchange", "", False),
               ("adjust", "Adjust count", "adjustments-horizontal", "", False)]),
    ("Reports", [("current_stock", "Current stock", "building-warehouse", "", False),
                 ("movements", "Movements", "history", "", False),
                 ("low_stock", "Low stock", "alert-triangle", "", False)]),
    ("Setup", [("items", "Items", "box", "", False), ("masters", "Masters", "settings", "", True)]),
]
EXTRA_URLS = ["global_search"]
# URL names that should highlight a menu entry other than their own.
ACTIVE_ALIASES = {"item_new": "items", "item_edit": "items", "item_detail": "items", "entry_detail": "movements"}


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def nav(request):
    """Sidebar sections, URLs by name (None until built), active entry, and the low-stock count."""
    if not request.user.is_authenticated:
        return {}
    urls = {name: _url(name) for _, entries in NAV for name, *_ in entries}
    urls.update({name: _url(name) for name in EXTRA_URLS})
    current = request.resolver_match.url_name if request.resolver_match else ""
    active = ACTIVE_ALIASES.get(current, current)
    sections = [(title, [{"name": n, "label": label, "icon": ic, "cls": cls, "admin_only": admin, "url": urls[n],
                          "active": n == active} for n, label, ic, cls, admin in entries]) for title, entries in NAV]
    return {"nav_sections": sections, "nav_urls": urls, "nav_low_count": len(low_stock_items())}
```

Add `"apps.inventory.context_processors.nav"` to the context processors in `config/settings/base.py`.

`apps/inventory/views.py`:
```python
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE

from . import selectors


@role_required(OFFICE)
def dashboard(request):
    today = timezone.localdate()
    weeks = selectors.weekly_in_out(today)
    return render(request, "inventory/dashboard.html", {
        "stats": selectors.dashboard_stats(today),
        "weeks": weeks,
        "weeks_chart": [{"label": w["label"], "in": w["qty_in"], "out": w["qty_out"]} for w in weeks],
        "locations": selectors.location_unit_totals(),
        "recent": selectors.recent_entries(),
        "today": today,
    })
```

`apps/inventory/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
```

`config/urls.py`: add `path("", include("apps.inventory.urls")),` after the accounts include.

- [ ] **Step 5: `templates/base.html`** (Tabler vertical layout from the approved mockup)

```html
{% load static %}<!doctype html>
<html lang="en-IN" data-bs-navbar-position="vertical">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{% block title %}SVKML Stock{% endblock %} · SVKML</title>
  <link rel="stylesheet" href="{% static 'vendor/tabler.min.css' %}">
  <link rel="stylesheet" href="{% static 'vendor/tom-select.bootstrap5.min.css' %}">
  <link rel="stylesheet" href="{% static 'vendor/tabler-vendors.min.css' %}">
  <link rel="stylesheet" href="{% static 'vendor/tabler-icons.min.css' %}">
  <link rel="stylesheet" href="{% static 'css/app.css' %}">
</head>
<body>
<div class="page">
  <aside class="navbar navbar-vertical navbar-expand-lg" data-bs-theme="dark">
    <div class="container-fluid">
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#sidebar-menu" aria-controls="sidebar-menu" aria-expanded="false" aria-label="Open menu"><span class="navbar-toggler-icon"></span></button>
      <a href="{% url 'dashboard' %}" class="navbar-brand navbar-brand-autodark brand"><span class="brand-mark"><i class="ti ti-bulb"></i></span> SVKML <span class="brand-sub">Stock</span></a>
      <div class="collapse navbar-collapse" id="sidebar-menu">
        <ul class="navbar-nav pt-lg-3" id="nav">
          {% for title, entries in nav_sections %}
            <li class="nav-section">{{ title }}</li>
            {% for e in entries %}{% if not e.admin_only or is_admin %}
              <li class="nav-item"><a class="nav-link{% if e.active %} active{% endif %}{% if not e.url %} disabled{% endif %}"
                href="{{ e.url|default:'#' }}"{% if not e.url %} aria-disabled="true"{% endif %}>
                <span class="nav-link-icon {{ e.cls }}"><i class="ti ti-{{ e.icon }}"></i></span><span class="nav-link-title">{{ e.label }}</span>
                {% if e.name == 'low_stock' and nav_low_count %}<span class="badge bg-red-lt ms-auto">{{ nav_low_count }}</span>{% endif %}</a></li>
            {% endif %}{% endfor %}
          {% endfor %}
        </ul>
      </div>
    </div>
  </aside>
  <div class="page-wrapper">
    <header class="navbar navbar-expand-md d-print-none topbar">
      <div class="container-xl">
        <div class="global-search">
          <div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
            <input id="gsearch" type="search" class="form-control" placeholder="Search items, old spellings, entry no…" autocomplete="off" aria-label="Search" data-url="{{ nav_urls.global_search|default:'' }}"></div>
          <div id="gresults" class="dropdown-menu gresults"></div>
        </div>
        <div class="navbar-nav flex-row order-md-last ms-auto align-items-center gap-2">
          <a href="{{ nav_urls.low_stock|default:'#' }}" class="nav-link px-2 position-relative" title="Low stock" aria-label="Low stock"><i class="ti ti-bell fs-2"></i><span class="badge bg-red text-white badge-notification bell-count">{% if nav_low_count %}{{ nav_low_count }}{% endif %}</span></a>
          <div class="nav-item dropdown">
            <a href="#" class="nav-link d-flex lh-1 text-reset p-0" data-bs-toggle="dropdown" aria-label="User menu">
              <span class="avatar avatar-sm kpi-brand">{{ user.username|slice:":2"|upper }}</span>
              <div class="d-none d-xl-block ps-2"><div>{{ user.first_name|default:user.username }}</div><div class="mt-1 small text-secondary">{% if is_admin %}Admin{% else %}Office staff{% endif %}</div></div>
            </a>
            <div class="dropdown-menu dropdown-menu-end dropdown-menu-arrow">
              {% if is_admin %}<a href="{% url 'admin:index' %}" class="dropdown-item"><i class="ti ti-users"></i>Users (admin)</a>{% endif %}
              <form method="post" action="{% url 'logout' %}">{% csrf_token %}<button class="dropdown-item" type="submit"><i class="ti ti-logout"></i>Logout</button></form>
            </div>
          </div>
        </div>
      </div>
    </header>
    <div class="page-header d-print-none"><div class="container-xl"><div class="row g-2 align-items-center">
      <div class="col"><div class="page-pretitle">{% block pretitle %}{% endblock %}</div><h2 class="page-title">{% block page_title %}{% endblock %}</h2></div>
      <div class="col-auto ms-auto d-print-none"><div class="btn-list">{% block actions %}{% endblock %}</div></div>
    </div></div></div>
    <div class="page-body"><div class="container-xl">
      {% for message in messages %}<div class="alert alert-{% if message.tags == 'error' %}danger{% else %}success{% endif %} alert-dismissible" role="alert">{{ message }}<a class="btn-close" data-bs-dismiss="alert" aria-label="close"></a></div>{% endfor %}
      {% block content %}{% endblock %}
    </div></div>
  </div>
</div>
<script src="{% static 'vendor/tabler.min.js' %}"></script>
<script src="{% static 'vendor/tom-select.complete.min.js' %}"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 6: Dashboard templates and chart JS**

`templates/inventory/_entries_table.html` (reused by dashboard and later lists; Task 9 links the entry number):
```html
{% load core_tags %}
<div class="table-responsive"><table class="table table-vcenter card-table table-striped">
  <thead><tr><th>Entry</th><th>Date</th><th>Type</th><th>Details</th><th>Items</th><th>Location</th><th>Supplier / issued to</th><th>By</th></tr></thead>
  <tbody>{% for e in entries %}
    <tr class="{% if e.is_undone %}undone{% endif %}"><td class="code">{{ e.number }}</td><td class="nowrap">{{ e.entry_date|date }}</td>
      <td><span class="badge badge-k k-{{ e.kind }}">{{ e.get_kind_display }}</span></td><td>{{ e.details }}</td>
      <td>{{ e|lines_summary }}</td><td>{{ e|entry_locations }}</td><td>{{ e.party }}</td><td>{{ e.created_by.first_name|default:e.created_by.username }}</td></tr>
  {% empty %}<tr><td colspan="8" class="text-center text-secondary py-4">No entries yet.</td></tr>{% endfor %}</tbody>
</table></div>
```

Add this property to `StockEntry` in `apps/inventory/models.py` (a safe check, because a missing reverse one-to-one raises in Python):
```python
    @property
    def is_undone(self):
        """True if an Undo entry reverses this one (uses the `undone_flag` annotation when present)."""
        flag = getattr(self, "undone_flag", None)
        return StockEntry.objects.filter(reverses=self).exists() if flag is None else flag
```
In `selectors.entries_with_lines`, annotate `undone_flag` to avoid one query per row:
```python
from django.db.models import Exists, OuterRef

def entries_with_lines(queryset):
    undone = StockEntry.objects.filter(reverses=OuterRef("pk"))
    return (queryset.annotate(undone_flag=Exists(undone)).select_related("reverses", "created_by")
            .prefetch_related("lines__item", "lines__location"))
```
(Replace the earlier `entries_with_lines` from Step 2 with this version.)

`templates/inventory/dashboard.html`:
```html
{% extends "base.html" %}{% load static %}
{% block title %}Dashboard{% endblock %}
{% block pretitle %}Overview{% endblock %}
{% block page_title %}Stock dashboard{% endblock %}
{% block actions %}<span class="text-secondary align-self-center"><i class="ti ti-calendar"></i> {{ today|date }}</span>{% endblock %}
{% block content %}
<div class="row row-deck row-cards">
  <div class="col-sm-6 col-lg-3"><div class="card card-sm"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar kpi-brand"><i class="ti ti-box"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ stats.active_items }}</div><div class="text-secondary">Active items</div></div></div></div></div></div>
  <div class="col-sm-6 col-lg-3"><div class="card card-sm"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar kpi-brand"><i class="ti ti-building-warehouse"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ stats.nos_in_stock }} NOS</div><div class="text-secondary">In stock (all locations)</div><div class="small text-secondary">other units shown per location</div></div></div></div></div></div>
  <div class="col-sm-6 col-lg-3"><div class="card card-sm"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar {% if stats.low_count %}kpi-alert{% else %}kpi-ok{% endif %}"><i class="ti ti-alert-triangle"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ stats.low_count }}</div><div class="text-secondary">Low stock items</div><div class="small text-secondary">at or below reorder level</div></div></div></div></div></div>
  <div class="col-sm-6 col-lg-3"><div class="card card-sm"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar kpi-brand"><i class="ti ti-arrows-exchange"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ stats.entries_week }}</div><div class="text-secondary">Entries this week</div><div class="small text-secondary">{{ stats.entries_today }} today</div></div></div></div></div></div>
  <div class="col-12"><div class="card"><div class="card-body"><div class="row g-2 quick">
    <div class="col-6 col-lg-3"><a href="{{ nav_urls.stock_in|default:'#' }}" class="btn btn-in w-100 flex-column"><i class="ti ti-package-import"></i> Stock IN<small>Material received</small></a></div>
    <div class="col-6 col-lg-3"><a href="{{ nav_urls.stock_out|default:'#' }}" class="btn btn-out w-100 flex-column"><i class="ti ti-package-export"></i> Stock OUT<small>Material issued</small></a></div>
    <div class="col-6 col-lg-3"><a href="{{ nav_urls.transfer|default:'#' }}" class="btn btn-quiet w-100 flex-column"><i class="ti ti-arrows-exchange"></i> Transfer<small>Between locations</small></a></div>
    <div class="col-6 col-lg-3"><a href="{{ nav_urls.adjust|default:'#' }}" class="btn btn-quiet w-100 flex-column"><i class="ti ti-adjustments-horizontal"></i> Adjust<small>Correct a count</small></a></div>
  </div></div></div></div>
  <div class="col-lg-8"><div class="card"><div class="card-header"><div><h3 class="card-title">Stock IN vs OUT</h3>
      <div class="card-subtitle">Quantity per week, last 5 weeks (items counted in NOS)</div></div>
      <div class="card-actions"><button type="button" class="btn btn-sm btn-outline-secondary" id="chart-toggle"><i class="ti ti-table"></i> View as table</button></div></div>
    <div class="card-body"><div id="chart-weekly" class="chart-box" role="img" aria-label="Bar chart of stock in and stock out per week"></div>
      <table class="table table-sm" id="chart-table" hidden><thead><tr><th>Week</th><th class="num">Stock IN (NOS)</th><th class="num">Stock OUT (NOS)</th></tr></thead>
        <tbody>{% for w in weeks %}<tr><td>{{ w.label }}</td><td class="num">{{ w.qty_in }}</td><td class="num">{{ w.qty_out }}</td></tr>{% endfor %}</tbody></table></div></div></div>
  <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">Stock by location</h3></div>
    <div class="list-group list-group-flush">{% for place, units in locations %}
      <div class="list-group-item d-flex align-items-center"><span class="avatar avatar-sm bg-secondary-lt me-3"><i class="ti ti-map-pin"></i></span>
        <div class="flex-fill"><div class="fw-medium">{{ place.name }}</div><div class="text-secondary small">{% for u, q in units.items %}{{ q }} {{ u }}{% if not forloop.last %} · {% endif %}{% empty %}Empty{% endfor %}</div></div></div>
    {% endfor %}</div></div></div>
  <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">Recent entries</h3>
    {% if nav_urls.movements %}<div class="card-actions"><a href="{{ nav_urls.movements }}" class="btn btn-sm btn-outline-primary">All movements <i class="ti ti-arrow-right"></i></a></div>{% endif %}</div>
    {% include "inventory/_entries_table.html" with entries=recent %}</div></div>
</div>
{{ weeks_chart|json_script:"weeks-data" }}
{% endblock %}
{% block scripts %}<script src="{% static 'vendor/apexcharts.min.js' %}"></script><script src="{% static 'js/dashboard.js' %}"></script>{% endblock %}
```

`static/js/dashboard.js`:
```javascript
/* Weekly IN vs OUT: grouped bars, CVD-validated pair (blue IN / orange OUT), 4px rounded ends, 2px gap,
   recessive grid, legend + shared tooltip, and a table view (DESIGN.md). */
(function () {
  const data = JSON.parse(document.getElementById("weeks-data").textContent);
  const el = document.getElementById("chart-weekly");
  new ApexCharts(el, {
    chart: { type: "bar", height: 260, toolbar: { show: false }, fontFamily: "inherit", animations: { enabled: false } },
    series: [{ name: "Stock IN", data: data.map(d => d.in) }, { name: "Stock OUT", data: data.map(d => d.out) }],
    colors: ["#2a78d6", "#eb6834"],
    plotOptions: { bar: { columnWidth: "45%", borderRadius: 4, borderRadiusApplication: "end" } },
    stroke: { show: true, width: 2, colors: ["#ffffff"] },
    dataLabels: { enabled: false },
    grid: { borderColor: "#eef0f3", strokeDashArray: 4 },
    xaxis: { categories: data.map(d => d.label), axisBorder: { show: false }, axisTicks: { show: false } },
    yaxis: { title: { text: "NOS" } },
    legend: { position: "top", horizontalAlign: "left", markers: { shape: "square", size: 7 } },
    tooltip: { shared: true, intersect: false, y: { formatter: v => `${v} NOS` } },
  }).render();
  const table = document.getElementById("chart-table"), btn = document.getElementById("chart-toggle");
  btn.addEventListener("click", () => {
    table.hidden = !table.hidden; el.hidden = !table.hidden;
    btn.innerHTML = table.hidden ? '<i class="ti ti-table"></i> View as table' : '<i class="ti ti-chart-bar"></i> View as chart';
  });
})();
```

- [ ] **Step 7: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q
uv run ruff format . && uv run ruff check .
git add apps templates static config tests
git commit -m "feat: Tabler app layout and stock dashboard with weekly IN vs OUT chart"
```

---
### Task 7: List screens: current stock, movements, low stock (server-side sort + paging)

**Files:**
- Create: `apps/core/tables.py`, `apps/inventory/filters.py`
- Modify: `apps/core/templatetags/core_tags.py` (add `sort_th`, `hidden_params`), `apps/inventory/services.py` (extract `item_search_q`), `apps/inventory/selectors.py`, `apps/inventory/views.py`, `apps/inventory/urls.py`
- Create: `templates/core/_sort_th.html`, `templates/core/_pagination.html`, `templates/inventory/current_stock.html`, `templates/inventory/movements.html`, `templates/inventory/low_stock.html`
- Test: `tests/core/test_tables.py`, `tests/inventory/test_lists.py`

- [ ] **Step 1: Write failing tests**

`tests/core/test_tables.py`:
```python
from django.test import RequestFactory

from apps.core.tables import sort_and_page

ROWS = [{"code": c, "n": n} for c, n in [("b", 2), ("a", 3), ("C", 1)] * 5]
SORTERS = {"code": lambda r: r["code"], "n": lambda r: r["n"]}


def run(qs):
    return sort_and_page(RequestFactory().get("/x" + qs), ROWS, SORTERS, "code")


def test_default_sort_is_case_insensitive_and_pages_by_10():
    t = run("")
    assert [r["code"] for r in t["page"].object_list][:5] == ["a"] * 5
    assert t["page"].paginator.per_page == 10 and t["total"] == 15


def test_sort_desc_and_size():
    t = run("?sort=n&dir=desc&size=25")
    assert t["page"].object_list[0]["n"] == 3 and t["size"] == 25 and t["dir"] == "desc"


def test_bad_params_fall_back():
    t = run("?sort=evil&dir=sideways&size=999&page=abc")
    assert (t["sort"], t["dir"], t["size"], t["page"].number) == ("code", "asc", 10, 1)
```

`tests/inventory/test_lists.py`:
```python
import datetime

import pytest
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry, undo_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def stock(office_user):
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module")
    b = make_item("LG78-150-700", reorder=2)
    c = make_item("LENS", reorder=0, spare_type="Lens")
    post_entry(kind=EntryKind.IN, entry_date=TODAY - datetime.timedelta(days=40), user=office_user,
               lines=[Line(a, loc(), 8), Line(b, loc(), 20), Line(c, loc("Svkml"), 5)])
    out = post_entry(kind=EntryKind.OUT, entry_date=TODAY, user=office_user, subtype="SITE", party="Dr Reddys",
                     lines=[Line(b, loc(), -3)])
    undo_entry(entry=out, reason="wrong job", user=office_user)
    return a, b, c


def test_current_stock_all_locations(office_client, stock):
    html = office_client.get("/stock/").content.decode()
    for text in ["EIO6006", "LG78-150-700", "LENS", "Vizag Office", "Svkml", "Showing 1–3 of 3"]:
        assert text in html


def test_current_stock_filters(office_client, stock):
    svkml = loc("Svkml").pk
    html = office_client.get(f"/stock/?location={svkml}").content.decode()
    assert "LENS" in html and "EIO6006" not in html
    html = office_client.get("/stock/?low=1").content.decode()
    assert "EIO6006" in html and "LG78-150-700" not in html
    html = office_client.get("/stock/?q=ei06006").content.decode()  # look-alike spelling
    assert "EIO6006" in html and "LENS" not in html


def test_current_stock_sort_by_total_desc(office_client, stock):
    html = office_client.get("/stock/?sort=total&dir=desc").content.decode()
    assert html.index("LG78-150-700") < html.index("EIO6006") < html.index("LENS")


def test_movements_default_last_30_days_and_undone(office_client, stock):
    html = office_client.get("/movements/").content.decode()
    assert "OUT-0001" in html and "REV-0001" in html and "IN-0001" not in html  # IN was 40 days ago
    assert 'class="undone"' in html
    old = (TODAY - datetime.timedelta(days=60)).isoformat()
    assert "IN-0001" in office_client.get(f"/movements/?date_from={old}").content.decode()


def test_movements_filter_kind(office_client, stock):
    html = office_client.get("/movements/?kind=REV").content.decode()
    assert "REV-0001" in html and "OUT-0001" not in html


def test_low_stock(office_client, stock):
    html = office_client.get("/low-stock/").content.decode()
    assert "EIO6006" in html and "LG78-150-700" not in html and "Short by" in html
```

Run: expected FAIL.

- [ ] **Step 2: `apps/core/tables.py`**

```python
"""Server-side sort + paging for list screens. GET params: sort, dir (asc|desc), page, size (10|25|50)."""

from django.core.paginator import Paginator

SIZES = (10, 25, 50)


def _key(value):
    if value is None:
        return (1, "")
    return (0, value.lower()) if isinstance(value, str) else (0, value)


def sort_and_page(request, rows, sorters, default_sort, default_dir="asc"):
    """rows: list; sorters: {key: row -> value}. Unknown params fall back to safe defaults."""
    sort = request.GET.get("sort") if request.GET.get("sort") in sorters else default_sort
    direction = request.GET.get("dir") if request.GET.get("dir") in ("asc", "desc") else default_dir
    rows = sorted(rows, key=lambda r: _key(sorters[sort](r)), reverse=direction == "desc")
    try:
        size = int(request.GET.get("size", SIZES[0]))
    except ValueError:
        size = SIZES[0]
    if size not in SIZES:
        size = SIZES[0]
    page = Paginator(rows, size).get_page(request.GET.get("page"))
    return {"page": page, "sort": sort, "dir": direction, "size": size, "sizes": SIZES, "total": len(rows)}
```

- [ ] **Step 3: Template tags and partials**

Append to `apps/core/templatetags/core_tags.py`:
```python
@register.inclusion_tag("core/_sort_th.html", takes_context=True)
def sort_th(context, key, label, num=False):
    """Column header that sorts by `key`; clicking again flips the direction."""
    table = context["table"]
    active = table["sort"] == key
    new_dir = "desc" if active and table["dir"] == "asc" else "asc"
    return {"href": url_with(context, sort=key, dir=new_dir, page=None), "label": label, "num": num,
            "cls": table["dir"] if active else ""}


@register.simple_tag(takes_context=True)
def hidden_params(context, exclude=""):
    """Hidden inputs for the current GET params (minus `exclude`), so a small form keeps the other filters."""
    skip = set(exclude.split(","))
    return format_html_join("", '<input type="hidden" name="{}" value="{}">',
                            ((k, v) for k, v in context["request"].GET.items() if k not in skip))
```
Add `format_html_join` to the `django.utils.html` import.

`templates/core/_sort_th.html`:
```html
<th class="{% if num %}num{% endif %}"><a class="sort {{ cls }}" href="{{ href }}">{{ label }}</a></th>
```

`templates/core/_pagination.html` (expects `table` in context):
```html
{% load core_tags %}
<div class="card-footer d-flex align-items-center flex-wrap gap-2">
  <p class="m-0 text-secondary">Showing {% if table.total %}{{ table.page.start_index }}–{{ table.page.end_index }}{% else %}0{% endif %} of {{ table.total }}</p>
  <div class="ms-auto d-flex align-items-center gap-2">
    <form method="get" class="m-0">{% hidden_params "size,page" %}
      <select name="size" class="form-select form-select-sm w-auto" onchange="this.form.submit()" aria-label="Rows per page">
        {% for s in table.sizes %}<option value="{{ s }}" {% if s == table.size %}selected{% endif %}>{{ s }} / page</option>{% endfor %}
      </select></form>
    {% if table.page.paginator.num_pages > 1 %}
    <ul class="pagination m-0">
      <li class="page-item {% if not table.page.has_previous %}disabled{% endif %}"><a class="page-link" href="{% if table.page.has_previous %}{% url_with page=table.page.previous_page_number %}{% else %}#{% endif %}" aria-label="Previous"><i class="ti ti-chevron-left"></i></a></li>
      {% for n in table.page.paginator.page_range %}
        {% if n == table.page.number %}<li class="page-item active"><span class="page-link">{{ n }}</span></li>
        {% elif n == 1 or n == table.page.paginator.num_pages or n|add:"-1" == table.page.number or n|add:"1" == table.page.number %}<li class="page-item"><a class="page-link" href="{% url_with page=n %}">{{ n }}</a></li>
        {% elif n|add:"-2" == table.page.number or n|add:"2" == table.page.number %}<li class="page-item disabled"><span class="page-link">…</span></li>{% endif %}
      {% endfor %}
      <li class="page-item {% if not table.page.has_next %}disabled{% endif %}"><a class="page-link" href="{% if table.page.has_next %}{% url_with page=table.page.next_page_number %}{% else %}#{% endif %}" aria-label="Next"><i class="ti ti-chevron-right"></i></a></li>
    </ul>{% endif %}
  </div>
</div>
```

- [ ] **Step 4: Filters, search Q, selectors**

In `apps/inventory/services.py`, split the query-building out of `search_items` (behaviour unchanged):
```python
def item_search_q(text):
    """Q matching any code, other spelling, description or fitting cat ref (typo-tolerant on codes). None if too short."""
    raw, code, key = (text or "").strip(), normalise_code(text), search_key(text)
    if len(raw) < 2:
        return None
    match = (Q(code__icontains=code) | Q(description__icontains=raw) | Q(cat_ref__icontains=code)
             | Q(aliases__alias__icontains=code))
    if len(key) > 2:
        match |= Q(search_key__contains=key) | Q(aliases__search_key__contains=key)
    return match


def search_items(text, limit=8, active_only=False):
    match = item_search_q(text)
    if match is None:
        return []
    items = Item.objects.filter(match)
    if active_only:
        items = items.filter(is_active=True)
    return list(items.select_related("spare_type", "company").prefetch_related("aliases").distinct().order_by("code")[:limit])
```

`apps/inventory/filters.py`:
```python
"""Parse list-screen GET params once; views and Excel exports share them."""

from dataclasses import dataclass
from datetime import date, timedelta

from .models import Company, EntryKind, FittingType, Item, Location, SpareType


def _obj(model, value):
    try:
        return model.objects.get(pk=int(value)) if value else None
    except (ValueError, model.DoesNotExist):
        return None


def _date(value, default):
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


@dataclass
class StockFilters:
    location: Location | None
    spare_type: SpareType | None
    company: Company | None
    q: str
    low: bool


def stock_filters(params):
    return StockFilters(_obj(Location, params.get("location")), _obj(SpareType, params.get("spare_type")),
                        _obj(Company, params.get("company")), params.get("q", "").strip(), params.get("low") == "1")


@dataclass
class MovementFilters:
    date_from: date
    date_to: date
    kind: str
    location: Location | None
    q: str
    item: Item | None


def movement_filters(params, today):
    kind = params.get("kind", "")
    return MovementFilters(_date(params.get("date_from"), today - timedelta(days=30)), _date(params.get("date_to"), today),
                           kind if kind in EntryKind.values else "", _obj(Location, params.get("location")),
                           params.get("q", "").strip(), _obj(Item, params.get("item")))


@dataclass
class ItemFilters:
    q: str
    spare_type: SpareType | None
    company: Company | None
    fitting_type: FittingType | None
    status: str  # "1" active, "0" inactive, "" all


def item_filters(params):
    status = params.get("status", "1")
    return ItemFilters(params.get("q", "").strip(), _obj(SpareType, params.get("spare_type")),
                       _obj(Company, params.get("company")), _obj(FittingType, params.get("fitting_type")),
                       status if status in ("1", "0", "") else "1")
```

Append to `apps/inventory/selectors.py` (add `Exists, OuterRef` to imports if not already, plus `from .services import item_search_q`):
```python
def _filtered_items(f):
    items = Item.objects.select_related("spare_type", "company", "fitting_type")
    if getattr(f, "spare_type", None):
        items = items.filter(spare_type=f.spare_type)
    if getattr(f, "company", None):
        items = items.filter(company=f.company)
    match = item_search_q(getattr(f, "q", ""))
    if match is not None:
        items = items.filter(match).distinct()
    return items


def current_stock_rows(f):
    """(rows, locations). Row: {item, per_loc: {location_id: qty}, total, low}. Hides items with no stock."""
    locations = [f.location] if f.location else list(Location.objects.filter(is_active=True))
    bal = balance_map()
    rows = []
    for item in _filtered_items(f).filter(is_active=True):
        per_loc = {place.pk: bal.get((item.pk, place.pk), 0) for place in Location.objects.all()}
        total = sum(per_loc.values())
        low = is_low(item, total)
        shown = per_loc.get(f.location.pk, 0) != 0 if f.location else (total != 0 or f.low)
        if shown and (low or not f.low):
            rows.append({"item": item, "per_loc": per_loc, "total": total, "low": low})
    return rows, locations


def low_stock_rows():
    rows, _ = current_stock_rows(type("F", (), {"location": None, "spare_type": None, "company": None, "q": "", "low": True})())
    for row in rows:
        row["short_by"] = max(0, row["item"].reorder_level - row["total"])
    return rows


def movement_rows(f):
    """One row per ledger line in the date range: {entry, line, undone}. Newest first."""
    undone = StockEntry.objects.filter(reverses=OuterRef("entry_id"))
    lines = (StockLine.objects.filter(entry__entry_date__gte=f.date_from, entry__entry_date__lte=f.date_to)
             .select_related("entry", "entry__created_by", "entry__reverses", "entry__reversed_by", "item", "location")
             .annotate(undone=Exists(undone)).order_by("-entry__entry_date", "-entry_id", "id"))
    if f.kind:
        lines = lines.filter(entry__kind=f.kind)
    if f.location:
        lines = lines.filter(location=f.location)
    if f.item:
        lines = lines.filter(item=f.item)
    if f.q:
        lines = lines.filter(Q(item__code__icontains=f.q) | Q(entry__party__icontains=f.q)
                             | Q(entry__ref__icontains=f.q) | Q(entry__number__icontains=f.q))
    return [{"entry": line.entry, "line": line, "undone": line.undone, "n": n} for n, line in enumerate(lines)]
```
Add `Q` to the `django.db.models` import in selectors.

- [ ] **Step 5: Views and URLs**

Append to `apps/inventory/views.py` (add imports: `from apps.core.tables import sort_and_page`, `from .filters import movement_filters, stock_filters`, `from .models import Company, EntryKind, Location, SpareType`):
```python
def _masters():
    return {"all_locations": Location.objects.filter(is_active=True), "spare_types": SpareType.objects.filter(is_active=True),
            "companies": Company.objects.filter(is_active=True)}


@role_required(OFFICE)
def current_stock(request):
    f = stock_filters(request.GET)
    rows, locations = selectors.current_stock_rows(f)
    sorters = {"code": lambda r: r["item"].code, "type": lambda r: r["item"].spare_type.name,
               "desc": lambda r: r["item"].description, "company": lambda r: r["item"].company.name,
               "total": lambda r: r["total"], "unit": lambda r: r["item"].unit}
    for p in locations:
        p.sort_key = f"L{p.pk}"
        sorters[p.sort_key] = lambda r, pk=p.pk: r["per_loc"].get(pk, 0)
    table = sort_and_page(request, rows, sorters, "code")
    return render(request, "inventory/current_stock.html", {"f": f, "table": table, "locations": locations, **_masters()})


@role_required(OFFICE)
def low_stock(request):
    rows = selectors.low_stock_rows()
    sorters = {"code": lambda r: r["item"].code, "type": lambda r: r["item"].spare_type.name,
               "total": lambda r: r["total"], "short": lambda r: r["short_by"], "reorder": lambda r: r["item"].reorder_level}
    table = sort_and_page(request, rows, sorters, "short", "desc")
    return render(request, "inventory/low_stock.html", {"table": table, "locations": Location.objects.filter(is_active=True)})


@role_required(OFFICE)
def movements(request):
    f = movement_filters(request.GET, timezone.localdate())
    rows = selectors.movement_rows(f)
    sorters = {"date": lambda r: r["n"], "no": lambda r: r["entry"].number, "kind": lambda r: r["entry"].kind,
               "code": lambda r: r["line"].item.code, "loc": lambda r: r["line"].location.name,
               "in": lambda r: r["line"].qty, "out": lambda r: -r["line"].qty, "party": lambda r: r["entry"].party,
               "by": lambda r: r["entry"].created_by.username}
    table = sort_and_page(request, rows, sorters, "date", "asc")
    return render(request, "inventory/movements.html", {"f": f, "table": table, "kinds": EntryKind.choices, **_masters()})
```
`movements` defaults to `sort=date` ascending on `n`, where `n` = 0 is the newest row, so newest appears first.

`apps/inventory/urls.py` urlpatterns become:
```python
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("stock/", views.current_stock, name="current_stock"),
    path("low-stock/", views.low_stock, name="low_stock"),
    path("movements/", views.movements, name="movements"),
]
```

- [ ] **Step 6: Templates**

`templates/inventory/current_stock.html`:
```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}Current stock{% endblock %}
{% block pretitle %}Reports{% endblock %}
{% block page_title %}Current stock{% endblock %}
{% block actions %}{% block export_button %}{% endblock %}{% endblock %}
{% block content %}
<div class="card">
  <div class="card-header"><form method="get" class="row g-2 w-100 align-items-end">
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="f-loc">Location</label>
      <select id="f-loc" name="location" class="form-select" onchange="this.form.submit()"><option value="">All locations</option>
        {% for p in all_locations %}<option value="{{ p.pk }}" {% if f.location == p %}selected{% endif %}>{{ p.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="f-type">Spare type</label>
      <select id="f-type" name="spare_type" class="form-select" onchange="this.form.submit()"><option value="">All types</option>
        {% for t in spare_types %}<option value="{{ t.pk }}" {% if f.spare_type == t %}selected{% endif %}>{{ t.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="f-co">Company</label>
      <select id="f-co" name="company" class="form-select" onchange="this.form.submit()"><option value="">All companies</option>
        {% for c in companies %}<option value="{{ c.pk }}" {% if f.company == c %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-4"><label class="form-label small text-secondary mb-1" for="f-q">Search</label>
      <div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
        <input id="f-q" type="search" name="q" value="{{ f.q }}" class="form-control" placeholder="Code, old spelling, description, fitting"></div></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" name="low" value="1" {% if f.low %}checked{% endif %} onchange="this.form.submit()"><span class="form-check-label">Only low stock</span></label></div>
  </form></div>
  <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr>{% sort_th "code" "Item code" %}{% sort_th "type" "Spare type" %}{% sort_th "desc" "Description" %}<th>Used in (fitting)</th>{% sort_th "company" "Company" %}
      {% for p in locations %}{% sort_th p.sort_key p.name True %}{% endfor %}
      {% if not f.location %}{% sort_th "total" "Total" True %}{% endif %}{% sort_th "unit" "Unit" %}</tr></thead>
    <tbody>{% for r in table.page %}<tr>
      <td><span class="code">{{ r.item.code }}</span></td><td>{{ r.item.spare_type.name }}</td><td>{{ r.item.description }}</td>
      <td>{% if r.item.cat_ref and r.item.cat_ref != r.item.code %}<span class="code">{{ r.item.cat_ref }}</span><div class="text-secondary small">{{ r.item.fitting_type.name|default:"" }}</div>{% else %}{{ r.item.fitting_type.name|default:"" }}{% endif %}</td>
      <td>{{ r.item.company.name }}</td>
      {% for p in locations %}<td class="num">{{ r.per_loc|get_item:p.pk|qty }}</td>{% endfor %}
      {% if not f.location %}<td class="num">{% if r.low %}<span class="badge bg-red-lt">{{ r.total }}</span>{% else %}<b>{{ r.total }}</b>{% endif %}</td>{% endif %}
      <td>{{ r.item.unit }}</td></tr>
    {% empty %}<tr><td colspan="12" class="text-center text-secondary py-4">Nothing matches these filters.</td></tr>{% endfor %}</tbody>
  </table></div>
  {% include "core/_pagination.html" %}
</div>
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Red total = at or below the item's reorder level.</p>
{% endblock %}
```
Each location object gets a `sort_key` (`L<pk>`) in the view, so its column can be sorted.

`templates/inventory/low_stock.html`:
```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}Low stock{% endblock %}
{% block pretitle %}Reports{% endblock %}
{% block page_title %}Low stock{% endblock %}
{% block content %}
<div class="alert alert-{% if table.total %}warning{% else %}success{% endif %}"><i class="ti ti-{% if table.total %}alert-triangle{% else %}circle-check{% endif %}"></i>
  {% if table.total %}{{ table.total }} items are at or below their reorder level (total across all locations).{% else %}Nothing is low.{% endif %}</div>
<div class="card"><div class="table-responsive"><table class="table table-vcenter card-table table-striped">
  <thead><tr>{% sort_th "code" "Item code" %}{% sort_th "type" "Spare type" %}<th>Description</th><th>Company</th>
    {% for p in locations %}<th class="num">{{ p.name }}</th>{% endfor %}{% sort_th "total" "Total" True %}{% sort_th "reorder" "Reorder at" True %}{% sort_th "short" "Short by" True %}<th>Unit</th></tr></thead>
  <tbody>{% for r in table.page %}<tr><td><span class="code">{{ r.item.code }}</span></td><td>{{ r.item.spare_type.name }}</td><td>{{ r.item.description }}</td><td>{{ r.item.company.name }}</td>
    {% for p in locations %}<td class="num">{{ r.per_loc|get_item:p.pk|qty }}</td>{% endfor %}
    <td class="num"><span class="badge bg-red-lt">{{ r.total }}</span></td><td class="num">{{ r.item.reorder_level }}</td><td class="num"><b class="text-danger">{{ r.short_by }}</b></td><td>{{ r.item.unit }}</td></tr>
  {% empty %}<tr><td colspan="12" class="text-center text-secondary py-4">Nothing is low.</td></tr>{% endfor %}</tbody>
</table></div>{% include "core/_pagination.html" %}</div>
{% endblock %}
```

`templates/inventory/movements.html`:
```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}Stock movements{% endblock %}
{% block pretitle %}Reports{% endblock %}
{% block page_title %}Stock movements{% endblock %}
{% block content %}
<div class="card">
  <div class="card-header"><form method="get" class="row g-2 w-100 align-items-end">
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="m-from">From date</label><input id="m-from" type="date" name="date_from" value="{{ f.date_from|date:'Y-m-d' }}" class="form-control" onchange="this.form.submit()"></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="m-to">To date</label><input id="m-to" type="date" name="date_to" value="{{ f.date_to|date:'Y-m-d' }}" class="form-control" onchange="this.form.submit()"></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="m-kind">Type</label><select id="m-kind" name="kind" class="form-select" onchange="this.form.submit()"><option value="">All types</option>
      {% for v, label in kinds %}<option value="{{ v }}" {% if f.kind == v %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="m-loc">Location</label><select id="m-loc" name="location" class="form-select" onchange="this.form.submit()"><option value="">All locations</option>
      {% for p in all_locations %}<option value="{{ p.pk }}" {% if f.location == p %}selected{% endif %}>{{ p.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-lg-4"><label class="form-label small text-secondary mb-1" for="m-q">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
      <input id="m-q" type="search" name="q" value="{{ f.q }}" class="form-control" placeholder="Item, supplier, customer, ref"></div></div>
  </form></div>
  <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr>{% sort_th "date" "Date" %}{% sort_th "no" "Entry" %}{% sort_th "kind" "Type" %}{% sort_th "code" "Item code" %}<th>Description</th>{% sort_th "loc" "Location" %}
      {% sort_th "in" "In" True %}{% sort_th "out" "Out" True %}<th>Unit</th>{% sort_th "party" "Supplier / issued to" %}<th>Ref</th>{% sort_th "by" "By" %}</tr></thead>
    <tbody>{% for r in table.page %}<tr class="{% if r.undone %}undone{% endif %}">
      <td class="nowrap">{{ r.entry.entry_date|date }}</td><td class="code">{{ r.entry.number }}</td><td><span class="badge badge-k k-{{ r.entry.kind }}">{{ r.entry.get_kind_display }}</span></td>
      <td class="code">{{ r.line.item.code }}</td><td>{{ r.line.item.description }}</td><td>{{ r.line.location.name }}</td>
      <td class="num">{% if r.line.qty > 0 %}<span class="qty-in">+{{ r.line.qty }}</span>{% endif %}</td>
      <td class="num">{% if r.line.qty < 0 %}<span class="qty-out">−{{ r.line.qty|stringformat:"d"|slice:"1:" }}</span>{% endif %}</td>
      <td>{{ r.line.item.unit }}</td><td>{{ r.entry.party|default:r.entry.get_reason_display }}</td><td>{{ r.entry.ref }}</td><td>{{ r.entry.created_by.first_name|default:r.entry.created_by.username }}</td></tr>
    {% empty %}<tr><td colspan="12" class="text-center text-secondary py-4">No movements in this period.</td></tr>{% endfor %}</tbody>
  </table></div>
  {% include "core/_pagination.html" %}
</div>
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Struck-through rows were undone; an "Undo" entry reverses them.</p>
{% endblock %}
```

Run the tests:
```bash
DATABASE_URL="<url>" uv run pytest -q    # expected: all pass
```

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff format . && uv run ruff check .
git add apps templates tests
git commit -m "feat: current stock, low stock and movements lists with filters, sorting and paging"
```

---

### Task 8: Items (list, add/edit form, item card with history, quick create)

**Files:**
- Create: `apps/inventory/forms.py`, `templates/inventory/items.html`, `templates/inventory/item_form.html`, `templates/inventory/_item_fields.html`, `templates/inventory/item_detail.html`
- Modify: `apps/inventory/selectors.py`, `apps/inventory/views.py`, `apps/inventory/urls.py`, `templates/inventory/current_stock.html`, `templates/inventory/low_stock.html`, `templates/inventory/movements.html` (item codes become links)
- Test: `tests/inventory/test_items_views.py`

- [ ] **Step 1: Write failing tests** — `tests/inventory/test_items_views.py`

```python
import pytest
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, Item, SpareType
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db


def form_data(**over):
    data = {"code": "MCB 32A DP", "spare_type": SpareType.objects.get(name="Accessory").pk,
            "company": Company.objects.get(name="Havells").pk, "description": "MCB 32A double pole", "cat_ref": "",
            "fitting_type": "", "wattage_w": "", "current_ma": "", "unit": "NOS", "reorder_level": "4",
            "aliases": "MCB-32A-DP", "is_active": "on"}
    data.update(over)
    return data


def test_items_list_filters(office_client):
    make_item("EIO6006", spare_type="PCB / LED module")
    make_item("LENS", spare_type="Lens")
    html = office_client.get("/items/?q=eio").content.decode()
    assert "EIO6006" in html and "LENS" not in html


def test_create_item(office_client):
    response = office_client.post("/items/new/", form_data())
    item = Item.objects.get(code="MCB 32A DP")
    assert response.status_code == 302 and response.url == f"/items/{item.pk}/"
    assert list(item.aliases.values_list("alias", flat=True)) == ["MCB-32A-DP"]


def test_create_item_lookalike_refused(office_client):
    make_item("LG30-018-054-0300")
    html = office_client.post("/items/new/", form_data(code="lg30-018-054-300", aliases="")).content.decode()
    assert "looks the same as LG30-018-054-0300" in html and not Item.objects.filter(code="LG30-018-054-300").exists()


def test_edit_item(office_client):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    response = office_client.post(f"/items/{item.pk}/edit/", form_data(code="EIO6006", description="LED module 9W", aliases=""))
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.description == "LED module 9W"


def test_item_detail_history_and_running_balance(office_client, office_user):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    today = timezone.localdate()
    post_entry(kind=EntryKind.IN, entry_date=today, lines=[Line(item, loc(), 9)], user=office_user)
    post_entry(kind=EntryKind.OUT, entry_date=today, lines=[Line(item, loc(), -2)], user=office_user, subtype="SITE", party="BARC")
    html = office_client.get(f"/items/{item.pk}/").content.decode()
    assert "Movement history" in html and "IN-0001" in html and "OUT-0001" in html
    assert "<b>7</b>" in html  # balance after the OUT


def test_quick_create_json(office_client):
    ok = office_client.post("/items/quick-create/", form_data(code="LG99-200-700X", aliases="")).json()
    assert ok["ok"] and ok["item"]["code"] == "LG99-200-700X" and ok["item"]["unit"] == "NOS"
    bad = office_client.post("/items/quick-create/", form_data(code="LG99-200-700X", aliases="")).json()
    assert not bad["ok"] and "already exists" in bad["error"]


def test_check_code_json(office_client):
    make_item("EIO8437", spare_type="PCB / LED module")
    assert office_client.get("/items/check-code/?code=ei08437").json()["status"] == "clash"
    assert office_client.get("/items/check-code/?code=NEW-1").json()["status"] == "ok"
```

Run: expected FAIL.

- [ ] **Step 2: `apps/inventory/forms.py`**

```python
from django import forms

from .models import Company, FittingType, SpareType, Unit


class TablerFormMixin:
    """Give every widget Tabler classes; mark invalid fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-select" if isinstance(field.widget, forms.Select) else (
                "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control")
            if self.errors.get(name):
                css += " is-invalid"
            field.widget.attrs["class"] = css


class ItemForm(TablerFormMixin, forms.Form):
    code = forms.CharField(max_length=80, label="Item code",
                           widget=forms.TextInput(attrs={"placeholder": "e.g. LG66-040-078-480IT", "autocomplete": "off"}))
    spare_type = forms.ModelChoiceField(SpareType.objects.filter(is_active=True), empty_label="Choose…")
    company = forms.ModelChoiceField(Company.objects.filter(is_active=True), label="Company / brand", empty_label=None)
    description = forms.CharField(max_length=200, required=False,
                                  widget=forms.TextInput(attrs={"placeholder": "e.g. LED driver 40W 480mA"}))
    cat_ref = forms.CharField(max_length=80, required=False, label="Used in fitting (Product Cat Ref)",
                              widget=forms.TextInput(attrs={"placeholder": "e.g. LF40-192-060-57-HE", "list": "cat-refs"}))
    fitting_type = forms.ModelChoiceField(FittingType.objects.filter(is_active=True), required=False, empty_label="None")
    wattage_w = forms.IntegerField(min_value=0, required=False, label="Wattage")
    current_ma = forms.IntegerField(min_value=0, required=False, label="Current")
    unit = forms.ChoiceField(choices=Unit.choices, initial=Unit.NOS)
    reorder_level = forms.IntegerField(min_value=0, initial=0, label="Reorder level")
    aliases = forms.CharField(required=False, label="Other spellings of this code",
                              widget=forms.TextInput(attrs={"placeholder": "e.g. EI08437, EIO-8437"}))
    is_active = forms.BooleanField(required=False, initial=True, label="Active")

    def clean_aliases(self):
        return [a.strip() for a in self.cleaned_data["aliases"].split(",") if a.strip()]

    @classmethod
    def initial_from(cls, item):
        return {"code": item.code, "spare_type": item.spare_type_id, "company": item.company_id, "description": item.description,
                "cat_ref": item.cat_ref, "fitting_type": item.fitting_type_id, "wattage_w": item.wattage_w,
                "current_ma": item.current_ma, "unit": item.unit, "reorder_level": item.reorder_level,
                "aliases": ", ".join(item.aliases.values_list("alias", flat=True)), "is_active": item.is_active}
```

- [ ] **Step 3: Selectors for items** (append to `apps/inventory/selectors.py`; add `FittingType` to the models import)

```python
def item_rows(f):
    """Items list rows: {item, total, low}."""
    items = _filtered_items(f).prefetch_related("aliases")
    if f.fitting_type:
        items = items.filter(fitting_type=f.fitting_type)
    if f.status:
        items = items.filter(is_active=f.status == "1")
    totals = item_totals()
    return [{"item": i, "total": totals.get(i.pk, 0), "low": is_low(i, totals.get(i.pk, 0))} for i in items]


def item_history(item, date_from, date_to, location=None):
    """Lines for one item, newest first, each with the running balance at its location after that line."""
    undone = StockEntry.objects.filter(reverses=OuterRef("entry_id"))
    lines = (StockLine.objects.filter(item=item).select_related("entry", "entry__created_by", "location")
             .annotate(undone=Exists(undone)).order_by("entry__entry_date", "entry_id", "id"))
    running, rows = defaultdict(int), []
    for line in lines:
        running[line.location_id] += line.qty
        if date_from <= line.entry.entry_date <= date_to and (location is None or line.location_id == location.pk):
            rows.append({"entry": line.entry, "line": line, "after": running[line.location_id], "undone": line.undone})
    return list(reversed(rows))


def picker_option(item):
    """Data the searchable item picker needs (also used by the global search)."""
    return {"id": item.pk, "code": item.code, "type": item.spare_type.name, "desc": item.description, "cat": item.cat_ref,
            "company": item.company.name, "unit": item.unit,
            "aliases": [a.alias for a in item.aliases.all()]}
```

- [ ] **Step 4: Views and URLs**

Append to `apps/inventory/views.py` (imports: `from django.contrib import messages`, `from django.http import JsonResponse`, `from django.shortcuts import get_object_or_404, redirect`, `from django.views.decorators.http import require_POST`, `from .filters import item_filters`, `from .forms import ItemForm`, `from .models import FittingType, Item`, `from .normalise import normalise_code`, `from .services import ItemError, find_item_by_code, save_item`, `from datetime import date, timedelta`):
```python
def _item_form_context(form, item=None):
    return {"form": form, "item": item, "cat_refs": Item.objects.exclude(cat_ref="").values_list("cat_ref", flat=True).distinct()}


@role_required(OFFICE)
def items(request):
    f = item_filters(request.GET)
    rows = selectors.item_rows(f)
    sorters = {"code": lambda r: r["item"].code, "type": lambda r: r["item"].spare_type.name,
               "desc": lambda r: r["item"].description, "cat": lambda r: r["item"].cat_ref,
               "watt": lambda r: r["item"].wattage_w, "company": lambda r: r["item"].company.name,
               "unit": lambda r: r["item"].unit, "reorder": lambda r: r["item"].reorder_level, "stock": lambda r: r["total"]}
    table = sort_and_page(request, rows, sorters, "code")
    return render(request, "inventory/items.html", {"f": f, "table": table, "fitting_types": FittingType.objects.filter(is_active=True), **_masters()})


@role_required(OFFICE)
def item_new(request):
    form = ItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            item = save_item(data=form.cleaned_data)
        except ItemError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, f"Item {item.code} saved.")
            return redirect("item_detail", pk=item.pk)
    return render(request, "inventory/item_form.html", _item_form_context(form))


@role_required(OFFICE)
def item_edit(request, pk):
    item = get_object_or_404(Item, pk=pk)
    form = ItemForm(request.POST or None, initial=ItemForm.initial_from(item))
    if request.method == "POST" and form.is_valid():
        try:
            item = save_item(item=item, data=form.cleaned_data)
        except ItemError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, f"Item {item.code} saved.")
            return redirect("item_detail", pk=item.pk)
    return render(request, "inventory/item_form.html", _item_form_context(form, item))


@role_required(OFFICE)
def item_detail(request, pk):
    item = get_object_or_404(Item.objects.select_related("spare_type", "company", "fitting_type"), pk=pk)
    today = timezone.localdate()
    try:
        date_from = date.fromisoformat(request.GET.get("date_from", ""))
    except ValueError:
        date_from = today - timedelta(days=30)
    try:
        date_to = date.fromisoformat(request.GET.get("date_to", ""))
    except ValueError:
        date_to = today
    location = Location.objects.filter(pk=request.GET.get("location") or None).first()
    bal = selectors.balance_map()
    places = list(Location.objects.filter(is_active=True))
    per_loc = [(p, bal.get((item.pk, p.pk), 0)) for p in places]
    total = sum(q for _, q in per_loc)
    return render(request, "inventory/item_detail.html", {
        "item": item, "per_loc": per_loc, "total": total, "low": selectors.is_low(item, total),
        "history": selectors.item_history(item, date_from, date_to, location),
        "date_from": date_from, "date_to": date_to, "location": location, "all_locations": places,
    })


@role_required(OFFICE)
@require_POST
def item_quick_create(request):
    """Create an item from the Stock IN form's modal; returns JSON for the item picker."""
    form = ItemForm(request.POST)
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        return JsonResponse({"ok": False, "error": first})
    try:
        item = save_item(data=form.cleaned_data)
    except ItemError as exc:
        return JsonResponse({"ok": False, "error": exc.message})
    return JsonResponse({"ok": True, "item": selectors.picker_option(item)})


@role_required(OFFICE)
def item_check_code(request):
    """Live hint while typing a code: ok / clash (exact or look-alike)."""
    code, original = request.GET.get("code", ""), request.GET.get("original", "")
    if not normalise_code(code):
        return JsonResponse({"status": "empty", "message": ""})
    hit = find_item_by_code(code)
    if hit and hit.code != normalise_code(original):
        msg = f"{hit.code} already exists." if hit.code == normalise_code(code) else f"Looks like existing item {hit.code}. Use that instead?"
        return JsonResponse({"status": "clash", "message": msg})
    return JsonResponse({"status": "ok", "message": f"Will be saved as {normalise_code(code)}"})
```

Add to `apps/inventory/urls.py`:
```python
    path("items/", views.items, name="items"),
    path("items/new/", views.item_new, name="item_new"),
    path("items/quick-create/", views.item_quick_create, name="item_quick_create"),
    path("items/check-code/", views.item_check_code, name="item_check_code"),
    path("items/<int:pk>/", views.item_detail, name="item_detail"),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
```

- [ ] **Step 5: Templates**

`templates/inventory/_item_fields.html` (used by the item page and the quick-create modal):
```html
<div class="row g-3">
  <div class="col-12 col-md-4"><label class="form-label required" for="{{ form.code.id_for_label }}">Item code</label>{{ form.code }}
    <small class="form-hint" id="code-hint" data-url="{% url 'item_check_code' %}" data-original="{{ item.code|default:'' }}"></small>{{ form.code.errors }}</div>
  <div class="col-12 col-md-4"><label class="form-label required" for="{{ form.spare_type.id_for_label }}">Spare type</label>{{ form.spare_type }}{{ form.spare_type.errors }}</div>
  <div class="col-12 col-md-4"><label class="form-label required" for="{{ form.company.id_for_label }}">Company / brand</label>{{ form.company }}</div>
  <div class="col-12"><label class="form-label" for="{{ form.description.id_for_label }}">Description</label>{{ form.description }}</div>
  <div class="col-12 col-md-4"><label class="form-label" for="{{ form.cat_ref.id_for_label }}">Used in fitting (Product Cat Ref)</label>{{ form.cat_ref }}<small class="form-hint">The fitting this spare belongs to (optional).</small></div>
  <div class="col-12 col-md-4"><label class="form-label" for="{{ form.fitting_type.id_for_label }}">Fitting type</label>{{ form.fitting_type }}</div>
  <div class="col-6 col-md-2"><label class="form-label" for="{{ form.wattage_w.id_for_label }}">Wattage</label><div class="input-group">{{ form.wattage_w }}<span class="input-group-text">W</span></div></div>
  <div class="col-6 col-md-2"><label class="form-label" for="{{ form.current_ma.id_for_label }}">Current</label><div class="input-group">{{ form.current_ma }}<span class="input-group-text">mA</span></div></div>
  <div class="col-12 col-md-4"><label class="form-label required" for="{{ form.unit.id_for_label }}">Unit</label>{{ form.unit }}</div>
  <div class="col-12 col-md-4"><label class="form-label" for="{{ form.reorder_level.id_for_label }}">Reorder level</label>{{ form.reorder_level }}<small class="form-hint">Warn when total stock falls to this.</small></div>
  <div class="col-12 col-md-4"><label class="form-label" for="{{ form.aliases.id_for_label }}">Other spellings of this code</label>{{ form.aliases }}<small class="form-hint">Comma separated. Searching any of these finds this item.</small></div>
</div>
<datalist id="cat-refs">{% for c in cat_refs %}<option value="{{ c }}">{% endfor %}</datalist>
```

`templates/inventory/item_form.html`:
```html
{% extends "base.html" %}
{% block title %}{% if item %}Edit {{ item.code }}{% else %}Add item{% endif %}{% endblock %}
{% block pretitle %}Setup · Items{% endblock %}
{% block page_title %}{% if item %}Edit item <span class="code">{{ item.code }}</span>{% else %}<i class="ti ti-plus"></i> Add item{% endif %}{% endblock %}
{% block content %}
<form method="post" novalidate>{% csrf_token %}
  <div class="card"><div class="card-body">{% include "inventory/_item_fields.html" %}
    {% if item %}<label class="form-check form-switch mt-3">{{ form.is_active }}<span class="form-check-label">Active (untick to hide from entry forms; history is kept)</span></label>{% else %}<input type="hidden" name="is_active" value="on">{% endif %}</div>
    <div class="card-footer d-flex"><div class="ms-auto btn-list"><a href="{% if item %}{% url 'item_detail' item.pk %}{% else %}{% url 'items' %}{% endif %}" class="btn btn-link link-secondary">Cancel</a>
      <button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Save item</button></div></div></div>
  {% if form.non_field_errors %}<div class="alert alert-danger mt-3" role="alert"><i class="ti ti-alert-circle"></i> {{ form.non_field_errors.0 }}</div>{% endif %}
</form>
{% endblock %}
{% block scripts %}<script>
(function () { // live hint: exact duplicate or look-alike code
  const input = document.getElementById("id_code"), hint = document.getElementById("code-hint");
  let t; input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const r = await fetch(`${hint.dataset.url}?code=${encodeURIComponent(input.value)}&original=${encodeURIComponent(hint.dataset.original)}`);
    const d = await r.json(); hint.textContent = d.message;
    hint.className = d.status === "clash" ? "invalid-feedback d-block" : "form-hint";
    input.classList.toggle("is-invalid", d.status === "clash"); }, 250); });
})();
</script>{% endblock %}
```

`templates/inventory/items.html`:
```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}Items{% endblock %}
{% block pretitle %}Setup{% endblock %}
{% block page_title %}Items{% endblock %}
{% block actions %}<a href="{% url 'item_new' %}" class="btn btn-primary"><i class="ti ti-plus"></i> Add item</a>{% block export_button %}{% endblock %}{% endblock %}
{% block content %}
<div class="card">
  <div class="card-header"><form method="get" class="row g-2 w-100 align-items-end">
    <div class="col-12 col-lg-4"><label class="form-label small text-secondary mb-1" for="i-q">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
      <input id="i-q" type="search" name="q" value="{{ f.q }}" class="form-control" placeholder="Code, old spelling, description, fitting"></div></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="i-type">Spare type</label><select id="i-type" name="spare_type" class="form-select" onchange="this.form.submit()"><option value="">All</option>
      {% for t in spare_types %}<option value="{{ t.pk }}" {% if f.spare_type == t %}selected{% endif %}>{{ t.name }}</option>{% endfor %}</select></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="i-co">Company</label><select id="i-co" name="company" class="form-select" onchange="this.form.submit()"><option value="">All</option>
      {% for c in companies %}<option value="{{ c.pk }}" {% if f.company == c %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="i-ft">Fitting type</label><select id="i-ft" name="fitting_type" class="form-select" onchange="this.form.submit()"><option value="">All</option>
      {% for t in fitting_types %}<option value="{{ t.pk }}" {% if f.fitting_type == t %}selected{% endif %}>{{ t.name }}</option>{% endfor %}</select></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="i-st">Status</label><select id="i-st" name="status" class="form-select" onchange="this.form.submit()">
      <option value="1" {% if f.status == "1" %}selected{% endif %}>Active</option><option value="0" {% if f.status == "0" %}selected{% endif %}>Inactive</option><option value="" {% if f.status == "" %}selected{% endif %}>All</option></select></div>
  </form></div>
  <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr>{% sort_th "code" "Item code" %}{% sort_th "type" "Spare type" %}{% sort_th "desc" "Description" %}{% sort_th "cat" "Product cat ref" %}{% sort_th "watt" "W" True %}
      {% sort_th "company" "Company" %}{% sort_th "unit" "Unit" %}{% sort_th "reorder" "Reorder at" True %}{% sort_th "stock" "In stock" True %}<th></th></tr></thead>
    <tbody>{% for r in table.page %}<tr>
      <td><a class="code" href="{% url 'item_detail' r.item.pk %}">{{ r.item.code }}</a>{% with al=r.item.aliases.all %}{% if al %}<div class="text-secondary small">also: {{ al|join:", " }}</div>{% endif %}{% endwith %}</td>
      <td>{{ r.item.spare_type.name }}</td><td>{{ r.item.description }}</td><td><span class="code">{{ r.item.cat_ref }}</span><div class="text-secondary small">{{ r.item.fitting_type.name|default:"" }}</div></td>
      <td class="num">{{ r.item.wattage_w|default_if_none:"" }}</td><td>{{ r.item.company.name }}</td><td>{{ r.item.unit }}</td><td class="num">{{ r.item.reorder_level }}</td>
      <td class="num">{% if r.low %}<span class="badge bg-red-lt">{{ r.total }}</span>{% else %}{{ r.total }}{% endif %}</td>
      <td><a href="{% url 'item_edit' r.item.pk %}" class="btn btn-sm btn-ghost-primary"><i class="ti ti-edit"></i> Edit</a></td></tr>
    {% empty %}<tr><td colspan="10" class="text-center text-secondary py-4">No items match.</td></tr>{% endfor %}</tbody>
  </table></div>
  {% include "core/_pagination.html" %}
</div>
{% endblock %}
```

`templates/inventory/item_detail.html`:
```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}{{ item.code }}{% endblock %}
{% block pretitle %}{{ item.spare_type.name }} · {{ item.company.name }}{% endblock %}
{% block page_title %}<span class="code">{{ item.code }}</span>{% if low %} <span class="badge bg-red-lt ms-2">Low stock</span>{% endif %}{% endblock %}
{% block actions %}
  {% if nav_urls.stock_in %}<a href="{{ nav_urls.stock_in }}?item={{ item.pk }}" class="btn btn-in"><i class="ti ti-package-import"></i> Stock IN</a>{% endif %}
  {% if nav_urls.stock_out %}<a href="{{ nav_urls.stock_out }}?item={{ item.pk }}" class="btn btn-out"><i class="ti ti-package-export"></i> Stock OUT</a>{% endif %}
  <a href="{% url 'item_edit' item.pk %}" class="btn btn-outline-secondary"><i class="ti ti-edit"></i> Edit</a>
{% endblock %}
{% block content %}
<div class="row row-cards">
  <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
    {% if item.description %}<div class="datagrid-item"><div class="datagrid-title">Description</div><div class="datagrid-content">{{ item.description }}</div></div>{% endif %}
    <div class="datagrid-item"><div class="datagrid-title">Spare type</div><div class="datagrid-content">{{ item.spare_type.name }}</div></div>
    {% if item.cat_ref and item.cat_ref != item.code %}<div class="datagrid-item"><div class="datagrid-title">Used in fitting</div><div class="datagrid-content code">{{ item.cat_ref }}</div></div>{% endif %}
    {% if item.fitting_type %}<div class="datagrid-item"><div class="datagrid-title">Fitting type</div><div class="datagrid-content">{{ item.fitting_type.name }}</div></div>{% endif %}
    {% if item.wattage_w %}<div class="datagrid-item"><div class="datagrid-title">Wattage</div><div class="datagrid-content">{{ item.wattage_w }} W</div></div>{% endif %}
    {% if item.current_ma %}<div class="datagrid-item"><div class="datagrid-title">Current</div><div class="datagrid-content">{{ item.current_ma }} mA</div></div>{% endif %}
    <div class="datagrid-item"><div class="datagrid-title">Company</div><div class="datagrid-content">{{ item.company.name }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Unit</div><div class="datagrid-content">{{ item.unit }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Reorder level</div><div class="datagrid-content">{{ item.reorder_level }} {{ item.unit }}</div></div>
    {% with al=item.aliases.all %}{% if al %}<div class="datagrid-item"><div class="datagrid-title">Other spellings</div><div class="datagrid-content">{{ al|join:", " }}</div></div>{% endif %}{% endwith %}
    <div class="datagrid-item"><div class="datagrid-title">Status</div><div class="datagrid-content">{% if item.is_active %}<span class="badge bg-green-lt">Active</span>{% else %}<span class="badge bg-secondary-lt">Inactive</span>{% endif %}</div></div>
  </div></div></div></div>
  <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">Stock by location</h3></div><div class="list-group list-group-flush">
    {% for p, q in per_loc %}<div class="list-group-item d-flex"><span>{{ p.name }}</span><span class="ms-auto fw-bold">{{ q|qty }} <span class="text-secondary fw-normal">{{ item.unit }}</span></span></div>{% endfor %}
    <div class="list-group-item d-flex bg-light"><b>Total</b><span class="ms-auto fw-bold">{{ total }} {{ item.unit }}</span></div></div></div></div>
  <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">Movement history</h3>{% block export_history %}{% endblock %}</div>
    <div class="card-body border-bottom py-3"><form method="get" class="row g-2">
      <div class="col-6 col-lg-3"><label class="form-label small text-secondary mb-1" for="h-from">From date</label><input id="h-from" type="date" name="date_from" value="{{ date_from|date:'Y-m-d' }}" class="form-control" onchange="this.form.submit()"></div>
      <div class="col-6 col-lg-3"><label class="form-label small text-secondary mb-1" for="h-to">To date</label><input id="h-to" type="date" name="date_to" value="{{ date_to|date:'Y-m-d' }}" class="form-control" onchange="this.form.submit()"></div>
      <div class="col-12 col-lg-3"><label class="form-label small text-secondary mb-1" for="h-loc">Location</label><select id="h-loc" name="location" class="form-select" onchange="this.form.submit()"><option value="">All locations</option>
        {% for p in all_locations %}<option value="{{ p.pk }}" {% if location == p %}selected{% endif %}>{{ p.name }}</option>{% endfor %}</select></div></form></div>
    <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
      <thead><tr><th>Date</th><th>Entry</th><th>Type</th><th>Location</th><th class="num">In</th><th class="num">Out</th><th class="num">Balance at location</th><th>Supplier / issued to</th><th>Ref</th><th>By</th></tr></thead>
      <tbody>{% for r in history %}<tr class="{% if r.undone %}undone{% endif %}"><td class="nowrap">{{ r.entry.entry_date|date }}</td><td class="code">{{ r.entry.number }}</td>
        <td><span class="badge badge-k k-{{ r.entry.kind }}">{{ r.entry.get_kind_display }}</span></td><td>{{ r.line.location.name }}</td>
        <td class="num">{% if r.line.qty > 0 %}<span class="qty-in">+{{ r.line.qty }}</span>{% endif %}</td>
        <td class="num">{% if r.line.qty < 0 %}<span class="qty-out">−{{ r.line.qty|stringformat:"d"|slice:"1:" }}</span>{% endif %}</td>
        <td class="num"><b>{{ r.after }}</b></td><td>{{ r.entry.party|default:r.entry.get_reason_display }}</td><td>{{ r.entry.ref }}</td><td>{{ r.entry.created_by.first_name|default:r.entry.created_by.username }}</td></tr>
      {% empty %}<tr><td colspan="10" class="text-center text-secondary py-4">No movements in this period.</td></tr>{% endfor %}</tbody>
    </table></div></div></div>
</div>
{% endblock %}
```

In `current_stock.html`, `low_stock.html` and `movements.html`, change item code cells to links: `<a class="code" href="{% url 'item_detail' r.item.pk %}">{{ r.item.code }}</a>` (in movements use `r.line.item`).

- [ ] **Step 6: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q
uv run ruff format . && uv run ruff check .
git add apps templates tests
git commit -m "feat: items list, add/edit with look-alike checks, item card with history, quick-create API"
```

---
### Task 9: Entry forms (Stock IN / OUT / Transfer / Adjust), entry detail, Undo

**Files:**
- Modify: `apps/inventory/forms.py`, `apps/inventory/selectors.py` (`picker_option` gets `keys`), `apps/inventory/views.py`, `apps/inventory/urls.py`, `templates/inventory/_entries_table.html`, `templates/inventory/movements.html`, `templates/inventory/item_detail.html`, `templates/inventory/item_form.html`
- Create: `apps/inventory/entry_lines.py`, `templates/inventory/entry_form.html`, `templates/inventory/entry_detail.html`, `static/js/entry-form.js`, `static/js/code-hint.js`
- Test: `tests/inventory/test_entry_lines.py`, `tests/inventory/test_entry_views.py`

How the page works (mirrors the approved mockup `mockups/stock/forms.js`):
- The server renders the header fields (Django form) and an empty `<tbody>`.
- `entry-form.js` builds one line row per item. Each row has a Tom Select item picker over the embedded `items-data` JSON. It shows "Available" from the embedded `balances-data` JSON for the chosen location, plus a live "Only N available" error.
- Each row posts as parallel arrays: `line_item`, `line_qty`, `line_batch`, `line_pkd` (`YYYY-MM`).
- On Stock IN, typing an unknown code offers "＋ Create new item…". This opens a Bootstrap modal holding the same item fields, posts to `item_quick_create`, and adds the new item to the picker.
- If the server rejects the POST, the page re-renders with the error and the posted lines (`initial-lines` JSON), so nothing typed is lost.

- [ ] **Step 1: Write failing tests**

`tests/inventory/test_entry_lines.py`:
```python
import pytest
from django.http import QueryDict

from apps.inventory.entry_lines import raw_lines, parse_lines
from apps.inventory.services import StockError
from tests.factories import make_item

pytestmark = pytest.mark.django_db


def post(*rows):
    q = QueryDict(mutable=True)
    for item, qty, batch, pkd in rows:
        q.appendlist("line_item", str(item)), q.appendlist("line_qty", str(qty))
        q.appendlist("line_batch", batch), q.appendlist("line_pkd", pkd)
    return raw_lines(q)


def test_parses_lines_and_skips_blank_rows():
    a = make_item("EIO6006")
    parsed = parse_lines(post((a.pk, 3, "B1", "2026-05"), ("", "", "", "")), "in")
    assert len(parsed) == 1
    item, qty, batch, pkd = parsed[0]
    assert (item, qty, batch, pkd.isoformat()) == (a, 3, "B1", "2026-05-01")


@pytest.mark.parametrize("rows,mode,msg", [
    ([], "in", "Add at least one item."),
    ([("", 3, "", "")], "out", "Line 1: choose an item."),
    ([("ITEM", "2.5", "", "")], "out", "Line 1: enter a whole-number quantity of 1 or more."),
    ([("ITEM", 0, "", "")], "trf", "Line 1: enter a whole-number quantity of 1 or more."),
    ([("ITEM", -1, "", "")], "adj", "Line 1: enter a whole-number counted quantity (0 or more)."),
    ([("ITEM", 1, "", ""), ("ITEM", 2, "", "")], "out", "The same item is on two lines. Combine them into one line."),
    ([("ITEM", 1, "", "13-2026")], "in", "Line 1: PKD must be a month like 2026-05."),
])
def test_line_errors(rows, mode, msg):
    a = make_item("EIO6006")
    rows = [(a.pk if r[0] == "ITEM" else r[0], *r[1:]) for r in rows]
    with pytest.raises(StockError, match=msg):
        parse_lines(post(*rows), mode)


def test_adjust_allows_zero_and_inactive_items_are_refused():
    a = make_item("EIO6006")
    assert parse_lines(post((a.pk, 0, "", "")), "adj")[0][1] == 0
    b = make_item("OLD-1", is_active=False)
    with pytest.raises(StockError, match="Line 1: choose an item."):
        parse_lines(post((b.pk, 1, "", "")), "in")
```

`tests/inventory/test_entry_views.py`:
```python
import datetime

import pytest
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, StockEntry
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate().isoformat()


def lines(*rows):
    data = {"line_item": [], "line_qty": [], "line_batch": [], "line_pkd": []}
    for item, qty in rows:
        data["line_item"].append(str(item.pk)), data["line_qty"].append(str(qty))
        data["line_batch"].append(""), data["line_pkd"].append("")
    return data


def test_stock_in_from_supplier(office_client):
    a = make_item("EIO6006")
    wipro = Company.objects.get(name="Wipro Lighting")
    r = office_client.post("/stock/in/", {"entry_date": TODAY, "subtype": "SUPPLIER", "company": wipro.pk, "party": "",
                                           "location": loc().pk, "ref": "DC 1", "note": "", **lines((a, 5))})
    entry = StockEntry.objects.get()
    assert r.status_code == 302 and r.url == "/entries/IN-0001/"
    assert (entry.party, entry.company, entry.subtype) == ("Wipro Lighting", wipro, "SUPPLIER")


def test_stock_in_needs_supplier(office_client):
    a = make_item("EIO6006")
    html = office_client.post("/stock/in/", {"entry_date": TODAY, "subtype": "SUPPLIER", "company": "", "party": "",
                                              "location": loc().pk, **lines((a, 5))}).content.decode()
    assert "Choose the supplier." in html and not StockEntry.objects.exists()
    assert '"item": ' in html  # the typed lines come back to the page


def test_stock_out_over_issue_refused(office_client, office_user):
    a = make_item("EIO6006")
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 2)], user=office_user)
    html = office_client.post("/stock/out/", {"entry_date": TODAY, "subtype": "SITE", "party": "BARC",
                                               "location": loc().pk, **lines((a, 5))}).content.decode()
    assert "Only 2 NOS of EIO6006 at Vizag Office. Nothing was saved." in html
    assert StockEntry.objects.count() == 1


def test_transfer(office_client, office_user):
    a = make_item("EIO6006")
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 4)], user=office_user)
    r = office_client.post("/stock/transfer/", {"entry_date": TODAY, "location": loc().pk, "to_location": loc("TV Shop").pk,
                                                **lines((a, 3))})
    assert r.url == "/entries/TRF-0001/"
    assert StockEntry.objects.get(number="TRF-0001").party == "TV Shop"


def test_transfer_same_location_refused(office_client):
    a = make_item("EIO6006")
    html = office_client.post("/stock/transfer/", {"entry_date": TODAY, "location": loc().pk, "to_location": loc().pk,
                                                   **lines((a, 3))}).content.decode()
    assert "From and To locations must be different." in html


def test_adjust_posts_difference(office_client, office_user):
    a = make_item("EIO6006")
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 4)], user=office_user)
    r = office_client.post("/stock/adjust/", {"entry_date": TODAY, "location": loc().pk, "reason": "DAMAGED",
                                              "note": "2 cracked", **lines((a, 2))})
    assert r.url == "/entries/ADJ-0001/"
    assert StockEntry.objects.get(number="ADJ-0001").lines.get().qty == -2


def test_future_date_refused(office_client):
    a = make_item("EIO6006")
    future = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
    html = office_client.post("/stock/out/", {"entry_date": future, "subtype": "SITE", "party": "X",
                                               "location": loc().pk, **lines((a, 1))}).content.decode()
    assert "The date can&#x27;t be in the future." in html


def test_entry_detail_and_undo(office_client, office_user):
    a = make_item("EIO6006")
    entry = post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 4)], user=office_user,
                       subtype="SUPPLIER", party="Wipro Lighting")
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert "IN-0001" in html and "EIO6006" in html and "Undo this entry" in html
    r = office_client.post(f"/entries/{entry.number}/undo/", {"reason": "typed wrong qty"})
    assert r.url == "/entries/REV-0001/"
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert "Undone by" in html and "Undo this entry" not in html


def test_undo_needs_reason(office_client, office_user):
    a = make_item("EIO6006")
    entry = post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 4)], user=office_user)
    r = office_client.post(f"/entries/{entry.number}/undo/", {"reason": " "}, follow=True)
    assert "Please give a reason." in r.content.decode()


def test_prefill_item_from_query(office_client):
    a = make_item("EIO6006")
    html = office_client.get(f"/stock/out/?item={a.pk}").content.decode()
    assert f'"item": "{a.pk}"' in html
```

Run: `DATABASE_URL="<url>" uv run pytest tests/inventory/test_entry_lines.py tests/inventory/test_entry_views.py -q`. Expected: FAIL (ImportError).

- [ ] **Step 2: `apps/inventory/entry_lines.py`**

```python
"""Read the item lines posted by the entry forms (parallel arrays line_item / line_qty / line_batch / line_pkd)."""

from datetime import date

from .models import Item
from .services import StockError

FIELDS = ("item", "qty", "batch", "pkd")


def raw_lines(post):
    """[{item, qty, batch, pkd}] exactly as typed (strings). Also sent back to the page when a POST fails."""
    columns = [post.getlist(f"line_{name}") for name in FIELDS]
    count = max((len(c) for c in columns), default=0)
    return [{name: (col[n].strip() if n < len(col) else "") for name, col in zip(FIELDS, columns)} for n in range(count)]


def _month(text, n):
    if not text:
        return None
    try:
        year, month = (int(part) for part in text.split("-"))
        return date(year, month, 1)
    except ValueError as exc:
        raise StockError(f"Line {n}: PKD must be a month like 2026-05.") from exc


def parse_lines(rows, mode):
    """[(item, qty, batch, pkd)] for mode in|out|trf|adj. Raises StockError with the first problem."""
    wanted = [r for r in rows if r["item"] or r["qty"]]
    items = Item.objects.filter(is_active=True).in_bulk([int(r["item"]) for r in wanted if r["item"].isdigit()])
    minimum = 0 if mode == "adj" else 1
    parsed = []
    for n, row in enumerate(wanted, start=1):
        item = items.get(int(row["item"])) if row["item"].isdigit() else None
        if item is None:
            raise StockError(f"Line {n}: choose an item.")
        try:
            qty = int(row["qty"])
        except ValueError:
            qty = None
        if qty is None or qty < minimum:
            what = "counted quantity (0 or more)" if mode == "adj" else "quantity of 1 or more"
            raise StockError(f"Line {n}: enter a whole-number {what}.")
        parsed.append((item, qty, row["batch"][:40], _month(row["pkd"], n)))
    if not parsed:
        raise StockError("Add at least one item.")
    if mode != "in" and len({item.pk for item, *_ in parsed}) != len(parsed):
        raise StockError("The same item is on two lines. Combine them into one line.")
    return parsed
```

- [ ] **Step 3: Header forms** — append to `apps/inventory/forms.py`

Update imports: `from django.utils import timezone`, and from `.models` add `AdjustReason, InSource, Location, OutTarget`. In `TablerFormMixin.__init__`, skip radio widgets (rendered by hand as Tabler select-groups):
```python
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.RadioSelect):
                continue
```
Then append:
```python
class EntryHeaderForm(TablerFormMixin, forms.Form):
    entry_date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    location = forms.ModelChoiceField(Location.objects.filter(is_active=True), empty_label=None)
    note = forms.CharField(required=False, label="Remarks",
                           widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entry_date"].widget.attrs["max"] = timezone.localdate().isoformat()

    def clean_entry_date(self):
        value = self.cleaned_data["entry_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("The date can't be in the future.")
        return value


class StockInForm(EntryHeaderForm):
    subtype = forms.ChoiceField(choices=InSource.choices, initial=InSource.SUPPLIER, widget=forms.RadioSelect,
                                label="Received from")
    company = forms.ModelChoiceField(Company.objects.filter(is_active=True), required=False,
                                     label="Supplier / company", empty_label="Choose…")
    party = forms.CharField(max_length=120, required=False, label="Site / customer",
                            widget=forms.TextInput(attrs={"list": "parties", "placeholder": "e.g. Dr Reddys, Vizag"}))
    ref = forms.CharField(max_length=60, required=False, label="DC / bill no.",
                          widget=forms.TextInput(attrs={"placeholder": "e.g. DC 4512"}))

    def clean(self):
        data = super().clean()
        source = data.get("subtype")
        if source == InSource.SUPPLIER:
            if not data.get("company"):
                raise forms.ValidationError("Choose the supplier.")
            data["party"] = data["company"].name
        elif source == InSource.RETURN:
            if not data.get("party", "").strip():
                raise forms.ValidationError("Enter the site / customer.")
            data["company"] = None
        elif source == InSource.OPENING:
            data["party"], data["company"] = "Opening stock (first count)", None
        return data


class StockOutForm(EntryHeaderForm):
    subtype = forms.ChoiceField(choices=OutTarget.choices, initial=OutTarget.SITE, widget=forms.RadioSelect,
                                label="Issued to")
    party = forms.CharField(max_length=120, required=False, label="Name",
                            widget=forms.TextInput(attrs={"list": "parties", "placeholder": "e.g. GMR Airport, Vizag"}))
    ref = forms.CharField(max_length=60, required=False, label="Job / reference no.",
                          widget=forms.TextInput(attrs={"placeholder": "Optional"}))

    def clean(self):
        data = super().clean()
        if data.get("subtype") and not data.get("party", "").strip():
            target = OutTarget(data["subtype"]).label.lower()
            raise forms.ValidationError(f"Enter who it was issued to ({target}).")
        return data


class TransferForm(EntryHeaderForm):
    to_location = forms.ModelChoiceField(Location.objects.filter(is_active=True), empty_label=None, label="To location")

    def clean(self):
        data = super().clean()
        if data.get("location") and data.get("location") == data.get("to_location"):
            raise forms.ValidationError("From and To locations must be different.")
        return data


class AdjustForm(EntryHeaderForm):
    reason = forms.ChoiceField(choices=[("", "Choose…"), *AdjustReason.choices])
    note = forms.CharField(label="Note", widget=forms.Textarea(
        attrs={"rows": 2, "placeholder": "What happened? e.g. 2 lenses cracked in storage"}),
        error_messages={"required": "Write a short note explaining the adjustment."})

    def clean_reason(self):
        if not self.cleaned_data["reason"]:
            raise forms.ValidationError("Choose the reason for the adjustment.")
        return self.cleaned_data["reason"]


class UndoForm(forms.Form):
    reason = forms.CharField(max_length=200)
```

- [ ] **Step 4: Picker data** — in `apps/inventory/selectors.py` replace `picker_option` (add `from .normalise import search_key`) and add `picker_data`:

```python
def picker_option(item):
    """Data the searchable item picker needs (also used by the global search)."""
    aliases = [a.alias for a in item.aliases.all()]
    return {"id": item.pk, "code": item.code, "type": item.spare_type.name, "desc": item.description, "cat": item.cat_ref,
            "company": item.company.name, "unit": item.unit, "aliases": aliases,
            "keys": " ".join(search_key(c) for c in [item.code, *aliases, item.cat_ref] if c)}


def picker_data():
    """(items, balances) for the entry forms. balances: {"<item_id>-<location_id>": qty}."""
    items = (Item.objects.filter(is_active=True).select_related("spare_type", "company")
             .prefetch_related("aliases").order_by("code"))
    return [picker_option(i) for i in items], {f"{i}-{p}": q for (i, p), q in balance_map().items()}


def recent_parties(subtype, limit=50):
    """Names used before for this IN/OUT subtype, newest first (suggestions for the 'Name' box)."""
    names = (StockEntry.objects.filter(subtype=subtype).exclude(party="").order_by("-id")
             .values_list("party", flat=True)[:500])
    return list(dict.fromkeys(names))[:limit]
```

- [ ] **Step 5: Views and URLs** — append to `apps/inventory/views.py`

Extra imports: `from .entry_lines import parse_lines, raw_lines`, `from .forms import AdjustForm, StockInForm, StockOutForm, TransferForm, UndoForm`, `from .models import InSource, OutTarget, StockEntry`, `from .services import Line, StockError, adjust_counts, post_entry, undo_entry`.
```python
ENTRY_PAGES = {
    # mode: (kind, form, title, subtitle, icon, save-button class)
    "in": (EntryKind.IN, StockInForm, "Stock IN", "Material received at a location", "package-import", "btn-in"),
    "out": (EntryKind.OUT, StockOutForm, "Stock OUT", "Material given out from a location", "package-export", "btn-out"),
    "trf": (EntryKind.TRF, TransferForm, "Transfer stock", "Move stock from one location to another", "arrows-exchange", "btn-primary"),
    "adj": (EntryKind.ADJ, AdjustForm, "Adjust stock count", "Correct the system count after a physical check",
            "adjustments-horizontal", "btn-primary"),
}


def _default_location():
    places = Location.objects.filter(is_active=True)
    return places.filter(name="Vizag Office").first() or places.first()


def _save_entry(mode, data, parsed, user):
    kind, place, note = ENTRY_PAGES[mode][0], data["location"], data.get("note", "")
    common = {"entry_date": data["entry_date"], "user": user, "note": note}
    if mode == "in":
        return post_entry(kind=kind, lines=[Line(i, place, q, b, p) for i, q, b, p in parsed], subtype=data["subtype"],
                          party=data["party"], company=data["company"], ref=data["ref"], **common)
    if mode == "out":
        return post_entry(kind=kind, lines=[Line(i, place, -q) for i, q, _, _ in parsed], subtype=data["subtype"],
                          party=data["party"], ref=data["ref"], **common)
    if mode == "trf":
        dest = data["to_location"]
        moves = [line for i, q, _, _ in parsed for line in (Line(i, place, -q), Line(i, dest, q))]
        return post_entry(kind=kind, lines=moves, party=dest.name, **common)
    return adjust_counts(entry_date=data["entry_date"], location=place, counts=[(i, q) for i, q, _, _ in parsed],
                         reason=data["reason"], note=note, user=user)


def _entry_page(request, mode):
    kind, form_class, title, subtitle, icon, button = ENTRY_PAGES[mode]
    initial = {"entry_date": timezone.localdate(), "location": _default_location(),
               "to_location": Location.objects.filter(is_active=True, name="TV Shop").first()}
    form = form_class(request.POST or None, initial=initial)
    error, lines = None, []
    if request.method == "POST":
        lines = raw_lines(request.POST)
        if form.is_valid():
            try:
                entry = _save_entry(mode, form.cleaned_data, parse_lines(lines, mode), request.user)
            except StockError as exc:
                error = f"{exc.message} Nothing was saved."
            else:
                count = entry.lines.values("item").distinct().count()
                messages.success(request, f"{entry.number} saved · {count} item(s). Stock updated.")
                return redirect("entry_detail", number=entry.number)
        else:
            error = next(iter(form.errors.values()))[0]
    elif request.GET.get("item", "").isdigit():
        lines = [{"item": request.GET["item"], "qty": "", "batch": "", "pkd": ""}]
    items, balances = selectors.picker_data()
    parties = {s: selectors.recent_parties(s) for s in [*InSource.values, *OutTarget.values]}
    return render(request, "inventory/entry_form.html", {
        "mode": mode, "form": form, "title": title, "subtitle": subtitle, "icon": icon, "button": button, "error": error,
        "items_data": items, "balances_data": balances, "initial_lines": lines, "parties": parties,
        "item_form": ItemForm(), "cat_refs": Item.objects.exclude(cat_ref="").values_list("cat_ref", flat=True).distinct(),
    })


@role_required(OFFICE)
def stock_in(request):
    return _entry_page(request, "in")


@role_required(OFFICE)
def stock_out(request):
    return _entry_page(request, "out")


@role_required(OFFICE)
def transfer(request):
    return _entry_page(request, "trf")


@role_required(OFFICE)
def adjust(request):
    return _entry_page(request, "adj")


@role_required(OFFICE)
def entry_detail(request, number):
    entry = get_object_or_404(selectors.entries_with_lines(StockEntry.objects.all()), number=number)
    undone_by = StockEntry.objects.filter(reverses=entry).first()
    return render(request, "inventory/entry_detail.html", {
        "entry": entry, "undone_by": undone_by, "can_undo": entry.kind != EntryKind.REV and undone_by is None,
    })


@role_required(OFFICE)
@require_POST
def entry_undo(request, number):
    entry = get_object_or_404(StockEntry, number=number)
    form = UndoForm(request.POST)
    try:
        rev = undo_entry(entry=entry, reason=form.data.get("reason", ""), user=request.user)
    except StockError as exc:
        messages.error(request, exc.message)
        return redirect("entry_detail", number=number)
    messages.success(request, f"{entry.number} undone by {rev.number}. Stock updated.")
    return redirect("entry_detail", number=rev.number)
```

Add to `apps/inventory/urls.py`:
```python
    path("stock/in/", views.stock_in, name="stock_in"),
    path("stock/out/", views.stock_out, name="stock_out"),
    path("stock/transfer/", views.transfer, name="transfer"),
    path("stock/adjust/", views.adjust, name="adjust"),
    path("entries/<str:number>/", views.entry_detail, name="entry_detail"),
    path("entries/<str:number>/undo/", views.entry_undo, name="entry_undo"),
```

- [ ] **Step 6: `templates/inventory/entry_form.html`**

```html
{% extends "base.html" %}{% load static %}
{% block title %}{{ title }}{% endblock %}
{% block pretitle %}Stock{% endblock %}
{% block page_title %}<i class="ti ti-{{ icon }}"></i> {{ title }}{% endblock %}
{% block content %}
<form method="post" id="entry-form" novalidate data-mode="{{ mode }}">{% csrf_token %}
  <div class="card mb-3"><div class="card-header"><h3 class="card-title"><i class="ti ti-file-description"></i> Details</h3>
    <div class="card-subtitle ms-2 text-secondary">{{ subtitle }}</div></div>
    <div class="card-body"><div class="row g-3">
      {% if form.subtype %}<div class="col-12"><label class="form-label required">{{ form.subtype.label }}</label><div class="form-selectgroup">
        {% for value, label in form.subtype.field.choices %}<label class="form-selectgroup-item">
          <input type="radio" name="subtype" value="{{ value }}" class="form-selectgroup-input" {% if form.subtype.value == value %}checked{% endif %}>
          <span class="form-selectgroup-label">{{ label }}</span></label>{% endfor %}</div></div>{% endif %}
      <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.entry_date.id_for_label }}">Date</label>
        <div class="input-icon"><span class="input-icon-addon"><i class="ti ti-calendar"></i></span>{{ form.entry_date }}</div></div>
      <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.location.id_for_label }}">{% if mode == "in" %}Into location{% elif mode == "adj" %}Location{% else %}From location{% endif %}</label>{{ form.location }}</div>
      {% if mode == "in" %}
        <div class="col-12 col-md-3" data-show="SUPPLIER"><label class="form-label required" for="{{ form.company.id_for_label }}">Supplier / company</label>{{ form.company }}</div>
        <div class="col-12 col-md-3" data-show="RETURN"><label class="form-label required" for="{{ form.party.id_for_label }}">Site / customer</label>{{ form.party }}</div>
        <div class="col-12 col-md-3"><label class="form-label" for="{{ form.ref.id_for_label }}">DC / bill no.</label>{{ form.ref }}</div>
      {% elif mode == "out" %}
        <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.party.id_for_label }}" id="party-label">Site / customer</label>{{ form.party }}</div>
        <div class="col-12 col-md-3"><label class="form-label" for="{{ form.ref.id_for_label }}">Job / reference no.</label>{{ form.ref }}</div>
      {% elif mode == "trf" %}
        <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.to_location.id_for_label }}">To location</label>{{ form.to_location }}</div>
      {% else %}
        <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.reason.id_for_label }}">Reason</label>{{ form.reason }}</div>
      {% endif %}
      <div class="col-12"><label class="form-label {% if mode == 'adj' %}required{% endif %}" for="{{ form.note.id_for_label }}">{{ form.note.label }}</label>{{ form.note }}</div>
    </div></div></div>
  <div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-list-details"></i> Items</h3></div>
    <div class="card-body"><div class="lines-wrap"><table class="table table-vcenter lines-table mb-0"><thead><tr><th class="w-1">#</th><th>Item</th>
      {% if mode == "in" %}<th>Quantity</th><th>Batch code</th><th>PKD (packed)</th>{% elif mode == "adj" %}<th>System qty</th><th>Counted qty</th><th>Difference</th>{% else %}<th>Available</th><th>Quantity</th>{% endif %}<th></th></tr></thead>
      <tbody id="lines"></tbody></table></div>
      <button type="button" class="btn btn-outline-primary mt-3" id="add-line"><i class="ti ti-plus"></i> Add another item</button></div>
    <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span id="lines-summary" class="text-secondary"></span>
      <div class="ms-auto btn-list"><a href="{% url 'dashboard' %}" class="btn btn-link link-secondary">Cancel</a>
        <button type="submit" class="btn {{ button }}"><i class="ti ti-device-floppy"></i> Save {{ title }}</button></div></div></div>
  <div id="form-error" class="mt-3">{% if error %}<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>{{ error }}</div></div></div>{% endif %}</div>
</form>
<datalist id="parties"></datalist>
{% if mode == "in" %}
<div class="modal modal-blur fade" id="new-item-modal" tabindex="-1" aria-hidden="true"><div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content">
  <form id="new-item-form" data-url="{% url 'item_quick_create' %}" novalidate>{% csrf_token %}
    <div class="modal-header"><h5 class="modal-title"><i class="ti ti-box"></i> Create new item</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body">{% with form=item_form %}{% include "inventory/_item_fields.html" %}{% endwith %}<input type="hidden" name="is_active" value="on"><div id="ni-err" class="text-danger mt-3"></div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button>
      <button type="submit" class="btn btn-primary ms-auto"><i class="ti ti-check"></i> Create item</button></div>
  </form></div></div></div>
{% endif %}
{{ items_data|json_script:"items-data" }}{{ balances_data|json_script:"balances-data" }}{{ initial_lines|json_script:"initial-lines" }}{{ parties|json_script:"parties-data" }}
{% endblock %}
{% block scripts %}<script src="{% static 'vendor/tom-select.complete.min.js' %}"></script>
<script src="{% static 'js/code-hint.js' %}"></script><script src="{% static 'js/entry-form.js' %}"></script>{% endblock %}
```

`json_script` output uses `"item": "5"` with a space after the colon. The tests rely on that.

- [ ] **Step 7: `static/js/code-hint.js`** (shared by the item page and the quick-create modal)

```javascript
/* Live hint under an item-code box: "Will be saved as …", or an exact / look-alike clash with an existing item. */
(function () {
  const input = document.getElementById("id_code"), hint = document.getElementById("code-hint");
  if (!input || !hint) return;
  let timer;
  const check = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const url = `${hint.dataset.url}?code=${encodeURIComponent(input.value)}&original=${encodeURIComponent(hint.dataset.original)}`;
      const data = await (await fetch(url)).json();
      hint.textContent = data.message;
      hint.className = data.status === "clash" ? "invalid-feedback d-block" : "form-hint";
      input.classList.toggle("is-invalid", data.status === "clash");
    }, 250);
  };
  input.addEventListener("input", check);
  window.checkCodeHint = check;
})();
```
In `templates/inventory/item_form.html`, replace the whole inline `{% block scripts %}…{% endblock %}` with:
```html
{% block scripts %}{% load static %}<script src="{% static 'js/code-hint.js' %}"></script>{% endblock %}
```

- [ ] **Step 8: `static/js/entry-form.js`**

```javascript
/* Item lines for the Stock IN / OUT / Transfer / Adjust forms. Data comes from json_script blocks on the page. */
(function () {
  const $ = id => document.getElementById(id);
  const data = id => JSON.parse($(id).textContent);
  const form = $("entry-form"), mode = form.dataset.mode, body = $("lines");
  const items = new Map(data("items-data").map(i => [String(i.id), i]));
  const balances = data("balances-data"), parties = data("parties-data");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = s => String(s || "").toUpperCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").trim();
  // Same rule as apps/inventory/normalise.search_key: O->0, I->1, leading zeros dropped, symbols removed.
  const lookKey = s => norm(s).replace(/O/g, "0").replace(/I/g, "1")
    .replace(/(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)/g, "$1$2").replace(/[^A-Z0-9]/g, "");
  const locSelect = $("id_location");
  const have = id => balances[`${id}-${locSelect.value}`] || 0;
  const locName = () => locSelect.options[locSelect.selectedIndex].text;
  const option = i => ({ ...i, value: String(i.id), hay: norm([i.code, ...i.aliases, i.desc, i.cat, i.type, i.company].join(" ")) });
  const rows = [];

  function picker(select, row) {
    return new TomSelect(select, {
      options: [...items.values()].map(option), valueField: "value", labelField: "code", maxOptions: 60,
      closeAfterSelect: true, openOnFocus: false, placeholder: "Type code, old spelling or description…",
      score(search) { // text anywhere, or a look-alike code (O/0, I/1, hyphens, leading zeros)
        const t = norm(search), k = lookKey(search);
        return it => !t ? 1 : it.hay.includes(t) ? 2 : (k.length > 2 && it.keys.includes(k)) ? 1.5 : 0;
      },
      create: mode === "in" ? (input, done) => openNewItem(norm(input), done) : false,
      render: {
        option: d => `<div><span class="opt-code">${esc(d.code)}</span><span class="opt-meta">${esc(d.type)} · ${esc(d.desc)}${d.cat && d.cat !== d.code ? ` · for ${esc(d.cat)}` : ""} · ${esc(d.company)}</span></div>`,
        item: d => `<div>${esc(d.code)}</div>`,
        option_create: d => `<div class="create">＋ Create new item <b>${esc(norm(d.input))}</b>…</div>`,
        no_results: () => `<div class="no-results">No matching item${mode === "in" ? " (type the full code to create it)" : ""}.</div>`,
      },
      onChange: () => refresh(row),
    });
  }

  function qtyCell(label, min) {
    return `<td data-label="${label}" style="min-width:9rem"><div class="input-group"><input type="number" name="line_qty" class="form-control qty" min="${min}" step="1"
      inputmode="numeric" placeholder="0" aria-label="${label}"><span class="input-group-text u">—</span></div><div class="invalid-feedback d-block err"></div></td>`;
  }

  function addRow(init = {}, focus = false) {
    const tr = document.createElement("tr"), row = { tr };
    const hidden = mode === "in" ? "" : `<input type="hidden" name="line_batch" value=""><input type="hidden" name="line_pkd" value="">`;
    tr.innerHTML = `<td class="c-n text-secondary"></td><td class="c-item"><select name="line_item" aria-label="Item"><option value=""></option></select>${hidden}<small class="form-hint line-meta"></small></td>` + {
      in: qtyCell("Quantity", 1) + `<td data-label="Batch code"><input name="line_batch" class="form-control" maxlength="40" placeholder="e.g. B2405"></td>
          <td data-label="PKD (packed)"><input name="line_pkd" class="form-control" type="month"></td>`,
      out: `<td data-label="Available" class="avail"></td>` + qtyCell("Quantity", 1),
      trf: `<td data-label="Available" class="avail"></td>` + qtyCell("Quantity", 1),
      adj: `<td data-label="System qty" class="avail"></td>` + qtyCell("Counted qty", 0) + `<td data-label="Difference" class="avail diff"></td>`,
    }[mode] + `<td class="c-rm"><button type="button" class="btn btn-icon btn-ghost-danger remove" title="Remove line" aria-label="Remove line"><i class="ti ti-trash"></i></button></td>`;
    body.appendChild(tr);
    row.ts = picker(tr.querySelector("select"), row);
    row.qty = tr.querySelector(".qty");
    row.qty.addEventListener("input", () => refresh(row));
    tr.querySelector(".remove").onclick = () => removeRow(row);
    rows.push(row);
    if (init.item && items.has(String(init.item))) row.ts.setValue(String(init.item), true);
    row.qty.value = init.qty || "";
    if (mode === "in") { tr.querySelector("[name=line_batch]").value = init.batch || ""; tr.querySelector("[name=line_pkd]").value = init.pkd || ""; }
    number(); refresh(row);
    if (focus) setTimeout(() => row.ts.focus(), 0);
  }

  function removeRow(row) {
    if (rows.length === 1) { row.ts.clear(); row.tr.querySelectorAll("input:not([type=hidden])").forEach(i => i.value = ""); refresh(row); return; }
    row.ts.destroy(); row.tr.remove(); rows.splice(rows.indexOf(row), 1); number(); summary();
  }

  const number = () => rows.forEach((r, n) => r.tr.querySelector(".c-n").textContent = n + 1);

  function refresh(row) {
    const it = items.get(row.ts.getValue()), unit = it ? it.unit : "—";
    row.tr.querySelectorAll(".u").forEach(s => s.textContent = unit);
    row.tr.querySelector(".line-meta").textContent = it ? `${it.type} · ${it.desc}${it.cat && it.cat !== it.code ? ` · for ${it.cat}` : ""}` : "";
    const err = row.tr.querySelector(".err");
    err.textContent = ""; row.qty.classList.remove("is-invalid");
    const avail = row.tr.querySelector(".avail:not(.diff)");
    if (avail) {
      if (!it) { avail.textContent = ""; } else {
        const n = have(it.id);
        avail.innerHTML = `<b>${n}</b> ${esc(unit)} <span class="text-secondary d-block small">at ${esc(locName())}</span>`;
        if (mode === "adj") {
          const counted = row.qty.value === "" ? null : Number(row.qty.value), d = counted === null ? null : counted - n;
          row.tr.querySelector(".diff").innerHTML = d === null ? "" :
            `<span class="badge ${d < 0 ? "bg-red-lt" : d > 0 ? "bg-green-lt" : "bg-secondary-lt"}">${d > 0 ? "+" : ""}${d} ${esc(unit)}</span>`;
        } else if (Number(row.qty.value) > n) {
          err.textContent = `Only ${n} ${unit} available`; row.qty.classList.add("is-invalid");
        }
      }
    }
    summary();
  }

  function summary() {
    const totals = {}, chosen = rows.filter(r => r.ts.getValue());
    if (mode !== "adj") for (const r of chosen) { const it = items.get(r.ts.getValue()), v = Number(r.qty.value); if (v > 0) totals[it.unit] = (totals[it.unit] || 0) + v; }
    const parts = Object.entries(totals).map(([u, q]) => `${q} ${u}`);
    $("lines-summary").textContent = chosen.length ? `${chosen.length} item${chosen.length > 1 ? "s" : ""}${parts.length ? " · " + parts.join(" · ") : ""}` : "";
  }

  // Subtype radios: show the matching "who" field and fill name suggestions.
  function subtypeChanged() {
    const picked = form.querySelector("input[name=subtype]:checked");
    if (!picked) return;
    form.querySelectorAll("[data-show]").forEach(el => el.hidden = el.dataset.show !== picked.value);
    const label = $("party-label");
    if (label) label.textContent = { SITE: "Site / customer", TECH: "Technician", OTHER: "Name" }[picked.value];
    $("parties").innerHTML = (parties[picked.value] || []).map(p => `<option value="${esc(p)}">`).join("");
  }
  form.querySelectorAll("input[name=subtype]").forEach(r => r.addEventListener("change", subtypeChanged));
  subtypeChanged();

  locSelect.addEventListener("change", () => rows.forEach(refresh));
  $("add-line").onclick = () => addRow({}, true);
  const initial = data("initial-lines");
  (initial.length ? initial : [{}]).forEach(l => addRow(l));

  // Client-side check before posting; the server checks everything again.
  form.addEventListener("submit", e => {
    const bad = rows.find(r => r.qty.classList.contains("is-invalid"));
    if (bad) { e.preventDefault(); $("form-error").innerHTML = `<div class="alert alert-danger" role="alert">Fix the highlighted quantities first.</div>`; bad.qty.focus(); }
  });

  // Quick "create item" (Stock IN only).
  let pending = null;
  function openNewItem(code, done) {
    const modalEl = $("new-item-modal"), codeInput = modalEl.querySelector("#id_code");
    pending = done; codeInput.value = code; $("ni-err").textContent = "";
    if (window.checkCodeHint) window.checkCodeHint();
    modalEl.addEventListener("hidden.bs.modal", () => { if (pending) { pending(false); pending = null; } }, { once: true });
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }
  const niForm = $("new-item-form");
  if (niForm) niForm.addEventListener("submit", async e => {
    e.preventDefault();
    const res = await (await fetch(niForm.dataset.url, { method: "POST", body: new FormData(niForm) })).json();
    if (!res.ok) { $("ni-err").textContent = res.error; return; }
    items.set(String(res.item.id), res.item);
    const done = pending; pending = null;
    bootstrap.Modal.getInstance($("new-item-modal")).hide();
    done(option(res.item));
    rows.forEach(r => r.ts.addOption(option(res.item)));
  });
})();
```

- [ ] **Step 9: `templates/inventory/entry_detail.html`**

```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}{{ entry.number }}{% endblock %}
{% block pretitle %}{{ entry.get_kind_display }}{% endblock %}
{% block page_title %}<span class="code">{{ entry.number }}</span> <span class="badge badge-k k-{{ entry.kind }} ms-2">{{ entry.get_kind_display }}</span>{% endblock %}
{% block actions %}
  {% if can_undo %}<button type="button" class="btn btn-outline-danger" data-bs-toggle="modal" data-bs-target="#undo-modal"><i class="ti ti-arrow-back-up"></i> Undo this entry</button>{% endif %}
  <a href="{% url 'movements' %}" class="btn btn-outline-secondary"><i class="ti ti-list"></i> All movements</a>
{% endblock %}
{% block content %}
{% if undone_by %}<div class="alert alert-warning"><i class="ti ti-arrow-back-up"></i> Undone by <a class="code" href="{% url 'entry_detail' undone_by.number %}">{{ undone_by.number }}</a> on {{ undone_by.entry_date|date }}: {{ undone_by.note }}</div>{% endif %}
{% if entry.reverses %}<div class="alert alert-info"><i class="ti ti-info-circle"></i> This entry cancels <a class="code" href="{% url 'entry_detail' entry.reverses.number %}">{{ entry.reverses.number }}</a>.</div>{% endif %}
<div class="row row-cards">
  <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
    <div class="datagrid-item"><div class="datagrid-title">Date</div><div class="datagrid-content">{{ entry.entry_date|date }}</div></div>
    {% if entry.details %}<div class="datagrid-item"><div class="datagrid-title">Type</div><div class="datagrid-content">{{ entry.details }}</div></div>{% endif %}
    {% if entry.party %}<div class="datagrid-item"><div class="datagrid-title">{% if entry.kind == "IN" %}Received from{% elif entry.kind == "TRF" %}To location{% else %}Issued to{% endif %}</div><div class="datagrid-content">{{ entry.party }}</div></div>{% endif %}
    {% if entry.ref %}<div class="datagrid-item"><div class="datagrid-title">DC / ref no.</div><div class="datagrid-content">{{ entry.ref }}</div></div>{% endif %}
    {% if entry.note %}<div class="datagrid-item"><div class="datagrid-title">{% if entry.kind == "REV" %}Reason{% else %}Note{% endif %}</div><div class="datagrid-content">{{ entry.note }}</div></div>{% endif %}
    <div class="datagrid-item"><div class="datagrid-title">Entered by</div><div class="datagrid-content">{{ entry.created_by.first_name|default:entry.created_by.username }} · {{ entry.created_at|date:"d-m-Y H:i" }}</div></div>
  </div></div></div></div>
  <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Items</h3></div>
    <div class="table-responsive"><table class="table table-vcenter card-table">
      <thead><tr><th>Item code</th><th>Description</th><th>Location</th><th class="num">In</th><th class="num">Out</th><th>Unit</th>{% if entry.kind == "IN" %}<th>Batch</th><th>PKD</th>{% endif %}</tr></thead>
      <tbody>{% for line in entry.lines.all %}<tr><td><a class="code" href="{% url 'item_detail' line.item.pk %}">{{ line.item.code }}</a></td><td>{{ line.item.description }}</td><td>{{ line.location.name }}</td>
        <td class="num">{% if line.qty > 0 %}<span class="qty-in">+{{ line.qty }}</span>{% endif %}</td>
        <td class="num">{% if line.qty < 0 %}<span class="qty-out">−{{ line.qty|stringformat:"d"|slice:"1:" }}</span>{% endif %}</td><td>{{ line.item.unit }}</td>
        {% if entry.kind == "IN" %}<td>{{ line.batch_code }}</td><td>{{ line.pkd|date:"m-Y" }}</td>{% endif %}</tr>{% endfor %}</tbody>
    </table></div></div></div>
</div>
{% if can_undo %}
<div class="modal modal-blur fade" id="undo-modal" tabindex="-1" aria-hidden="true"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
  <form method="post" action="{% url 'entry_undo' entry.number %}">{% csrf_token %}
    <div class="modal-status bg-danger"></div>
    <div class="modal-body"><h3><i class="ti ti-arrow-back-up text-danger"></i> Undo {{ entry.number }}?</h3>
      <p class="text-secondary">This posts a new "Undo" entry with the opposite quantities. Both stay on record.</p>
      <label class="form-label required" for="undo-reason">Reason</label>
      <input id="undo-reason" name="reason" class="form-control" required maxlength="200" placeholder="e.g. typed the wrong quantity"></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button>
      <button type="submit" class="btn btn-danger ms-auto">Undo entry</button></div>
  </form></div></div></div>
{% endif %}
{% endblock %}
```
`base.html` (Task 6) already renders `messages` as Tabler alerts/toasts, so the success and error messages show after redirects.

- [ ] **Step 10: Link entry numbers everywhere**

- `templates/inventory/_entries_table.html`: `<td class="code">{{ e.number }}</td>` → `<td><a class="code" href="{% url 'entry_detail' e.number %}">{{ e.number }}</a></td>`
- `templates/inventory/movements.html`: `<td class="code">{{ r.entry.number }}</td>` → `<td><a class="code" href="{% url 'entry_detail' r.entry.number %}">{{ r.entry.number }}</a></td>`
- `templates/inventory/item_detail.html`: the same change for `r.entry.number` in the history table.

- [ ] **Step 11: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q    # expected: all pass
uv run ruff format . && uv run ruff check .
git add apps templates static tests
git commit -m "feat: stock IN/OUT/transfer/adjust forms with item picker, entry detail and undo"
```

---

### Task 10: Excel exports (current stock, movements, item list, low stock, item history)

**Files:**
- Create: `apps/core/excel.py`, `apps/inventory/exports.py`
- Modify: `apps/inventory/urls.py`, `templates/inventory/current_stock.html`, `templates/inventory/movements.html`, `templates/inventory/items.html`, `templates/inventory/low_stock.html`
- Test: `tests/core/test_excel.py`, `tests/inventory/test_exports.py`

The layout is the one approved with the sample files in `mockups/stock/exports/`, ported from `mockups/stock/make_sample_exports.py`: company title, report name, filters, a "generated on … by …" line, an Excel table with "Table Style Medium 2", frozen header, autofit, A4 landscape fitting the page width, and a repeated header row. Each export reuses the list screen's GET filters (the `filters.py` parsers), so "Export" always downloads exactly what is on screen (all pages).

- [ ] **Step 1: Write failing tests**

`tests/core/test_excel.py`:
```python
import io
from datetime import date, datetime

import openpyxl

from apps.core.excel import Column, workbook_response


def test_report_layout():
    response = workbook_response("Test_Report", "Test Report", "All items", "office",
                                 [Column("Code", "code"), Column("Qty", "int"), Column("Date", "date")],
                                 [["A1", 3, date(2026, 10, 1)], ["B2", 0, date(2026, 10, 2)]], low_rows={1}, low_col=1,
                                 now=datetime(2026, 10, 11, 14, 5))
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'filename="Test_Report_2026-10-11.xlsx"' in response["Content-Disposition"]
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert ws["A1"].value == "SVKML Electrical Works" and ws["A2"].value == "Test Report"
    assert ws["A3"].value == "Filters: All items"
    assert ws["A4"].value == "Generated on 11-10-2026 14:05 by office · 2 rows"
    assert [c.value for c in ws[6]] == ["Code", "Qty", "Date"]
    assert ws.freeze_panes == "B7"
    assert ws["C7"].number_format == "dd-mm-yyyy" and ws["B8"].fill.fgColor.rgb.endswith("FDE2E2")
    assert ws.page_setup.orientation == "landscape" and ws.print_title_rows.replace("$", "") == "6:6"


def test_empty_report_still_valid():
    response = workbook_response("Empty", "Empty", "-", "office", [Column("Code", "code")], [], now=datetime(2026, 10, 11))
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert ws["A7"].value == "(no rows)"
```

`tests/inventory/test_exports.py`:
```python
import io

import openpyxl
import pytest
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db


def sheet(response):
    assert response.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(response.content)).active


@pytest.fixture
def stock(office_user):
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module", description="LED module")
    b = make_item("LG78-150-700", reorder=2)
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), user=office_user, subtype="SUPPLIER", party="Wipro Lighting",
               lines=[Line(a, loc(), 8), Line(b, loc("TV Shop"), 20)])
    return a, b


def test_current_stock_export_respects_filters(office_client, stock):
    ws = sheet(office_client.get(f"/stock/export/?location={loc('TV Shop').pk}"))
    codes = [ws.cell(r, 1).value for r in range(7, ws.max_row + 1)]
    assert codes == ["LG78-150-700"] and "TV Shop" in ws["A3"].value


def test_movements_export(office_client, stock):
    ws = sheet(office_client.get("/movements/export/"))
    headers = [c.value for c in ws[6]]
    assert headers[:3] == ["Date", "Entry no.", "Type"] and ws.max_row == 8  # 2 lines


def test_items_and_low_stock_exports(office_client, stock):
    assert sheet(office_client.get("/items/export/")).max_row == 8
    low = sheet(office_client.get("/low-stock/export/"))
    assert low.cell(7, 1).value == "EIO6006" and low.max_row == 7


def test_item_history_export(office_client, stock):
    a, _ = stock
    ws = sheet(office_client.get(f"/items/{a.pk}/export/"))
    assert "EIO6006" in ws["A2"].value and ws.cell(7, 2).value == "IN-0001"


def test_export_buttons_keep_filters(office_client, stock):
    html = office_client.get("/stock/?q=eio").content.decode()
    assert 'href="/stock/export/?q=eio"' in html
```

Run: expected FAIL.

- [ ] **Step 2: `apps/core/excel.py`**

```python
"""One neat layout for every Excel export (approved via mockups/stock/exports/)."""

import io
from dataclasses import dataclass
from datetime import date, datetime

import xlsxwriter
from django.http import HttpResponse
from django.utils import timezone

COMPANY = "SVKML Electrical Works"
HEAD_ROW = 5  # zero-based; rows 0-3 hold the title block
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Column:
    header: str
    kind: str = "text"  # text | code | int | date
    width: int | None = None  # characters; None = autofit


def _formats(wb):
    return {
        "company": wb.add_format({"bold": True, "font_size": 15, "font_color": "#0F2744"}),
        "title": wb.add_format({"bold": True, "font_size": 12}),
        "meta": wb.add_format({"italic": True, "font_color": "#555555", "font_size": 9}),
        "text": wb.add_format({"valign": "top"}),
        "code": wb.add_format({"font_name": "Consolas", "num_format": "@"}),
        "int": wb.add_format({"num_format": '#,##0;-#,##0;"–"'}),
        "date": wb.add_format({"num_format": "dd-mm-yyyy", "align": "left"}),
        "low": wb.add_format({"bg_color": "#FDE2E2", "font_color": "#9B1C1C", "bold": True}),
    }


def _cell(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time())
    return value


def _title(ws, row, last, text, fmt):
    """Title-block line across the table width (XlsxWriter refuses a one-cell merge)."""
    if last:
        ws.merge_range(row, 0, row, last, text, fmt)
    else:
        ws.write(row, 0, text, fmt)


def workbook_response(filename, title, filters, username, columns, rows, low_rows=(), low_col=None, now=None):
    """Build the report in memory and return it as a download. low_rows: row indexes to highlight in low_col."""
    now = now or timezone.localtime()
    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
    wb.set_properties({"title": title, "company": COMPANY, "author": "SVKML Stock"})
    ws = wb.add_worksheet(title[:31])
    f = _formats(wb)
    last = len(columns) - 1
    data = [[_cell(v) for v in row] for row in rows]
    ws.add_table(HEAD_ROW, 0, HEAD_ROW + max(len(data), 1), last, {
        "data": data or [["(no rows)"] + [None] * last],
        "style": "Table Style Medium 2",
        "columns": [{"header": c.header, "format": f[c.kind]} for c in columns],
    })
    for n in low_rows:
        ws.write(HEAD_ROW + 1 + n, low_col, data[n][low_col], f["low"])
    ws.freeze_panes(HEAD_ROW + 1, 1)
    ws.autofit(max_width=280)  # before the title rows, so they don't widen column A
    for n, col in enumerate(columns):
        if col.width:
            ws.set_column(n, n, col.width)
    _title(ws, 0, last, COMPANY, f["company"])
    _title(ws, 1, last, title, f["title"])
    _title(ws, 2, last, f"Filters: {filters}", f["meta"])
    _title(ws, 3, last, f"Generated on {now:%d-%m-%Y %H:%M} by {username} · {len(data)} rows", f["meta"])
    ws.set_row(HEAD_ROW, 30)
    ws.hide_gridlines(2)
    ws.set_landscape()
    ws.set_paper(9)  # A4
    ws.fit_to_pages(1, 0)
    ws.repeat_rows(HEAD_ROW)
    ws.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.set_header(f"&L&8{COMPANY}&R&8{title}")
    ws.set_footer("&L&8Generated &D &T&R&8Page &P of &N")
    wb.close()
    response = HttpResponse(buffer.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="{filename}_{now:%Y-%m-%d}.xlsx"'
    return response
```

- [ ] **Step 3: `apps/inventory/exports.py`**

```python
"""Excel downloads. Each one reuses its list screen's filters, so it exports exactly what is shown (all pages)."""

from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.excel import Column, workbook_response

from . import selectors
from .filters import item_filters, movement_filters, stock_filters
from .models import EntryKind, Item, Location


def _describe(*parts):
    return " · ".join(p for p in parts if p) or "None"


def _who(request):
    return request.user.first_name or request.user.username


def _pkd(line):
    return f"{line.pkd:%m-%Y}" if line.pkd else ""


@role_required(OFFICE)
def current_stock_xlsx(request):
    f = stock_filters(request.GET)
    rows, locations = selectors.current_stock_rows(f)
    rows.sort(key=lambda r: r["item"].code)
    cols = [Column("Item code", "code"), Column("Spare type"), Column("Description", width=30),
            Column("Used in fitting (cat ref)", "code"), Column("Fitting type"), Column("Company")]
    cols += [Column(p.name, "int") for p in locations]
    cols += [Column("Total", "int"), Column("Unit"), Column("Reorder level", "int"), Column("Status")]
    data = [[r["item"].code, r["item"].spare_type.name, r["item"].description,
             r["item"].cat_ref if r["item"].cat_ref != r["item"].code else "",
             r["item"].fitting_type.name if r["item"].fitting_type else "", r["item"].company.name]
            + [r["per_loc"].get(p.pk, 0) for p in locations]
            + [r["total"], r["item"].unit, r["item"].reorder_level, "LOW" if r["low"] else "OK"] for r in rows]
    filters = _describe(f.location.name if f.location else "All locations",
                        f.spare_type.name if f.spare_type else "all types", f.company.name if f.company else "all companies",
                        f'search "{f.q}"' if f.q else "", "only low stock" if f.low else "")
    low = {n for n, r in enumerate(rows) if r["low"]}
    return workbook_response("Current_Stock", "Current Stock", filters, _who(request), cols, data, low, len(cols) - 1)


@role_required(OFFICE)
def movements_xlsx(request):
    f = movement_filters(request.GET, timezone.localdate())
    rows = selectors.movement_rows(f)
    cols = [Column("Date", "date"), Column("Entry no.", "code"), Column("Type"), Column("Details"), Column("Item code", "code"),
            Column("Description", width=28), Column("Location"), Column("Qty in", "int"), Column("Qty out", "int"),
            Column("Unit"), Column("Supplier / issued to", width=26), Column("DC / ref no."), Column("Batch code"),
            Column("PKD"), Column("Entered by"), Column("Note", width=28)]
    data = []
    for r in rows:
        e, line = r["entry"], r["line"]
        note = f"Undone by {e.reversed_by.number}" if r["undone"] else e.note
        data.append([e.entry_date, e.number, e.get_kind_display(), e.details, line.item.code, line.item.description,
                     line.location.name, line.qty if line.qty > 0 else None, -line.qty if line.qty < 0 else None,
                     line.item.unit, e.party, e.ref, line.batch_code, _pkd(line),
                     e.created_by.first_name or e.created_by.username, note])
    filters = _describe(f"{f.date_from:%d-%m-%Y} to {f.date_to:%d-%m-%Y}",
                        EntryKind(f.kind).label if f.kind else "all types", f.location.name if f.location else "all locations",
                        f.item.code if f.item else "", f'search "{f.q}"' if f.q else "")
    return workbook_response("Stock_Movements", "Stock Movements", filters, _who(request), cols, data)


@role_required(OFFICE)
def items_xlsx(request):
    f = item_filters(request.GET)
    rows = sorted(selectors.item_rows(f), key=lambda r: r["item"].code)
    cols = [Column("Item code", "code"), Column("Other spellings", "code"), Column("Spare type"), Column("Description", width=30),
            Column("Product cat ref", "code"), Column("Fitting type"), Column("Wattage (W)", "int"), Column("Current (mA)", "int"),
            Column("Company"), Column("Unit"), Column("Reorder level", "int"), Column("In stock", "int"), Column("Status")]
    data = [[i.code, ", ".join(a.alias for a in i.aliases.all()), i.spare_type.name, i.description, i.cat_ref,
             i.fitting_type.name if i.fitting_type else "", i.wattage_w, i.current_ma, i.company.name, i.unit,
             i.reorder_level, r["total"], "Active" if i.is_active else "Inactive"] for r in rows for i in [r["item"]]]
    status = {"1": "active", "0": "inactive", "": "active and inactive"}[f.status]
    filters = _describe(f'search "{f.q}"' if f.q else "", f.spare_type.name if f.spare_type else "all types",
                        f.company.name if f.company else "all companies", f.fitting_type.name if f.fitting_type else "", status)
    return workbook_response("Item_List", "Item List", filters, _who(request), cols, data)


@role_required(OFFICE)
def low_stock_xlsx(request):
    rows = sorted(selectors.low_stock_rows(), key=lambda r: -r["short_by"])
    locations = list(Location.objects.filter(is_active=True))
    cols = [Column("Item code", "code"), Column("Spare type"), Column("Description", width=30), Column("Company")]
    cols += [Column(p.name, "int") for p in locations]
    cols += [Column("Total", "int"), Column("Reorder level", "int"), Column("Short by", "int"), Column("Unit")]
    data = [[r["item"].code, r["item"].spare_type.name, r["item"].description, r["item"].company.name]
            + [r["per_loc"].get(p.pk, 0) for p in locations]
            + [r["total"], r["item"].reorder_level, r["short_by"], r["item"].unit] for r in rows]
    total_col = 4 + len(locations)
    return workbook_response("Low_Stock", "Low Stock", "Items at or below their reorder level (total across all locations)",
                             _who(request), cols, data, set(range(len(data))), total_col)


@role_required(OFFICE)
def item_history_xlsx(request, pk):
    item = get_object_or_404(Item, pk=pk)
    today = timezone.localdate()
    f = movement_filters(request.GET, today)
    location = f.location
    rows = selectors.item_history(item, f.date_from, f.date_to, location)
    cols = [Column("Date", "date"), Column("Entry no.", "code"), Column("Type"), Column("Location"), Column("Qty in", "int"),
            Column("Qty out", "int"), Column("Balance at location", "int"), Column("Supplier / issued to", width=26),
            Column("DC / ref no."), Column("Batch code"), Column("PKD"), Column("Entered by")]
    data = [[r["entry"].entry_date, r["entry"].number, r["entry"].get_kind_display(), r["line"].location.name,
             r["line"].qty if r["line"].qty > 0 else None, -r["line"].qty if r["line"].qty < 0 else None, r["after"],
             r["entry"].party, r["entry"].ref, r["line"].batch_code, _pkd(r["line"]),
             r["entry"].created_by.first_name or r["entry"].created_by.username] for r in rows]
    filters = _describe(f"{f.date_from:%d-%m-%Y} to {f.date_to:%d-%m-%Y}", location.name if location else "all locations")
    return workbook_response(f"Item_{item.pk}_History", f"Item history: {item.code} ({item.unit})", filters,
                             _who(request), cols, data)
```

Add to `apps/inventory/urls.py` (`from . import exports, views`):
```python
    path("stock/export/", exports.current_stock_xlsx, name="current_stock_xlsx"),
    path("movements/export/", exports.movements_xlsx, name="movements_xlsx"),
    path("items/export/", exports.items_xlsx, name="items_xlsx"),
    path("low-stock/export/", exports.low_stock_xlsx, name="low_stock_xlsx"),
    path("items/<int:pk>/export/", exports.item_history_xlsx, name="item_history_xlsx"),
```
Put `items/export/` **before** `items/<int:pk>/`. The int converter would not match "export" anyway, but keeping static routes first is clearer.

- [ ] **Step 4: Export buttons**

Add a template tag to `apps/core/templatetags/core_tags.py`, which builds the export URL with the current query string:
```python
@register.simple_tag(takes_context=True)
def export_url(context, name, *args):
    """reverse(name) + the current GET params (minus paging/sorting), so the download matches the screen."""
    params = context["request"].GET.copy()
    for key in ("page", "size", "sort", "dir"):
        params.pop(key, None)
    query = params.urlencode()
    return reverse(name, args=args) + (f"?{query}" if query else "")
```
(`from django.urls import reverse`.)

Fill the `export_button` blocks:
- `current_stock.html`: `{% block export_button %}<a href="{% export_url 'current_stock_xlsx' %}" class="btn btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Export to Excel</a>{% endblock %}`
- `items.html`: the same with `'items_xlsx'`
- `movements.html` and `low_stock.html`: add `{% block actions %}<a href="{% export_url 'movements_xlsx' %}" …>` (and `'low_stock_xlsx'`)
- `item_detail.html`: fill `{% block export_history %}<div class="card-actions"><a href="{% export_url 'item_history_xlsx' item.pk %}" class="btn btn-sm btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Export</a></div>{% endblock %}`

The item card's history filter uses the same `date_from`, `date_to` and `location` params as `movement_filters`. That is why the export reuses that parser.

- [ ] **Step 5: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q
uv run ruff format . && uv run ruff check .
git add apps templates tests
git commit -m "feat: neatly formatted Excel exports for stock, movements, items, low stock and item history"
```

---

### Task 11: Masters page (admin), global search, permission sweep

**Files:**
- Create: `apps/inventory/masters.py`, `templates/inventory/masters.html`, `static/js/app.js`
- Modify: `apps/inventory/urls.py`, `apps/inventory/views.py`, `templates/base.html` (load `app.js`)
- Test: `tests/inventory/test_masters.py`, `tests/inventory/test_search.py`, `tests/test_permissions.py`

- [ ] **Step 1: Write failing tests**

`tests/inventory/test_masters.py`:
```python
import pytest

from apps.inventory.models import Company, Location

pytestmark = pytest.mark.django_db


def test_office_cannot_open_masters(office_client):
    assert office_client.get("/masters/").status_code == 403


def test_admin_adds_location_and_company(admin_client):
    assert admin_client.get("/masters/").status_code == 200
    r = admin_client.post("/masters/", {"kind": "location", "name": "  Gajuwaka Store "})
    assert r.status_code == 302 and Location.objects.filter(name="Gajuwaka Store").exists()
    admin_client.post("/masters/", {"kind": "company", "name": "Bajaj"})
    assert Company.objects.filter(name="Bajaj").exists()


def test_duplicate_name_refused(admin_client):
    html = admin_client.post("/masters/", {"kind": "location", "name": "vizag office"}, follow=True).content.decode()
    assert "already exists" in html and Location.objects.filter(name__iexact="vizag office").count() == 1


def test_toggle_active(admin_client):
    place = Location.objects.get(name="TV Shop")
    admin_client.post("/masters/toggle/", {"kind": "location", "pk": place.pk})
    place.refresh_from_db()
    assert place.is_active is False
```

`tests/inventory/test_search.py`:
```python
import pytest
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db


def test_global_search_items_and_entries(office_client, office_user):
    a = make_item("EIO8437", spare_type="PCB / LED module")
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 1)], user=office_user)
    data = office_client.get("/search/?q=ei08437").json()
    assert data["items"][0]["code"] == "EIO8437" and data["items"][0]["url"] == f"/items/{a.pk}/"
    data = office_client.get("/search/?q=in-0001").json()
    assert data["entries"][0] == {"number": "IN-0001", "url": "/entries/IN-0001/", "label": "Stock IN"}


def test_short_query_returns_nothing(office_client):
    assert office_client.get("/search/?q=e").json() == {"items": [], "entries": []}
```

`tests/test_permissions.py` (a sweep over every named URL, so a new view can't silently skip login):
```python
import pytest
from django.urls import get_resolver

pytestmark = pytest.mark.django_db
PUBLIC = {"login", "logout", "healthz"}
ADMIN_ONLY = {"masters", "masters_toggle"}


def named_routes():
    for name, patterns in get_resolver().reverse_dict.items():
        if isinstance(name, str) and not name.startswith("admin") and name not in PUBLIC:
            result, params = patterns[0][0]  # (possibilities, pattern, defaults, converters)[0] -> first possibility
            yield name, result % {k: 1 for k in params}


@pytest.mark.parametrize("name,path", sorted(named_routes()))
def test_anonymous_is_sent_to_login(client, name, path):
    r = client.get("/" + path)
    assert r.status_code == 302 and r.url.startswith("/login/"), name


@pytest.mark.parametrize("name,path", sorted(n for n in named_routes() if n[0] in ADMIN_ONLY))
def test_office_blocked_from_admin_pages(office_client, name, path):
    assert office_client.get("/" + path).status_code == 403
```

Run: expected FAIL.

- [ ] **Step 2: Masters service + view** — `apps/inventory/masters.py`

```python
"""Admin-only page to add and switch off locations, companies, fitting types and spare types."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN

from .models import Company, FittingType, Location, SpareType

KINDS = {
    "location": (Location, "Locations", "map-pin"),
    "company": (Company, "Suppliers / companies", "building-store"),
    "fitting_type": (FittingType, "Fitting types", "bulb"),
    "spare_type": (SpareType, "Spare types", "components"),
}


@role_required(ADMIN)
def masters(request):
    if request.method == "POST":
        model, label, _ = KINDS.get(request.POST.get("kind"), (None, "", ""))
        name = " ".join(request.POST.get("name", "").split())
        if model is None or not name:
            messages.error(request, "Type a name.")
        elif model.objects.filter(name__iexact=name).exists():
            messages.error(request, f"{name} already exists in {label.lower()}.")
        else:
            model.objects.create(name=name)
            messages.success(request, f"Added {name}.")
        return redirect("masters")
    groups = [(key, label, icon, model.objects.order_by("-is_active", "name")) for key, (model, label, icon) in KINDS.items()]
    return render(request, "inventory/masters.html", {"groups": groups})


@role_required(ADMIN)
@require_POST
def masters_toggle(request):
    model = KINDS.get(request.POST.get("kind"), (None,))[0]
    if model is not None:
        row = model.objects.filter(pk=request.POST.get("pk")).first()
        if row:
            row.is_active = not row.is_active
            row.save(update_fields=["is_active"])
            messages.success(request, f"{row.name} is now {'active' if row.is_active else 'hidden from forms'}.")
    return redirect("masters")
```

`masters_toggle` is POST-only, so the anonymous GET in the sweep is redirected to login by `role_required` before `require_POST` runs. Keep the decorator order exactly as written. For the office-user sweep, a GET to `masters_toggle` returns 403 from `role_required` first.

`templates/inventory/masters.html`:
```html
{% extends "base.html" %}
{% block title %}Masters{% endblock %}
{% block pretitle %}Setup · Admin only{% endblock %}
{% block page_title %}Masters{% endblock %}
{% block actions %}<a href="{% url 'admin:index' %}" class="btn btn-outline-secondary"><i class="ti ti-users"></i> Users &amp; full admin</a>{% endblock %}
{% block content %}
<div class="row row-cards">{% for key, label, icon, rows in groups %}
  <div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-header"><h3 class="card-title"><i class="ti ti-{{ icon }}"></i> {{ label }}</h3></div>
    <div class="list-group list-group-flush">{% for row in rows %}
      <div class="list-group-item d-flex align-items-center"><span class="{% if not row.is_active %}text-secondary text-decoration-line-through{% endif %}">{{ row.name }}</span>
        <form method="post" action="{% url 'masters_toggle' %}" class="ms-auto">{% csrf_token %}<input type="hidden" name="kind" value="{{ key }}"><input type="hidden" name="pk" value="{{ row.pk }}">
          <button class="btn btn-sm btn-ghost-secondary" title="{% if row.is_active %}Hide from forms{% else %}Show in forms{% endif %}">{% if row.is_active %}Hide{% else %}Show{% endif %}</button></form></div>
    {% endfor %}</div>
    <div class="card-footer"><form method="post" class="d-flex gap-2">{% csrf_token %}<input type="hidden" name="kind" value="{{ key }}">
      <input name="name" class="form-control" maxlength="80" placeholder="Add new…" aria-label="New {{ label|lower }}" required>
      <button class="btn btn-primary"><i class="ti ti-plus"></i></button></form></div></div></div>
{% endfor %}</div>
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Hidden entries stay on old records but no longer appear in dropdowns. Users and passwords are managed in the full admin.</p>
{% endblock %}
```
This assumes every master model has a `name` with max_length ≥ 80 (Task 3 `Master`). If Task 3 used a shorter `max_length`, use that value for `maxlength`.

- [ ] **Step 3: Global search** — append to `apps/inventory/views.py`

```python
@role_required(OFFICE)
def global_search(request):
    """Top-bar search: items (code, other spelling, description, fitting) and entry numbers."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"items": [], "entries": []})
    found = [{**selectors.picker_option(i), "url": reverse("item_detail", args=[i.pk])} for i in search_items(q, limit=8)]
    entries = StockEntry.objects.filter(number__icontains=q.upper()).order_by("-id")[:5]
    return JsonResponse({"items": found, "entries": [
        {"number": e.number, "url": reverse("entry_detail", args=[e.number]), "label": e.get_kind_display()} for e in entries]})
```
Imports: add `search_items` to the `.services` import, and `from django.urls import reverse`.

URLs (`from . import exports, masters, views`):
```python
    path("search/", views.global_search, name="global_search"),
    path("masters/", masters.masters, name="masters"),
    path("masters/toggle/", masters.masters_toggle, name="masters_toggle"),
```

`static/js/app.js` (top-bar search dropdown; base.html already has `#gsearch` with `data-url`):
```javascript
/* Top-bar search: shows matching items and entries in a dropdown under the box. */
(function () {
  const box = document.getElementById("gsearch");
  if (!box || !box.dataset.url) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const menu = document.createElement("div");
  menu.className = "dropdown-menu dropdown-menu-card gsearch-menu";
  box.parentElement.style.position = "relative";
  box.parentElement.appendChild(menu);
  let timer, active = -1;
  const links = () => [...menu.querySelectorAll("a")];
  const close = () => { menu.classList.remove("show"); active = -1; };
  box.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = box.value.trim();
      if (q.length < 2) return close();
      const d = await (await fetch(`${box.dataset.url}?q=${encodeURIComponent(q)}`)).json();
      const items = d.items.map(i => `<a class="dropdown-item" href="${i.url}"><div><span class="code">${esc(i.code)}</span>
        <div class="text-secondary small">${esc(i.type)} · ${esc(i.desc)}${i.aliases.length ? " · also " + esc(i.aliases.join(", ")) : ""}</div></div></a>`);
      const entries = d.entries.map(e => `<a class="dropdown-item" href="${e.url}"><span class="code">${esc(e.number)}</span><span class="ms-2 text-secondary">${esc(e.label)}</span></a>`);
      menu.innerHTML = (items.length ? `<h6 class="dropdown-header">Items</h6>${items.join("")}` : "")
        + (entries.length ? `<h6 class="dropdown-header">Entries</h6>${entries.join("")}` : "")
        || `<span class="dropdown-item-text text-secondary">Nothing found for “${esc(q)}”.</span>`;
      menu.classList.add("show"); active = -1;
    }, 200);
  });
  box.addEventListener("keydown", e => {
    const all = links();
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); if (!all.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length;
      all.forEach((a, n) => a.classList.toggle("active", n === active));
    } else if (e.key === "Enter") { e.preventDefault(); (all[active] || all[0])?.click(); }
    else if (e.key === "Escape") { close(); }
  });
  document.addEventListener("click", e => { if (!box.parentElement.contains(e.target)) close(); });
})();
```
Add to `static/css/app.css`: `.gsearch-menu { width: 100%; min-width: 22rem; max-height: 70vh; overflow-y: auto; top: 100%; }`.
In `templates/base.html`, load it after the Tabler JS and before `{% block scripts %}`: `<script src="{% static 'js/app.js' %}"></script>`.

- [ ] **Step 4: Run tests, lint, commit**

```bash
DATABASE_URL="<url>" uv run pytest -q
uv run ruff format . && uv run ruff check .
git add apps templates static tests
git commit -m "feat: admin masters page, global search, and a permission sweep over every URL"
```

---

### Task 12: Demo data, browser walkthrough, docs

**Files:**
- Create: `apps/inventory/demo/demo-data.json` (copy of `mockups/stock/demo-data.json`), `apps/inventory/management/commands/seed_stock_demo.py`, `e2e/walkthrough.py`
- Modify: `Makefile` (`demo` target), `README.md`, `CLAUDE.md`, `tasks/todo.md`
- Test: `tests/inventory/test_seed_demo.py`

- [ ] **Step 1: Write the failing test** — `tests/inventory/test_seed_demo.py`

```python
import io

import pytest
from django.core.management import call_command

from apps.inventory.models import Item, StockEntry
from apps.inventory.services import balance_drift

pytestmark = pytest.mark.django_db


def test_seed_demo_loads_items_and_history(admin_user, office_user):
    out = io.StringIO()
    call_command("seed_stock_demo", stdout=out)
    assert Item.objects.count() == 28 and StockEntry.objects.count() == 35
    assert StockEntry.objects.filter(kind="REV").exists() and balance_drift() == []
    assert "28 items, 35 entries" in out.getvalue()


def test_seed_demo_refuses_second_run(admin_user, office_user):
    call_command("seed_stock_demo", stdout=io.StringIO())
    with pytest.raises(Exception, match="already has stock entries"):
        call_command("seed_stock_demo", stdout=io.StringIO())
```
`seed_stock_demo` maps the demo's "by" values to users: `Admin` → the first ADMIN-group or superuser, `Office` → the first OFFICE-group user. The `admin_user` and `office_user` fixtures provide both.

- [ ] **Step 2: Implement the command**

```bash
mkdir -p apps/inventory/demo && cp mockups/stock/demo-data.json apps/inventory/demo/demo-data.json
```

`apps/inventory/management/commands/seed_stock_demo.py`:
```python
"""Load the approved demo items and ~5 weeks of stock history (dates shifted so the last entry is today)."""

import json
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import ADMIN, OFFICE
from apps.inventory.models import AdjustReason, Company, EntryKind, FittingType, Location, SpareType, StockEntry
from apps.inventory.services import Line, post_entry, save_item, undo_entry

DEMO = Path(__file__).resolve().parents[2] / "demo" / "demo-data.json"
REASONS = {label: value for value, label in AdjustReason.choices}


def _user(role):
    users = get_user_model().objects.order_by("id")
    found = users.filter(groups__name=role).first() or (users.filter(is_superuser=True).first() if role == ADMIN else None)
    if found is None:
        raise CommandError(f"No {role} user. Run `manage.py seed_users` first.")
    return found


class Command(BaseCommand):
    help = "Load demo items and stock history (only into an empty ledger)."

    @transaction.atomic
    def handle(self, *args, **options):
        if StockEntry.objects.exists():
            raise CommandError("The database already has stock entries. Demo data is only for an empty system.")
        db = json.loads(DEMO.read_text(encoding="utf-8"))
        users = {"Admin": _user(ADMIN), "Office": _user(OFFICE)}
        shift = timezone.localdate() - date.fromisoformat(db["today"])
        for model, names in [(Location, db["locations"]), (SpareType, db["spareTypes"]),
                             (FittingType, db["fittingTypes"]), (Company, db["companies"])]:
            for name in names:
                model.objects.get_or_create(name=name)
        items = {}
        for d in db["items"]:
            items[d["code"]] = save_item(data={
                "code": d["code"], "spare_type": SpareType.objects.get(name=d["type"]), "description": d["desc"],
                "cat_ref": d["catRef"], "fitting_type": FittingType.objects.filter(name=d["fittingType"]).first(),
                "wattage_w": d["watt"], "current_ma": d["ma"], "company": Company.objects.get(name=d["company"]),
                "unit": d["unit"], "reorder_level": d["reorder"], "aliases": d["aliases"], "is_active": d["active"]})
        places = {p.name: p for p in Location.objects.all()}
        posted = {}
        for e in sorted(db["entries"], key=lambda e: (e["date"], e["no"])):
            when, user = date.fromisoformat(e["date"]) + shift, users[e["by"]]
            if e["kind"] == EntryKind.REV:
                posted[e["no"]] = undo_entry(entry=posted[e["reverses"]], reason=e.get("note", "Demo undo"), user=user,
                                             entry_date=when)
                continue
            lines = [Line(items[ln["code"]], places[ln["loc"]], ln["qty"], ln.get("batch", ""),
                          date.fromisoformat(ln["pkd"] + "-01") if ln.get("pkd") else None) for ln in e["lines"]]
            company = Company.objects.filter(name=e.get("party", "")).first() if e.get("subtype") == "SUPPLIER" else None
            posted[e["no"]] = post_entry(kind=e["kind"], entry_date=when, lines=lines, user=user, subtype=e.get("subtype", ""),
                                         party=e.get("party", ""), company=company, ref=e.get("ref", ""),
                                         reason=REASONS.get(e.get("reason"), ""), note=e.get("note", ""))
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(items)} items, {len(posted)} entries."))
```
Check the exact `save_item` data keys against Task 5 (`ItemForm.cleaned_data` keys: code, spare_type, company, description, cat_ref, fitting_type, wattage_w, current_ma, unit, reorder_level, aliases (list), is_active). They match the dict above. Entry numbers come out the same as the demo file because entries are posted in date order per kind. If a demo REV appears before its target in that sort order, sort by `(date, kind == "REV", no)` instead.

`Makefile`, add:
```make
demo:  ## load demo users, items and stock history into an empty database
	docker compose exec web python manage.py seed_users
	docker compose exec web python manage.py seed_stock_demo
```

Run: `DATABASE_URL="<url>" uv run pytest tests/inventory/test_seed_demo.py -q`. Expected: PASS.

- [ ] **Step 3: Browser walkthrough** — `e2e/walkthrough.py`

This ports `mockups/stock/walkthrough.py` to the real app. It is a script run by hand (not part of pytest), using Playwright from `uv run --with playwright`.

```python
"""End-to-end walkthrough against a running dev server with demo data. Usage:

    uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office <password>
Exit code 0 = every step passed and the browser logged no JS errors.
"""

import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE, USER, PASSWORD = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
errors = []


def run(page):
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(f"{BASE}/login/")
    page.fill("#id_username", USER), page.fill("#id_password", PASSWORD), page.click("button[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("Dashboard")

    # Stock IN with a brand-new item created from the picker
    page.goto(f"{BASE}/stock/in/")
    page.locator(".lines-table .ts-control input").first.fill("TEST-NEW-1")
    page.locator(".ts-dropdown .create").click()
    page.select_option("#new-item-modal #id_spare_type", label="Driver")
    page.click("#new-item-form button[type=submit]")
    expect(page.locator("#new-item-modal")).to_be_hidden()
    page.locator("input[name=line_qty]").first.fill("5")
    page.select_option("#id_company", label="Wipro Lighting")
    page.click("button.btn-in[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("IN-")

    # Over-issue refused live and by the server
    page.goto(f"{BASE}/stock/out/")
    page.locator(".lines-table .ts-control input").first.fill("TEST-NEW-1")
    page.locator(".ts-dropdown .option").first.click()
    page.locator("input[name=line_qty]").first.fill("99")
    expect(page.locator(".err").first).to_contain_text("Only 5 NOS available")

    # Look-alike search in the top bar
    page.fill("#gsearch", "ei08437")
    expect(page.locator(".gsearch-menu")).to_contain_text("EIO8437")

    # Current stock: sort + export
    page.goto(f"{BASE}/stock/?sort=total&dir=desc")
    with page.expect_download() as dl:
        page.click("text=Export to Excel")
    assert dl.value.suggested_filename.startswith("Current_Stock_")

    # Undo the IN we made
    page.goto(f"{BASE}/movements/?q=TEST-NEW-1")
    page.locator("a.code", has_text=re.compile(r"^IN-")).first.click()
    page.click("text=Undo this entry")
    page.fill("#undo-reason", "walkthrough cleanup")
    page.click("#undo-modal button[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("REV-")


def phone(page):
    """Phone width: log in, open the off-canvas menu, open a list screen."""
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/login/")
    page.fill("#id_username", USER), page.fill("#id_password", PASSWORD), page.click("button[type=submit]")
    page.click(".navbar-toggler")
    expect(page.get_by_role("link", name="Stock IN").first).to_be_visible()
    page.goto(f"{BASE}/stock/")
    expect(page.locator("table")).to_be_visible()


with sync_playwright() as p:
    browser = p.chromium.launch()
    for size in ({"width": 1366, "height": 860}, {"width": 390, "height": 844}):
        page = browser.new_page(viewport=size)
        run(page) if size["width"] > 500 else phone(page)
        page.screenshot(path=f"e2e/screen-{size['width']}.png", full_page=True)
    browser.close()

print("JS errors:", errors or "none")
sys.exit(1 if errors else 0)
```
Add `e2e/*.png` to `.gitignore`.

Run it against the dev server with demo data:
```bash
DATABASE_URL="<url>" uv run python manage.py migrate
DATABASE_URL="<url>" SEED_PASSWORD="demo-pass-123" uv run python manage.py seed_users
DATABASE_URL="<url>" uv run python manage.py seed_stock_demo
DATABASE_URL="<url>" uv run python manage.py runserver 8000   # background
uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office demo-pass-123
```
Expected: exit 0, "JS errors: none". Open both screenshots and check them by eye (sidebar, tables, no overlaps).

- [ ] **Step 4: Docs**

- `README.md`: what the app does (one paragraph), local setup (`docker compose up`, `make demo`), the no-Docker dev setup (`uv sync`, `DATABASE_URL`, `manage.py migrate/seed_users/seed_stock_demo/runserver`), tests (`uv run pytest`), the e2e walkthrough command, and roles (Admin / Office).
- `CLAUDE.md`: add a "Build" section with the commands above, where business logic lives (`services.py` writes, `selectors.py` reads, `entry_lines.py` line parsing, `core/excel.py` exports), and the rule "never write to StockEntry/StockLine/StockBalance outside services.py".
- `tasks/todo.md`: mark Step B done, with the test count and walkthrough result as evidence.

- [ ] **Step 5: Full check and commit**

```bash
DATABASE_URL="<url>" uv run pytest -q                      # all pass
uv run ruff format --check . && uv run ruff check .
DATABASE_URL="<url>" uv run python manage.py check --deploy --settings=config.settings.prod  # no errors besides HTTPS-host warnings
git add -A
git commit -m "feat: demo data command, e2e walkthrough, docs"
```
