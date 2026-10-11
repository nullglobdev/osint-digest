#!/bin/sh
# Run from any working directory. All operator interaction stays in the terminal.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if ! docker compose version >/dev/null 2>&1; then
    echo 'Install Docker Engine and the Docker Compose plugin first.' >&2
    exit 1
fi
case "${1:-help}" in
    setup)
        docker compose build --pull digest
        docker compose run --rm digest setup
        echo 'Setup saved. Start background checks with: sh scripts/server.sh start'
        ;;
    settings|sources|models|webhooks|scope|filters) docker compose run --rm digest "$1" ;;
    start) docker compose up -d digest ;;
    stop) docker compose stop digest ;;
    logs) docker compose logs --follow --tail 100 digest ;;
    status)
        docker compose ps
        docker compose run --rm -T digest status
        ;;
    update)
        docker compose build --pull digest
        docker compose up -d digest
        ;;
    check-feeds|test-ai|preview|batch|new|test-discord|backup)
        docker compose run --rm -T digest "$@"
        ;;
    *)
        echo 'Usage: sh scripts/server.sh setup|settings|sources|models|webhooks|scope|filters|start|stop|status|logs|update'
        echo 'Actions: check-feeds|test-ai [--source NAME]|preview|new|test-discord|backup'
        echo 'Manual tests: new|preview --test-mode [--count N] [--test-days 1-365] (allows repeat articles)'
        echo 'Previews and AI tests also accept --test-days 1-365; normal checks keep the 48-hour window.'
        ;;
esac
