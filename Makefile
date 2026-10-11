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
