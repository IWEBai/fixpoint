# Changelog

All notable changes to Fixpoint will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-02-08

### Added

- **Phase 3A — Command Injection, Path Traversal, SSRF**
  - **Command injection**: Converts `os.system(cmd)` and `subprocess.run(cmd, shell=True)` to safe `subprocess.run(shlex.split(cmd), shell=False)`.
  - **Path traversal**: Adds path validation when `os.path.join(base, user_var)` is used; ensures resolved path is under base directory.
  - **SSRF**: Detection for `requests.get/post` and `urlopen` with dynamic URLs; guidance in comments (deterministic fix deferred to config-driven approach).

- **Phase 3B — JavaScript/TypeScript support**
  - **eval**: Detection for dangerous `eval()` usage; guidance in warn comments.
  - **Hardcoded secrets**: Replaces `apiKey = "xxx"` with `process.env.API_KEY`.
  - **DOM XSS**: Replaces `innerHTML =` with `textContent =` for user-controlled content.
  - Semgrep rules: `javascript_eval.yaml`, `javascript_secrets.yaml`, `javascript_dom_xss.yaml`.
  - Scanner and entrypoint now include `.js`, `.ts`, `.jsx`, `.tsx` files.

- **Safety rails** (formalized)
  - Max-diff threshold: Reject commits when diff exceeds `max_diff_lines` (default 500). Configurable via `.fixpoint.yml` or `FIXPOINT_MAX_DIFF_LINES`.
  - Optional test run before commit: When `test_before_commit` is enabled, runs `test_command` (default `pytest`) before committing. Skips commit if tests fail.
  - CWE/OWASP tags in PR comments: Findings now display CWE and OWASP identifiers in warn and fix comments (e.g. `CWE-89 | A03:2021`).

### Changed

- GitHub Action: New inputs `max_diff_lines`, `test_before_commit`, `test_command` for safety rail configuration.

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
| 1.1.0 | 2026-02-08 | Phase 3A/3B, safety rails, JS/TS support |
| 1.0.0 | 2026-01-25 | Initial release |

---

[Unreleased]: https://github.com/IWEBai/fixpoint/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/IWEBai/fixpoint/releases/tag/v1.1.0
[1.0.0]: https://github.com/IWEBai/fixpoint/releases/tag/v1.0.0
