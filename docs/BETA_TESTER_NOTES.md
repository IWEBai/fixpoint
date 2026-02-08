# Fixpoint v1.1.0 — Beta Tester Notes

Thank you for testing Fixpoint. These notes help you try the release and tell us what's working and what isn't.

---

## What's New in v1.1.0

### Python

| Feature | Description |
|---------|-------------|
| **Command Injection** | Converts `os.system(cmd)` and `subprocess` with `shell=True` to safe list-based subprocess |
| **Path Traversal** | Adds path validation for `os.path.join(base, user_input)` |
| **SSRF** | Detects `requests.get/post` and `urlopen` with dynamic URLs; guidance in comments (no auto-fix yet) |

### JavaScript/TypeScript

| Feature | Description |
|---------|-------------|
| **eval** | Detects dangerous `eval()` usage; guidance in warn comments (no auto-fix) |
| **Hardcoded Secrets** | Replaces `apiKey = "xxx"` with `process.env.API_KEY` |
| **DOM XSS** | Replaces `innerHTML =` with `textContent =` |

### Safety Rails

- **Max-diff limit:** Skips commit if changes exceed `max_diff_lines` (default 500)
- **Test before commit:** Optional run of `test_command` (e.g. `pytest`) before committing
- **CWE/OWASP tags:** Each finding shows CWE and OWASP identifiers in PR comments

---

## How to Try It

### 1. GitHub Action (recommended)

1. Add the [workflow](../../README.md#quick-start) to `.github/workflows/fixpoint.yml`
2. Use `mode: warn` first
3. Open a PR with vulnerable code (e.g. SQL injection, hardcoded secret)
4. Fixpoint will post a comment with proposed fixes
5. Switch to `mode: enforce` when you're comfortable with the fixes

### 2. Demo Repo

1. Fork [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo)
2. Add the Fixpoint workflow
3. Open a PR with vulnerable code
4. Confirm the comment and (in enforce mode) auto-fix behavior

### 3. CLI (Linux/Mac)

```bash
pip install -r requirements.txt
pip install semgrep  # Required for scanning

# Warn mode
python main.py /path/to/repo --warn-mode

# Enforce mode
python main.py /path/to/repo
```

Note: Semgrep is not supported on Windows.

---

## Known Limitations

| Limitation | Workaround |
|------------|------------|
| **Windows CLI** | Semgrep not supported; use GitHub Action or WSL |
| **SSRF / eval** | Detection only; no auto-fix yet - guidance in comments |
| **Some JS patterns** | Regex-based; may miss edge cases |
| **Fork PRs** | Enforce mode downgraded to warn (no write access to forks) |

---

## What We're Looking For

### Bugs

- Fixes that change behavior unexpectedly
- Incorrect or missing fixes
- Crashes or errors in CI/CLI/webhook

### UX

- Unclear PR comments
- Confusing configuration
- Unclear what Fixpoint did or didn't do

### Features

- Missing vulnerability types
- Desired safety rails
- Integration or workflow improvements

---

## How to Give Feedback

| Type | Where |
|------|-------|
| **Bugs** | [GitHub Issues](https://github.com/IWEBai/fixpoint/issues) - include steps to reproduce, logs, and examples |
| **Questions / Ideas** | [GitHub Discussions](https://github.com/IWEBai/fixpoint/discussions) |
| **Who's using it** | [Who's using Fixpoint?](https://github.com/IWEBai/fixpoint/discussions/categories/whos-using-fixpoint) |
| **Hosted version** | [Would you pay for a hosted version?](https://github.com/IWEBai/fixpoint/discussions) - what would make it worth it? |

---

## Quick Checklist

- [ ] Ran Fixpoint on a real or demo repo
- [ ] Tested warn mode (comments only)
- [ ] Tested enforce mode (if applicable)
- [ ] Checked PR comments for clarity
- [ ] Reported any issues or awkward flows
- [ ] Optional: Shared what would make a hosted version valuable

---

*Thank you for testing Fixpoint. Your feedback helps us improve.*
