"""Check GitHub App installation permissions"""
import os, sys, time, json, urllib.request, base64
sys.path.insert(0, r"E:\\railo-cloud")
from core.github_app_auth import _load_private_key, _get_jwt_module

app_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("GITHUB_APP_ID", "2914293")
private_key = _load_private_key()
if not private_key:
    # Try loading from keyvault
    import subprocess
    pk = subprocess.check_output("az keyvault secret show --vault-name railo-kv --name github-private-key --query value -o tsv", shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    os.environ["GITHUB_APP_PRIVATE_KEY"] = pk
    private_key = pk

jwt_mod = _get_jwt_module()
now = int(time.time())
payload = {"iat": now - 60, "exp": now + 600, "iss": str(app_id).strip()}
encoded_jwt = jwt_mod.encode(payload, private_key, algorithm="RS256")

# Get installation token and check permissions
url = "https://api.github.com/app/installations/112237863/access_tokens"
req = urllib.request.Request(url, data=b"", headers={
    "Authorization": f"Bearer {encoded_jwt}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}, method="POST")

with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
    print("Token prefix:", data.get("token", "")[:10] + "...")
    print("Permissions:", json.dumps(data.get("permissions", {}), indent=2))
