"""Check for check runs on the test repo"""
import os, sys, json, time, urllib.request
sys.path.insert(0, r"E:\fixpoint-cloud")
from core.github_app_auth import _load_private_key, _get_jwt_module

pk = __import__('subprocess').check_output("az keyvault secret show --vault-name railo-kv --name github-private-key --query value -o tsv", shell=True, text=True, stderr=__import__('subprocess').DEVNULL).strip()
os.environ["GITHUB_APP_PRIVATE_KEY"] = pk

jwt_mod = _get_jwt_module()
now = int(time.time())
payload = {"iat": now - 60, "exp": now + 600, "iss": "2914293"}
encoded_jwt = jwt_mod.encode(payload, pk, algorithm="RS256")

url = "https://api.github.com/app/installations/112237863/access_tokens"
req = urllib.request.Request(url, data=b"", headers={
    "Authorization": f"Bearer {encoded_jwt}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}, method="POST")

with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
    token = data["token"]

import requests
sha = "2b0f88fe93fd7652e29cfc670072799771141f85"
resp = requests.get(
    f"https://api.github.com/repos/zariffromlatif/railo-webhook-test/commits/{sha}/check-runs",
    headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Total check runs: {data.get('total_count', 0)}")
for cr in data.get("check_runs", []):
    print(f"  - {cr['name']}: {cr['conclusion']} ({cr['html_url']})")
if data.get("total_count", 0) == 0:
    print("No check runs found on this commit")
