FROM python:3.12-slim

WORKDIR /app

# Git required to commit/push. ca-certs for HTTPS.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install runtime deps
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENTRYPOINT ["python", "main.py"]
