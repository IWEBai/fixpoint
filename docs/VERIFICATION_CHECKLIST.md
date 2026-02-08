# Fixpoint Verification Checklist

Use this checklist before releasing or after major changes to ensure the core flow works.

---

## 1. Test Suite

```bash
python -m pytest tests/ -v --tb=short
```

- [ ] **133 passed** (2 skipped on Windows for Semgrep)
- [ ] No unexpected failures

---

## 2. GitHub Action (CI)

- [ ] Push to a branch and open a PR
- [ ] CI workflow runs (see `.github/workflows/ci.yml`)
- [ ] Lint and tests pass in GitHub Actions

---

## 3. End-to-End Flow (Demo Repo)

**Warn mode:**

1. [ ] Fork [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo)
2. [ ] Add Fixpoint workflow to `.github/workflows/fixpoint.yml` (see README)
3. [ ] Open a PR with vulnerable code (e.g. SQL injection, hardcoded secret)
4. [ ] Fixpoint runs and posts a comment with proposed fixes
5. [ ] Status check `fixpoint/compliance` shows FAIL

**Enforce mode:**

1. [ ] Change `mode: enforce` in the workflow
2. [ ] Open a PR with vulnerable code
3. [ ] Fixpoint commits the fix to the PR branch
4. [ ] Status check `fixpoint/compliance` shows PASS
5. [ ] PR shows a new commit: `[fixpoint] fix: Apply compliance fixes`

---

## 4. Fixer Coverage (Quick Smoke Test)

| Fixer | Test file | Expected |
|-------|-----------|----------|
| SQL injection | `tests/test_fix_sqli.py` | PASS |
| Secrets | `tests/test_secrets.py` | PASS |
| XSS | `tests/test_xss.py` | PASS |
| Command injection | `tests/test_command_injection.py` | PASS |
| Path traversal | `tests/test_path_traversal.py` | PASS |
| JavaScript | `tests/test_javascript.py` | PASS |

---

## 5. CLI Mode

```bash
# Warn mode
python main.py /path/to/repo --warn-mode

# Enforce mode (creates branch and PR)
python main.py /path/to/repo
```

- [ ] Warn mode prints proposed fixes
- [ ] Enforce mode applies fixes and creates branch/PR (or pushes to existing)

---

## 6. Webhook Server (Optional)

```bash
python webhook_server.py
```

- [ ] Server starts on configured PORT
- [ ] `/health` returns 200
- [ ] Valid webhook payload triggers processing (requires GitHub webhook setup)

---

## Pre-Release Sign-Off

- [ ] All tests pass
- [ ] CHANGELOG updated
- [ ] Tag created: `git tag -a v1.1.0 -m "Release v1.1.0"`
- [ ] Push and push tags: `git push && git push --tags`

---

*Last updated: February 2026*
