"""Replay a webhook fixture against the local API."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import requests

API_URL = "http://localhost:8000/webhook"
SECRET = "devsecret"
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "pull_request.json"


def sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def main() -> None:
    body = FIXTURE.read_bytes()
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": sign(body),
        "X-GitHub-Delivery": "local-replay",
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, data=body, headers=headers, timeout=10)
    print(resp.status_code, resp.text)


if __name__ == "__main__":
    main()
