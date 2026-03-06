#!/bin/bash
# docker-entrypoint.sh
# Starts the cron daemon (maintenance + digest flush) when the container runs
# as root, then execs the main process via "$@".
#
# Usage (web server mode):
#   docker run --env MAINTENANCE_CRON_ENABLED=true railo-web gunicorn -b 0.0.0.0:8080 webhook.server:app
#
# Usage (GitHub Actions / default):
#   docker run railo python main.py
set -e

if [ "${MAINTENANCE_CRON_ENABLED:-false}" = "true" ]; then
    if [ "$(id -u)" = "0" ]; then
        echo "[railo-entrypoint] MAINTENANCE_CRON_ENABLED=true — starting cron daemon"
        service cron start || cron
    else
        echo "[railo-entrypoint] WARNING: MAINTENANCE_CRON_ENABLED=true but running as non-root." >&2
        echo "[railo-entrypoint] Cron will not start. Use a separate Container Apps Job instead." >&2
    fi
fi

exec "$@"
