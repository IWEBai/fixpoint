import requests
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from core.github_app_auth import get_installation_access_token

token = get_installation_access_token(112237863)
sha = "2b0f88fe93fd7652e29cfc670072799771141f85"
owner = "zariffromlatif"
repo = "railo-webhook-test"

resp = requests.get(
    f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs",
    headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Total: {data.get('total_count', 0)}")
for cr in data.get("check_runs", []):
    print(f"  - {cr['name']}: {cr['conclusion']} ({cr['html_url']})")
