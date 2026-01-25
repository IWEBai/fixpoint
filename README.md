# Fixpoint by IWEB

**Auto-fix security vulnerabilities in your PRs.**

Fixpoint automatically detects and fixes security vulnerabilities in your pull requests, reducing time-to-merge from days to minutes.

[![Tests](https://img.shields.io/badge/tests-119%20passed-brightgreen)](https://github.com/IWEBai/fixpoint)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Marketplace](https://img.shields.io/badge/GitHub-Marketplace-blue)](https://github.com/marketplace/actions/fixpoint-auto-fix-security-vulnerabilities)

> **Try it now!** Fork the [demo repository](https://github.com/IWEBai/fixpoint-demo) to see Fixpoint in action.

---

## What It Fixes

| Vulnerability | Detection | Auto-Fix |
|---------------|-----------|----------|
| **SQL Injection** | f-strings, concatenation, `.format()`, `%` formatting | ✅ Parameterized queries |
| **Hardcoded Secrets** | Passwords, API keys, tokens, database URIs | ✅ `os.environ.get()` |
| **XSS (Templates)** | `\|safe` filter, `autoescape off` | ✅ Removes unsafe patterns |
| **XSS (Python)** | `mark_safe()`, `SafeString()` | ✅ Replaces with `escape()` |

**Philosophy:** Deterministic-first. Same input → same output. No AI hallucinations.

---

## Quick Start

Add to `.github/workflows/fixpoint.yml`:

```yaml
name: Fixpoint

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  statuses: write

jobs:
  fixpoint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
          fetch-depth: 0

      - name: Fixpoint
        uses: IWEBai/fixpoint@v1
        with:
          mode: warn  # Start with warn, graduate to enforce
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**That's it.** Fixpoint will scan every PR for vulnerabilities.

---

## Example Fixes

### SQL Injection

```python
# Before (vulnerable)
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)

# After (auto-fixed)
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))
```

### Hardcoded Secrets

```python
# Before (vulnerable)
api_key = "sk_live_abc123def456"

# After (auto-fixed)
api_key = os.environ.get("API_KEY")
```

### XSS in Templates

```html
<!-- Before (vulnerable) -->
<p>{{ user_input|safe }}</p>

<!-- After (auto-fixed) -->
<p>{{ user_input }}</p>
```

### XSS in Python

```python
# Before (vulnerable)
return mark_safe(user_input)

# After (auto-fixed)
return escape(user_input)
```

---

## Modes

### Warn Mode (Default)

```yaml
mode: warn
```

- Posts PR comments with proposed fixes
- Sets status check to **FAIL**
- No commits made
- Perfect for building trust

### Enforce Mode

```yaml
mode: enforce
```

- Applies fixes automatically
- Commits to PR branch
- Sets status check to **PASS**
- For trusted, production use

**Recommended:** Start with `warn` mode, review the fixes, then graduate to `enforce`.

---

## Status Checks

Fixpoint sets GitHub status checks (`fixpoint/compliance`):

| Status | Meaning |
|--------|---------|
| ✅ **PASS** | No vulnerabilities found |
| ❌ **FAIL** | Vulnerabilities found (warn mode) |
| ✅ **PASS** | Vulnerabilities fixed (enforce mode) |

### Block Merges on Failure

1. Go to **Settings → Branches → Branch protection rules**
2. Enable **"Require status checks to pass before merging"**
3. Select: `fixpoint/compliance`
4. Save

Now PRs with security issues can't be merged until fixed.

---

## Ignore Files

Create `.fixpointignore` in your repo root:

```bash
# .fixpointignore
tests/
test_*.py
migrations/
third_party/
*.test.py
```

---

## Detection Details

### SQL Injection (Python)

Detects unsafe SQL construction patterns:

| Pattern | Example |
|---------|---------|
| f-strings | `f"SELECT * WHERE id = {id}"` |
| Concatenation | `"SELECT * WHERE id = " + id` |
| `.format()` | `"SELECT {}".format(id)` |
| `%` formatting | `"SELECT %s" % id` |

Supports variable names: `query`, `sql`, `stmt`, `command`, etc.
Supports cursor names: `cursor`, `cur`, `db`, `conn`, `c`, etc.

### Hardcoded Secrets

Detects secrets in code:

| Type | Examples |
|------|----------|
| AWS Keys | `AKIA...` pattern |
| GitHub Tokens | `ghp_...`, `gho_...` |
| Slack Tokens | `xoxb-...` |
| Stripe Keys | `sk_live_...` |
| Database URIs | `postgres://user:pass@...` |
| Generic | `password = "..."`, `api_key = "..."` |

### XSS (Cross-Site Scripting)

**In Templates (Jinja2/Django):**
- `{{ variable|safe }}` - The `|safe` filter
- `{% autoescape off %}` - Disabled escaping

**In Python:**
- `mark_safe(variable)` - Django mark_safe
- `SafeString(variable)` - Django SafeString
- `Markup(variable)` - Flask/Jinja2 Markup

---

## CLI Usage

```bash
# Install
pip install -r requirements.txt
pip install semgrep  # Linux/Mac only

# Warn mode
python main.py /path/to/repo --warn-mode

# Enforce mode
python main.py /path/to/repo

# PR diff mode
python main.py /path/to/repo --pr-mode --base-ref main --head-ref feature
```

---

## Self-Hosted Webhook

For on-premise deployments:

```bash
# Configure
cp .env.example .env
# Edit .env with your settings

# Run
python webhook_server.py
```

Configure GitHub webhook:
- **URL:** `https://your-domain.com/webhook`
- **Events:** `pull_request` (opened, synchronize)
- **Secret:** Your `WEBHOOK_SECRET`

See [API Reference](./docs/API_REFERENCE.md) for details.

---

## What It Does NOT Do

- ❌ Fix arbitrary bugs
- ❌ Refactor code
- ❌ Auto-merge PRs
- ❌ Generate creative fixes
- ❌ Use AI/LLMs

**Only deterministic, verifiable, compliance-safe changes.**

---

## Requirements

- Python 3.12+
- GitHub repository
- GitHub Actions (or self-hosted webhook)

---

## Documentation

- [Demo Repository](https://github.com/IWEBai/fixpoint-demo) - Try Fixpoint with vulnerable code examples
- [Introduction](./docs/INTRODUCTION.md) - Why Fixpoint?
- [Getting Started](./docs/GETTING_STARTED.md) - Complete setup guide
- [API Reference](./docs/API_REFERENCE.md) - Webhook API
- [Environment Variables](./docs/ENVIRONMENT_VARIABLES.md) - Configuration
- [Roadmap](./ROADMAP.md) - What's next

---

## License

MIT License - See [LICENSE](./LICENSE) for details.

---

## Support

- **Issues:** [GitHub Issues](https://github.com/IWEBai/fixpoint/issues)
- **Discussions:** [GitHub Discussions](https://github.com/IWEBai/fixpoint/discussions)

---

*Fixpoint by IWEB — Because security shouldn't slow you down.*
