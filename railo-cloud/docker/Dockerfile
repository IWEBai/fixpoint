FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appgroup \
    && useradd -r -g appgroup -m -d /home/appuser appuser

COPY railo-cloud/requirements.cloud.txt /app/requirements.cloud.txt
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.cloud.txt

COPY . /app
# Overwrite with freshly built frontend (replaces any stale committed dist)
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# Ensure non-root user owns the app files
RUN chown -R appuser:appgroup /app \
    && mkdir -p /artifacts /tmp/fixpoint-live \
    && chown -R appuser:appgroup /artifacts /tmp/fixpoint-live

USER appuser

ENV PYTHONPATH=/app:/app/railo-cloud

# Default command is API; worker overrides in compose
CMD ["uvicorn", "railo_cloud.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
