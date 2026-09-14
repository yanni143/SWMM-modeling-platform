FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY Controller ./Controller
COPY Service ./Service
COPY Tools ./Tools
COPY database ./database
COPY models ./models
COPY schemas ./schemas
COPY storage ./storage
COPY swmm_core ./swmm_core
COPY resources ./resources
COPY config.py ./config.py
COPY study_areas.py ./study_areas.py

RUN pip install --upgrade pip \
    && pip install . \
    && mkdir -p /app/.runtime \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn Controller.controller:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
