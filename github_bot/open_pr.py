from __future__ import annotations

import os
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()

def open_or_get_pr(
    owner: str | None,
    repo: str | None,
    head: str,
    base: str,
    title: str,
    body: str,
) -> str:
    """
    Open a PR if it doesn't exist; otherwise return existing PR URL.

    head should be the *branch name* on the same repo, e.g. "autopatcher/fix-sqli-1"
    """

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not found in .env")

    if not owner or not repo:
        raise RuntimeError("owner/repo not provided. Set GITHUB_OWNER and GITHUB_REPO in .env.")

    g = Github(auth=Auth.Token(token))
    r = g.get_repo(f"{owner}/{repo}")

    # If PR already exists from this head -> return it
    pulls = r.get_pulls(state="open", head=f"{owner}:{head}")
    if pulls.totalCount > 0:
        return pulls[0].html_url

    pr = r.create_pull(
        title=title,
        body=body,
        head=head,
        base=base,
    )
    return pr.html_url


def main():
    """
    Manual test mode (safe): should return existing PR if you already created one.
    """
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")

    url = open_or_get_pr(
        owner=owner,
        repo=repo,
        head="autopatcher/fix-sqli-1",
        base="main",
        title="AutoPatch: Fix SQL injection (parameterized query)",
        body="Test PR body",
    )
    print("PR:", url)


if __name__ == "__main__":
    main()
