# Nourai backend image (Flask + Gunicorn)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

# System deps: libpq not needed (MySQL via PyMySQL? -> use mysqlclient? we use PyMySQL pure-python)
# Pillow needs libjpeg/zlib at runtime; tiktoken needs a C build at install time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libjpeg62-turbo-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

EXPOSE 8000

# NOTE: MySQL driver — SQLAlchemy needs one for mysql:// URLs.
# We depend on PyMySQL (pure python) so no extra system packages are required.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "app:create_app()"]
