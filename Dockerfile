# syntax=docker/dockerfile:1
# Base: python:3.13-slim, resolved to its index digest on 2026-11-24 (ADR-0017). Base-image fixes arrive
# only when this digest is updated by hand.

FROM python:3.13-slim@sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50 AS builder
WORKDIR /app
COPY requirements.txt ./
RUN python -m venv .venv \
    && .venv/bin/python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt

FROM python:3.13-slim@sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin tollgate
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY app ./app
COPY deploy/logging.json ./deploy/logging.json
USER 10001
EXPOSE 8000
# Exec form, so uvicorn is PID 1 and receives SIGTERM. One worker per container (ADR-0017).
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "deploy/logging.json", "--no-access-log"]
