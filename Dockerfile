# LERNA Voice AI Service — production image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY streamlit_app ./streamlit_app

# Debian (python:3.12-slim <-> base-passwd) already ships a `voice` group (GID 22),
# so plain `useradd voice` aborts with "group voice exists". Create idempotently and
# attach the service user to whichever `voice` group the base image provides.
RUN set -eux; \
    getent group voice >/dev/null || groupadd --system voice; \
    id -u voice >/dev/null 2>&1 || useradd --create-home --uid 10001 --gid voice voice; \
    chown -R voice:voice /app
USER voice

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# One worker: voice sessions are stateful and live in-process.
# Scale horizontally with sticky sessions, not with extra workers.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --timeout-keep-alive 75 --no-access-log"]
