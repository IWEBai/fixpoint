import requests
import sys

sha = sys.argv[1] if len(sys.argv) > 1 else "2b0f88f"
owner = "zariffromlatif"
repo = "railo-webhook-test"
resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs")
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Total: {data.get('total_count', 0)}")
for cr in data.get("check_runs", []):
    print(f"  - {cr['name']}: {cr['conclusion']} ({cr['html_url']})")
