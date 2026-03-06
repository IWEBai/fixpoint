"""Test creating a check run on the test repo"""
import os, sys, json, time, urllib.request
sys.path.insert(0, r"E:\fixpoint-cloud")
from core.github_app_auth import _load_private_key, _get_jwt_module

# Get installation token
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

# Now try to create a check run
os.environ["GITHUB_TOKEN"] = token

try:
    from github import Github, Auth
    g = Github(auth=Auth.Token(token))
    r = g.get_repo("zariffromlatif/railo-webhook-test")
    check_run = r.create_check_run(
        name="Fixpoint - Security Check",
        head_sha="adf62e8e07c0eebcb7fd5e8ae35ad42dbd9116a8",
        status="completed",
        conclusion="success",
        output={
            "title": "Fixpoint - Security Check",
            "summary": "No violations detected by Fixpoint.",
            "annotations": [],
        },
    )
    print(f"Check run created: {check_run.html_url}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
