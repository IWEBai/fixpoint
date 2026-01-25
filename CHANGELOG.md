# Changelog

All notable changes to Fixpoint will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-01-25

### Added

- **SQL Injection Auto-Fix**: Automatically converts unsafe SQL queries to parameterized queries
  - Supports f-strings: `f"SELECT * WHERE id = {id}"`
  - Supports concatenation: `"SELECT * WHERE id = " + id`
  - Supports `.format()`: `"SELECT {}".format(id)`
  - Supports `%` formatting: `"SELECT %s" % id`

- **Hardcoded Secrets Auto-Fix**: Replaces hardcoded secrets with `os.environ.get()`
  - Detects passwords, API keys, tokens
  - Detects AWS keys, GitHub tokens, Slack tokens, Stripe keys
  - Detects database connection strings

- **XSS Auto-Fix**: Removes unsafe patterns in templates and Python code
  - Removes `|safe` filter in Jinja2/Django templates
  - Removes `{% autoescape off %}` blocks
  - Replaces `mark_safe()` with `escape()`
  - Replaces `SafeString()` with `escape()`

- **GitHub Action**: Zero-configuration GitHub Action
  - `warn` mode: Comments with proposed fixes
  - `enforce` mode: Automatically applies fixes
  - Status checks: `fixpoint/compliance` pass/fail

- **Webhook Server**: Self-hosted option for on-premise deployments
  - Signature verification
  - Replay protection
  - Rate limiting
  - Repository allowlist/denylist

- **CLI Tool**: Local scanning and fixing
  - Full repo scan mode
  - PR diff mode
  - Warn and enforce modes

- **Ignore File**: `.fixpointignore` for excluding files/directories

- **Documentation**: Complete documentation
  - Getting Started guide
  - API Reference
  - Environment Variables reference

### Security

- HMAC-SHA256 webhook signature verification
- Replay attack protection via delivery ID tracking
- Rate limiting to prevent abuse
- Repository allowlist/denylist support
- No token embedding in URLs

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0.0 | 2026-01-25 | Initial release |

---

[Unreleased]: https://github.com/IWEBai/fixpoint/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/IWEBai/fixpoint/releases/tag/v1.0.0
