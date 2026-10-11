COMPOSE = docker compose
RUN = $(COMPOSE) run --rm web
LEGACY = data/legacy

.PHONY: up down build logs migrate makemigrations seed test lint fmt shell check import-review import-apply

up:            ## start db + web (http://localhost:8000)
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f web

migrate:
	$(RUN) python manage.py migrate

makemigrations:
	$(RUN) python manage.py makemigrations

seed:
	$(RUN) python manage.py seed_demo

test:          ## pytest against postgres:16 in compose
	$(RUN) pytest --cov=apps --cov-report=term-missing $(ARGS)

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt:
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

shell:
	$(RUN) python manage.py shell

check:
	$(RUN) python manage.py check

import-review: ## Phase 2: write $(LEGACY)/import_review.xlsx
	$(RUN) python manage.py import_legacy --review

import-apply:  ## Phase 2: apply an approved review workbook
	$(RUN) python manage.py import_legacy --apply $(LEGACY)/import_review.xlsx
