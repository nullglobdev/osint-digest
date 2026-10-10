# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OSINT_DATA_DIR=/data
WORKDIR /app
RUN groupadd --gid 10001 osint && useradd --uid 10001 --gid osint --no-create-home osint \
    && mkdir -p /data && chown osint:osint /data && chmod 700 /data
# Explicit allowlist: no desktop runtime, credentials, previews, or delivery state.
COPY bot.py ai_endpoints.py desktop_ai.py desktop_sources.py server.py server_settings.py server_setup.py sources.json ./
USER 10001:10001
VOLUME ["/data"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "server.py", "health"]
ENTRYPOINT ["python", "/app/server.py"]
CMD ["serve"]
