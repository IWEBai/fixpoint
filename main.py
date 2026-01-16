from __future__ import annotations

import argparse
from email.mime import text
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone


from dotenv import load_dotenv

# Import our existing components
# (We will make fix_sqli accept a repo path in Step A2)
from github_bot.open_pr import open_or_get_pr  # we'll create this function in Step A3


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """
    Run a command and raise a readable error if it fails.
    Windows-safe: force UTF-8 decoding (and ignore undecodable chars).
    """
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n\nSTDOUT:\n{p.stdout}\n\nSTDERR:\n{p.stderr}"
        )
    return p



def semgrep_scan(repo_path: Path, rules_path: Path, out_json: Path) -> dict:
    """Run semgrep and write JSON to out_json."""
    cmd = [
        "semgrep",
        "--config",
        str(rules_path),
        "--json",
        "--output",
        str(out_json),
        str(repo_path),
    ]
    run(cmd)
    raw = out_json.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    return json.loads(text)



def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Compliance Auto-Patcher (MVP)")
    parser.add_argument("repo", type=str, help="Path to local git repo to patch")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Repo path does not exist: {repo_path}")

    rules_path = Path(__file__).parent / "rules" / "sql_injection.yaml"
    results_path = Path("semgrep_results.json")

    print(f"[1/5] Scanning repo with Semgrep: {repo_path}")
    data = semgrep_scan(repo_path, rules_path, results_path)

    results = data.get("results", [])
    if not results:
        print("No findings. Exiting.")
        return

    print(f"[2/5] Findings: {len(results)}")
    # For MVP: only process the first finding
    finding = results[0]
    file_path = finding.get("path")
    start = finding.get("start", {}).get("line")
    message = finding.get("extra", {}).get("message", "").strip()

    print(f" - file: {file_path}")
    print(f" - line: {start}")
    print(f" - msg : {message}")

    print("[3/5] Applying SQLi fix (deterministic)")
    # Step A2 will implement this function properly
    from patcher.fix_sqli import apply_fix_sqli

    changed = apply_fix_sqli(repo_path)
    if not changed:
        print("No fix applied (already safe or pattern mismatch).")

    print("[4/5] Creating branch + commit + push")
    branch_name = f"autopatcher/fix-sqli-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}"

    # Create branch
    run(["git", "checkout", "-B", branch_name], cwd=repo_path)

    # Ensure git identity exists (required on GitHub Actions runners)
    run(
        ["git", "config", "user.email", "auditshield-bot@users.noreply.github.com"],
        cwd=repo_path,
    )
    run(
        ["git", "config", "user.name", "auditshield-bot"],
        cwd=repo_path,
    )
    # Stage changes
    run(["git", "add", "."], cwd=repo_path)

    # Only commit if there are changes
    status = run(["git", "status", "--porcelain"], cwd=repo_path)
    if status.stdout.strip():
        run(
            ["git", "commit", "-m", "Fix SQL injection by parameterizing query"],
            cwd=repo_path,
        )
        run(["git", "push", "-u", "origin", branch_name], cwd=repo_path)
    else:
        print("No changes to commit.")


    print("[5/5] Opening PR (or reusing existing)")
    pr_url = open_or_get_pr(
        owner=os.getenv("GITHUB_OWNER"),
        repo=os.getenv("GITHUB_REPO"),
        head=branch_name,
        base="main",
        title="AutoPatch: Fix SQL injection (parameterized query)",
        body=(
            "This PR was generated automatically.\n\n"
            "## What was found\n"
            "- Possible SQL injection via string formatting.\n\n"
            "## What changed\n"
            "- Replaced formatted SQL with a parameterized query.\n"
            "- Updated execute call to pass parameters safely.\n\n"
            "## Safety\n"
            "- Minimal diff\n"
            "- No refactors\n"
        ),
    )

    print("Done.")
    print("PR:", pr_url)


if __name__ == "__main__":
    main()
