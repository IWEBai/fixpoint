"""
Tests for the Railo magic moment.

The core user journey:
  Developer opens a PR
  → Railo scans it
  → Railo comments on the PR
  → Railo creates a Fix PR
  → Developer reviews and merges

Every step must be reliable, readable, and understandable in under 20 seconds.
"""
from __future__ import annotations

import re
import inspect
import pytest

from core.fix_pr_service import (
    generate_fix_branch_name,
    build_fix_pr_metadata,
    estimate_fix_safety,
    estimate_fix_confidence,
    _vuln_label,
)
from core.pr_comments import (
    generate_fix_pr_notification,
    _vuln_label as pr_vuln_label,
    _confidence_bar,
    _extract_confidence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sqli_finding():
    return {
        "check_id": "python.django.security.injection.tainted-sql-string",
        "path": "app/views.py",
        "start": {"line": 42},
        "extra": {
            "message": "SQL injection via f-string",
            "metadata": {"confidence": "high", "severity": "ERROR"},
        },
    }


@pytest.fixture
def xss_finding():
    return {
        "check_id": "python.django.security.xss.mark-safe",
        "path": "app/templates/index.html",
        "start": {"line": 17},
        "extra": {
            "message": "XSS via mark_safe",
            "metadata": {"confidence": "medium"},
        },
    }


@pytest.fixture
def two_findings(sqli_finding, xss_finding):
    return [sqli_finding, xss_finding]


@pytest.fixture
def sample_previews():
    return [
        {
            "file": "app/views.py",
            "line": 42,
            "before": 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")',
            "after": "cursor.execute(\"SELECT * FROM users WHERE id = %s\", (user_id,))",
            "check_id": "python.django.security.injection.tainted-sql-string",
            "confidence": 90,
        }
    ]


# ---------------------------------------------------------------------------
# Step 1: Fix branch naming — must be readable at a glance
# ---------------------------------------------------------------------------

class TestFixBranchNaming:
    def test_starts_with_railo_prefix(self, sqli_finding):
        name = generate_fix_branch_name([sqli_finding], original_pr_number=42)
        assert name.startswith("railo/"), f"Branch must start with 'railo/', got: {name}"

    def test_pr_number_is_prominent(self, sqli_finding):
        name = generate_fix_branch_name([sqli_finding], original_pr_number=42)
        assert "pr42" in name, f"PR number must appear as 'pr42' in branch name, got: {name}"

    def test_contains_vuln_type(self, sqli_finding):
        name = generate_fix_branch_name([sqli_finding], original_pr_number=42)
        assert "sqli" in name or "sql" in name, f"Vuln type missing from branch name: {name}"

    def test_xss_finding_produces_xss_branch(self, xss_finding):
        name = generate_fix_branch_name([xss_finding], original_pr_number=7)
        assert "xss" in name, f"XSS finding should produce xss branch, got: {name}"

    def test_no_opaque_file_hash(self, sqli_finding):
        """The old format included a 6-char sha1 fragment — remove it."""
        name = generate_fix_branch_name([sqli_finding], original_pr_number=42)
        parts = name.split("-")
        opaque_hex = [p for p in parts if len(p) == 6 and re.fullmatch(r"[0-9a-f]+", p)]
        assert opaque_hex == [], f"Branch name contains opaque hex hash: {name}"

    def test_no_full_timestamp(self, sqli_finding):
        """Time-of-day (HHMMSS) makes branch names unreadable — use date only."""
        name = generate_fix_branch_name([sqli_finding], original_pr_number=1)
        assert not re.search(r"-\d{6}(-|$)", name), (
            f"Branch should not contain 6-digit HHMMSS timestamp, got: {name}"
        )

    def test_contains_date_component(self, sqli_finding):
        name = generate_fix_branch_name([sqli_finding], original_pr_number=1)
        assert re.search(r"\d{6,8}", name), f"Branch should contain a date component, got: {name}"

    def test_empty_findings_graceful(self):
        name = generate_fix_branch_name([], original_pr_number=5)
        assert name.startswith("railo/pr5-fix-"), f"Should still produce valid name, got: {name}"

    def test_max_length_under_80_chars(self, two_findings):
        name = generate_fix_branch_name(two_findings, original_pr_number=99999)
        assert len(name) <= 80, f"Branch name too long ({len(name)} chars): {name}"

    def test_different_pr_numbers_produce_different_names(self, sqli_finding):
        a = generate_fix_branch_name([sqli_finding], original_pr_number=1)
        b = generate_fix_branch_name([sqli_finding], original_pr_number=2)
        assert a != b, "Different PR numbers must produce different branch names"


# ---------------------------------------------------------------------------
# Step 2: Fix PR title — first thing the developer reads
# ---------------------------------------------------------------------------

class TestFixPRTitle:
    def test_starts_with_railo(self, two_findings):
        title, _ = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert title.startswith("Railo:"), f"Title must start with 'Railo:': {title}"

    def test_contains_pr_number(self, two_findings):
        title, _ = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "#42" in title or "42" in title, f"PR number missing from title: {title}"

    def test_no_awkward_issue_s(self, two_findings):
        title, _ = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "issue(s)" not in title, f"'issue(s)' is awkward; use 'issues': {title}"

    def test_singular_plural_one_finding(self, sqli_finding):
        title, _ = build_fix_pr_metadata(
            [sqli_finding], 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert " 1 security issue " in title, f"Single finding should use 'issue' (not 'issues'): {title}"

    def test_plural_multiple_findings(self, two_findings):
        title, _ = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert " 2 security issues " in title, f"Multiple findings should use 'issues': {title}"

    def test_no_raw_check_id_in_title(self, sqli_finding):
        title, _ = build_fix_pr_metadata(
            [sqli_finding], 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "python.django" not in title.lower(), f"Raw check_id leaked into title: {title}"
        assert "tainted" not in title.lower(), f"Raw check_id detail leaked into title: {title}"

    def test_empty_findings_graceful(self):
        title, _ = build_fix_pr_metadata(
            [], 5, "https://github.com/o/r/pull/5", "bob", 0.0
        )
        assert title.startswith("Railo:"), f"Empty findings title should still start with 'Railo:': {title}"


# ---------------------------------------------------------------------------
# Step 3: Fix PR body — must be skimmable in 20 seconds
# ---------------------------------------------------------------------------

class TestFixPRBody:
    def test_original_pr_linked(self, two_findings):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "#42" in body
        assert "alice" in body

    def test_safety_score_visible(self, two_findings):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 87.0
        )
        assert "87" in body, "Safety score must appear in fix PR body"

    def test_confidence_visible_when_provided(self, two_findings):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0,
            confidence=91.0
        )
        assert "91" in body, "Confidence must appear in fix PR body when provided"

    def test_next_steps_present(self, two_findings):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "Next steps" in body or "Review" in body

    def test_sentinel_comment_present(self, two_findings):
        """Sentinel <!-- railo-fix --> is used for idempotency lookups."""
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "railo-fix" in body, "Idempotency sentinel must be present in fix PR body"

    def test_body_concise_without_previews(self, two_findings):
        """Without code previews the body should be short enough to read in 20 seconds."""
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert len(body) < 900, (
            f"Fix PR body too long without previews ({len(body)} chars) — developers shouldn't need to scroll"
        )

    def test_before_after_blocks_with_previews(self, two_findings, sample_previews):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0,
            previews=sample_previews
        )
        assert "Before:" in body
        assert "After:" in body
        assert "SELECT * FROM users" in body   # before block content
        assert "%s" in body                    # after block content

    def test_previews_use_human_label_not_raw_check_id(self, two_findings, sample_previews):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0,
            previews=sample_previews
        )
        # The display label for the preview item should be human-readable
        assert "SQL Injection" in body, "Preview label should say 'SQL Injection' not raw check_id"
        assert "python.django.security.injection" not in body, (
            "Raw check_id must not appear as section label in fix PR previews"
        )

    def test_no_fixpoint_branding(self, two_findings):
        _, body = build_fix_pr_metadata(
            two_findings, 42, "https://github.com/o/r/pull/42", "alice", 82.0
        )
        assert "Fixpoint" not in body, "Old 'Fixpoint' branding must not appear in fix PR body"


# ---------------------------------------------------------------------------
# Step 4: Original PR notification — first thing developer sees after scan
# ---------------------------------------------------------------------------

class TestFixPRNotification:
    def test_fix_pr_link_present(self, two_findings):
        text = generate_fix_pr_notification(
            fix_pr_number=99,
            fix_pr_url="https://github.com/o/r/pull/99",
            safety_score=85.0,
            vuln_count=2,
            vuln_types=["sqli", "xss"],
            findings=two_findings,
        )
        assert "99" in text
        assert "https://github.com/o/r/pull/99" in text

    def test_fix_pr_link_is_prominent_cta(self, two_findings):
        """The link must be a heading or bold CTA, not buried in prose."""
        text = generate_fix_pr_notification(
            fix_pr_number=99,
            fix_pr_url="https://github.com/o/r/pull/99",
            safety_score=85.0,
            vuln_count=2,
            vuln_types=["sqli"],
            findings=two_findings,
        )
        # Must be a CTA heading (###) or prominent emoji arrow
        assert ("### " in text and "pull/99" in text) or "👉" in text, (
            "Fix PR link must be a prominent CTA (heading or 👉), not buried in text"
        )

    def test_branch_untouched_message(self, two_findings):
        text = generate_fix_pr_notification(
            fix_pr_number=55, fix_pr_url="u", safety_score=80.0,
            vuln_count=1, vuln_types=["sqli"], findings=two_findings,
        )
        lowered = text.lower()
        assert "not modified" in lowered or "untouched" in lowered or "unchanged" in lowered, (
            "Developer must be told their branch was not modified"
        )

    def test_safety_score_shown(self):
        text = generate_fix_pr_notification(
            fix_pr_number=55, fix_pr_url="u", safety_score=82.0,
            vuln_count=1, vuln_types=["sqli"],
        )
        assert "82" in text, "Safety score must be visible in notification"

    def test_with_previews_shows_before_after(self, sample_previews, two_findings):
        text = generate_fix_pr_notification(
            fix_pr_number=55, fix_pr_url="u", safety_score=80.0,
            vuln_count=1, vuln_types=["sqli"], findings=two_findings,
            previews=sample_previews,
        )
        assert "Before:" in text
        assert "After:" in text
        assert "SELECT * FROM users" in text

    def test_without_previews_shows_findings_table(self, two_findings):
        """Fallback: when no previews given, a compact table replaces the blocks."""
        text = generate_fix_pr_notification(
            fix_pr_number=55, fix_pr_url="u", safety_score=80.0,
            vuln_count=2, vuln_types=["sqli", "xss"], findings=two_findings,
        )
        assert "app/views.py" in text, "Findings table should show file names"

    def test_railo_branding(self, two_findings):
        text = generate_fix_pr_notification(
            fix_pr_number=55, fix_pr_url="u", safety_score=80.0,
            vuln_count=1, vuln_types=["sqli"], findings=two_findings,
        )
        assert "Railo" in text, "Notification must mention Railo"

    def test_no_fixpoint_branding(self, two_findings):
        text = generate_fix_pr_notification(
            fix_pr_number=55, fix_pr_url="u", safety_score=80.0,
            vuln_count=1, vuln_types=["sqli"], findings=two_findings,
        )
        assert "Fixpoint" not in text, "Old 'Fixpoint' branding must not appear"

    def test_notification_concise_without_previews(self):
        """Without previews the notification must be short enough to read immediately."""
        text = generate_fix_pr_notification(
            fix_pr_number=55,
            fix_pr_url="https://github.com/org/repo/pull/55",
            safety_score=85.0,
            vuln_count=2,
            vuln_types=["sqli", "xss"],
        )
        assert len(text) < 600, (
            f"Notification too long ({len(text)} chars) — should be skim-readable in seconds"
        )


# ---------------------------------------------------------------------------
# Step 5: Warn-mode comment — correct Railo branding and idempotency
# ---------------------------------------------------------------------------

class TestWarnComment:
    def test_no_fixpoint_branding_in_source(self):
        from core.pr_comments import create_warn_comment
        src = inspect.getsource(create_warn_comment)
        assert "Fixpoint" not in src, (
            "create_warn_comment must not reference 'Fixpoint' — use 'Railo'"
        )

    def test_idempotency_sentinel_uses_railo(self):
        from core.pr_comments import create_warn_comment
        src = inspect.getsource(create_warn_comment)
        # The body text that is checked for idempotency should key on "Railo"
        assert '"Railo"' in src or "'Railo'" in src, (
            "Idempotency check should use 'Railo' as sentinel, not 'Fixpoint'"
        )

    def test_error_comment_no_fixpoint_branding(self):
        from core.pr_comments import create_error_comment
        src = inspect.getsource(create_error_comment)
        assert "Fixpoint" not in src, (
            "create_error_comment must not reference 'Fixpoint'"
        )


# ---------------------------------------------------------------------------
# Vuln label mapping — what developers read in comments
# ---------------------------------------------------------------------------

class TestVulnLabelMapping:
    @pytest.mark.parametrize("check_id,expected", [
        ("python.django.security.injection.tainted-sql-string", "SQL Injection"),
        ("javascript.browser.security.xss.innerhtml",           "XSS"),
        ("generic.secrets.security.hardcoded-password",         "Hardcoded Secret"),
        ("python.lang.security.audit.subprocess-shell-true",    "Command Injection"),
        ("python.lang.security.audit.path-traversal",           "Path Traversal"),
        ("python.requests.security.ssrf-requests",              "SSRF"),
        ("python.lang.security.audit.eval-detected",            "Dangerous eval"),
        ("some.unknown.rule.id",                                 "Security Issue"),
    ])
    def test_fix_pr_label(self, check_id, expected):
        assert _vuln_label(check_id) == expected

    @pytest.mark.parametrize("check_id,expected", [
        ("python.django.security.injection.tainted-sql-string", "SQL Injection"),
        ("javascript.browser.security.xss.innerhtml",           "XSS"),
        ("generic.secrets.security.hardcoded-password",         "Hardcoded Secret"),
        ("python.lang.security.audit.subprocess-shell-true",    "Command Injection"),
        ("some.unknown.rule.id",                                 "Security Issue"),
    ])
    def test_pr_comment_label(self, check_id, expected):
        assert pr_vuln_label(check_id) == expected


# ---------------------------------------------------------------------------
# Confidence and scoring helpers
# ---------------------------------------------------------------------------

class TestConfidenceHelpers:
    def test_extract_high_string(self, sqli_finding):
        c = _extract_confidence(sqli_finding)
        assert c is not None and c >= 80.0, f"'high' should map to >=80, got {c}"

    def test_extract_medium_string(self, xss_finding):
        c = _extract_confidence(xss_finding)
        assert c is not None and 50.0 <= c <= 80.0, f"'medium' should be 50-80, got {c}"

    def test_extract_numeric_probability(self):
        finding = {"extra": {"metadata": {"probability": 0.92}}}
        c = _extract_confidence(finding)
        assert c == pytest.approx(92.0), f"0.92 should normalise to 92.0, got {c}"

    def test_extract_missing_returns_none(self):
        assert _extract_confidence({}) is None
        assert _extract_confidence({"extra": {}}) is None
        assert _extract_confidence({"extra": {"metadata": {}}}) is None

    def test_confidence_bar_full(self):
        bar = _confidence_bar(100.0)
        assert "100%" in bar
        assert "█" * 10 in bar

    def test_confidence_bar_empty(self):
        bar = _confidence_bar(0.0)
        assert "0%" in bar
        assert "░" * 10 in bar

    def test_confidence_bar_half(self):
        bar = _confidence_bar(50.0)
        assert "50%" in bar
        assert "█" in bar and "░" in bar


class TestScoring:
    def test_safety_score_in_valid_range(self, two_findings):
        s = estimate_fix_safety(two_findings)
        assert 0.0 <= s <= 100.0

    def test_confidence_score_in_valid_range(self, two_findings):
        c = estimate_fix_confidence(two_findings)
        assert 0.0 <= c <= 100.0

    def test_high_confidence_findings_score_high(self):
        findings = [
            {"extra": {"metadata": {"confidence": "high"}}},
            {"extra": {"metadata": {"confidence": "high"}}},
        ]
        c = estimate_fix_confidence(findings)
        assert c >= 80.0, f"All-high confidence findings should score >=80, got {c}"

    def test_empty_findings_returns_zero(self):
        assert estimate_fix_safety([]) == 0.0
        assert estimate_fix_confidence([]) == 0.0


# ---------------------------------------------------------------------------
# End-to-end: the full magic-moment checklist in one test
# ---------------------------------------------------------------------------

class TestMagicMomentEndToEnd:
    """
    Simulates every artifact Railo produces for a developer:
    branch name → fix PR title → fix PR body → original PR notification.
    All must be clear, Railo-branded, and skimmable in under 20 seconds.
    """

    def test_complete_flow_checklist(self, sqli_finding, sample_previews):
        findings = [sqli_finding]
        pr_number = 42
        pr_url = "https://github.com/org/repo/pull/42"
        fix_pr_url = "https://github.com/org/repo/pull/99"

        # 1. Branch name
        branch = generate_fix_branch_name(findings, original_pr_number=pr_number)
        assert "railo/" in branch, "Branch must be in railo/ namespace"
        assert "pr42" in branch, "Branch must reference source PR"
        assert len(branch) <= 80, "Branch name must be short"

        # 2. Fix PR title + body
        title, body = build_fix_pr_metadata(
            findings, pr_number, pr_url, "alice", 85.0,
            previews=sample_previews, confidence=90.0
        )
        assert title.startswith("Railo:"), "Title must start with 'Railo:'"
        assert "42" in title, "Title must reference source PR"
        assert "issue(s)" not in title, "Title must use natural English"
        assert "Before:" in body, "Body must show before/after"
        assert "After:" in body
        assert "SQL Injection" in body, "Body must use human-readable vuln label"
        assert "python.django.security" not in body, "Raw check_id must not leak into body"
        assert "85" in body, "Safety score must be in body"
        assert "90" in body, "Confidence must be in body"
        assert "railo-fix" in body, "Idempotency sentinel must be present"
        assert "Fixpoint" not in body, "Old branding must not appear"

        # 3. Original PR notification
        notification = generate_fix_pr_notification(
            fix_pr_number=99,
            fix_pr_url=fix_pr_url,
            safety_score=85.0,
            vuln_count=1,
            vuln_types=["sqli"],
            findings=findings,
            previews=sample_previews,
        )
        assert "pull/99" in notification, "Notification must link to fix PR"
        assert "Railo" in notification, "Notification must be Railo-branded"
        assert "Fixpoint" not in notification, "Old branding must not appear"
        assert "Before:" in notification, "Notification must show before/after when previews given"
        assert "85" in notification, "Notification must show safety score"
        lowered = notification.lower()
        assert "not modified" in lowered or "unchanged" in lowered or "untouched" in lowered, (
            "Notification must reassure dev their branch is untouched"
        )
