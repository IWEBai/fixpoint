FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \ 
    && apt-get install -y --no-install-recommends git curl \ 
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appgroup \
    && useradd -r -g appgroup -m -d /home/appuser appuser

COPY fixpoint-cloud/requirements.cloud.txt /app/requirements.cloud.txt
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.cloud.txt

COPY . /app

# Ensure non-root user owns the app files
RUN chown -R appuser:appgroup /app \
    && mkdir -p /artifacts /tmp/fixpoint-live \
    && chown -R appuser:appgroup /artifacts /tmp/fixpoint-live

USER appuser

ENV PYTHONPATH=/app:/app/fixpoint-cloud

# Default command is API; worker overrides in compose
CMD ["uvicorn", "fixpoint_cloud.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
