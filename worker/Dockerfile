# Ingestion worker image (ARQ). Build context: repository root.

FROM python:3.12-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/backend:/app
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data/storage && chown app:app /data/storage
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY backend/app/ /app/backend/app/
COPY worker/ /app/worker/
USER app
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["arq", "--check", "worker.main.WorkerSettings"]
CMD ["arq", "worker.main.WorkerSettings"]
