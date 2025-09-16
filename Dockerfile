# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11-slim

FROM python:${PYTHON_VERSION} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /wheels
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:${PYTHON_VERSION} AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UI_PORT=5000 \
    INDEX_DIR=/app/data/index \
    CRAWL_STORE=/app/data/crawl
WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt

COPY . /app

ARG USE_JS_FALLBACK=true
RUN if [ "$USE_JS_FALLBACK" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends libnss3 libatk1.0-0 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 libasound2 libpangocairo-1.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgtk-3-0 && \
        rm -rf /var/lib/apt/lists/* && \
        python -m playwright install --with-deps chromium; \
    else \
        true; \
    fi

EXPOSE ${UI_PORT}
CMD ["python", "app.py"]
