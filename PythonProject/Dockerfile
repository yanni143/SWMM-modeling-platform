FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY pyproject.toml alembic.ini ./
COPY requirements.txt ./

# 依赖层只由 requirements.txt 失效；普通源码修改会复用这一层，避免每次部署
# 都重新下载/安装 PySWMM、SQLAlchemy 等依赖。
RUN pip install --upgrade pip "setuptools>=68" \
    && pip install -r requirements.txt

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

# 依赖已经在上层安装；这里只安装当前源码包，不再触发依赖解析或安装。
RUN pip install --no-build-isolation --no-deps . \
    && mkdir -p /app/.runtime \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn Controller.controller:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
