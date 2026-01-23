# Release Notes

## v0.1.0 - Warn-First Release (2026-01-23)

**First stable release with warn mode, status checks, and GitHub Action support.**

### Features

- ✅ **Warn Mode** - Propose fixes in PR comments without auto-committing
- ✅ **Status Check Semantics** - PASS/FAIL gates in GitHub PR checks
- ✅ **AST-Based Fixer** - Handles any variable name (not just `{email}`)
- ✅ **.auditshieldignore** - Exclude files/directories from scanning
- ✅ **GitHub Action** - Easy CI/CD integration (composite action)
- ✅ **PR Diff Scanning** - Only scans changed files, not entire repo
- ✅ **Idempotency & Loop Prevention** - Safe for production use
- ✅ **Webhook Security** - Signature verification, rate limiting

### Installation

Add to your `.github/workflows/auditshield.yml`:

```yaml
name: AuditShield
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  auditshield:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      statuses: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: your-org/auditshield@v0.1.0
        with:
          mode: warn  # Start in warn mode
          base_branch: main
```

### Breaking Changes

None (first release)

### Migration Guide

N/A (first release)

### Known Issues

- In-memory stores (idempotency/rate limiting) lost on restart (use Redis in production)
- Python only (JavaScript/TypeScript support coming in v0.2.0)
- SQL injection fixes only (more violation types coming)

### What's Next

- v0.1.1 - Bug fixes and patches
- v0.2.0 - Multi-language support (JavaScript, TypeScript)
- v0.3.0 - More violation types (PII logging, secrets)
