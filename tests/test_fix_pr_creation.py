from pathlib import Path

import core.fix_pr_service as svc


def _sample_findings():
    return [
        {
            "check_id": "SQLi",
            "path": "app/db.py",
            "extra": {"metadata": {"confidence": 90}},
        },
        {
            "check_id": "xss",
            "path": "app/templates/index.html",
            "extra": {"metadata": {"confidence": 80}},
        },
    ]


def test_generate_fix_branch_name_format():
    name = svc.generate_fix_branch_name(_sample_findings(), original_pr_number=12)
    assert name.startswith("railo/pr12-fix-"), f"Expected 'railo/pr12-fix-...' prefix, got: {name}"
    assert "pr12" in name


def test_estimate_fix_safety_ranges():
    score = svc.estimate_fix_safety(_sample_findings())
    assert 0 <= score <= 100
    assert score >= 60


def test_build_fix_pr_metadata_contains_links():
    title, body = svc.build_fix_pr_metadata(
        _sample_findings(),
        original_pr_number=12,
        original_pr_url="https://example.com/pr/12",
        original_pr_author="octocat",
        safety_score=85,
    )
    assert "PR #12" in title
    assert "octocat" in body
    assert "https://example.com/pr/12" in body


def test_create_fix_pr_success(monkeypatch, tmp_path):
    calls = {}

    def fake_create_branch(repo_path: Path, branch_name: str, commit_message: str):
        calls["branch"] = (branch_name, commit_message)
        return True, None

    def fake_open_pr(owner, repo, head, base, title, body, labels=None, assignee=None, request_reviewers=None):
        calls["pr"] = {
            "owner": owner,
            "repo": repo,
            "head": head,
            "base": base,
            "title": title,
            "body": body,
            "labels": labels,
        }
        return {"number": 55, "html_url": "https://example.com/pr/55", "url": "https://example.com/pr/55"}

    monkeypatch.setattr(svc, "create_fix_pr_branch", fake_create_branch)
    monkeypatch.setattr(svc, "open_or_get_pr", fake_open_pr)

    ok, info = svc.create_fix_pr(
        findings=_sample_findings(),
        owner="iweb",
        repo_name="railo",
        original_pr_number=12,
        original_pr_author="octocat",
        original_pr_url="https://example.com/pr/12",
        base_branch="main",
        repo_path=tmp_path,
    )

    assert ok is True
    assert info["fix_pr_number"] == 55
    assert "branch" in calls
    assert calls["pr"]["head"] == info["branch_name"]
