FROM python:3.12-slim

WORKDIR /app

# Git required to commit/push. ca-certs for HTTPS. cron for maintenance schedule. curl for health checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates cron curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install runtime deps + Semgrep (required for scanning)
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir semgrep

# Copy application code
COPY . /app

# Install maintenance cron schedule
COPY scripts/crontab.railo /etc/cron.d/railo-maintenance
RUN chmod 0644 /etc/cron.d/railo-maintenance && touch /var/log/railo-cron.log

# Copy and install entrypoint (runs as root — starts cron then drops to appuser)
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check: verifies the HTTP server is up and responds correctly
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Web server mode (with cron):
#   docker run -e MAINTENANCE_CRON_ENABLED=true -e FLASK_APP=webhook.server \
#              railo /usr/local/bin/docker-entrypoint.sh gunicorn -b 0.0.0.0:8080 webhook.server:app
#
# GitHub Actions mode (default):
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "main.py"]
