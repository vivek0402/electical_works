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
