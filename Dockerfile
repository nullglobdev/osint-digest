# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OSINT_DATA_DIR=/data
WORKDIR /app
RUN groupadd --gid 10001 osint && useradd --uid 10001 --gid osint --no-create-home osint \
    && mkdir -p /data && chown osint:osint /data && chmod 700 /data
# Explicit allowlist: no desktop runtime, credentials, previews, or delivery state.
COPY server.py ./
COPY osint_digest/__init__.py osint_digest/paths.py ./osint_digest/
COPY osint_digest/core/*.py ./osint_digest/core/
COPY osint_digest/server/*.py ./osint_digest/server/
COPY config/sources.json ./config/
USER 10001:10001
VOLUME ["/data"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "server.py", "health"]
ENTRYPOINT ["python", "/app/server.py"]
CMD ["serve"]
