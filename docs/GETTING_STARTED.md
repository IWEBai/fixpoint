# Getting Started with AuditShield

This guide walks you through setting up and using AuditShield.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Options](#installation-options)
3. [GitHub Action Setup](#github-action-setup)
4. [Webhook Server Setup](#webhook-server-setup)
5. [Demo Repository Setup](#demo-repository-setup)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Version | Check Command | Install Link |
|----------|---------|---------------|--------------|
| Python | 3.11+ | `python --version` | https://python.org |
| Git | 2.30+ | `git --version` | https://git-scm.com |
| GitHub CLI | Latest | `gh --version` | https://cli.github.com |

### GitHub CLI Authentication

**You must authenticate before running any `gh` commands:**

```bash
gh auth login
```

Follow the prompts:
1. Choose: `GitHub.com`
2. Choose: `HTTPS`
3. Choose: `Login with a web browser`
4. Press Enter, copy the code, paste in browser
5. Authorize GitHub CLI

**Verify authentication:**
```bash
gh auth status
# Should show: ✓ Logged in to github.com as [your-username]
```

---

## Installation Options

### Option A: GitHub Action (Recommended)

Add AuditShield to your repository with zero infrastructure.

**Create `.github/workflows/auditshield.yml`:**

```yaml
name: AuditShield

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  statuses: write

jobs:
  auditshield:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
          fetch-depth: 0

      - name: AuditShield
        uses: zariffromlatif/auditshield@v0.1.0
        with:
          mode: warn  # or "enforce" for auto-fix
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**That's it!** AuditShield will run on every PR.

### Option B: Self-Hosted Webhook Server

For organizations that need self-hosted deployments.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/zariffromlatif/auditshield.git
   cd auditshield
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Start the server:**
   ```bash
   python webhook_server.py
   ```

5. **Configure GitHub webhook:**
   - URL: `https://your-domain.com/webhook`
   - Content type: `application/json`
   - Secret: Your `WEBHOOK_SECRET`
   - Events: Pull requests

See [Environment Variables](./ENVIRONMENT_VARIABLES.md) for configuration options.

### Option C: CLI Usage

For local testing and one-off scans.

```bash
# Clone and install
git clone https://github.com/zariffromlatif/auditshield.git
cd auditshield
pip install -r requirements.txt

# Scan a repository (warn mode)
python main.py /path/to/repo --warn-mode

# Scan and fix (enforce mode)
python main.py /path/to/repo

# Scan PR diff only
python main.py /path/to/repo --pr-mode --base-ref main --head-ref feature-branch
```

---

## GitHub Action Setup

### Step 1: Add Workflow File

Create `.github/workflows/auditshield.yml` in your repository (see above).

### Step 2: Choose Mode

**Warn Mode (default):**
- Posts comments with suggested fixes
- Sets status check to FAIL
- Does NOT modify code

**Enforce Mode:**
- Automatically applies fixes
- Commits to PR branch
- Sets status check to PASS

Start with `warn` mode to review fixes, then switch to `enforce` once you trust them.

### Step 3: Configure Branch Protection (Optional)

To block merges until violations are fixed:

1. Go to **Settings → Branches → Branch protection rules**
2. Click **Add rule**
3. Branch name pattern: `main`
4. Enable **"Require status checks to pass before merging"**
5. Search and select: `auditshield/compliance`
6. Save

---

## Webhook Server Setup

### Configuration

Create `.env` file:

```bash
# Required
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
WEBHOOK_SECRET=your_secret_here

# Mode
AUDITSHIELD_MODE=warn
ENVIRONMENT=production

# Server
PORT=8000
DEBUG=false
```

See [Environment Variables](./ENVIRONMENT_VARIABLES.md) for all options.

### Docker Deployment

```bash
docker build -t auditshield .
docker run -p 8000:8000 --env-file .env auditshield
```

### Verify Deployment

```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

---

## Demo Repository Setup

To test AuditShield with sample PRs:

### Automated Setup (Windows PowerShell)

```powershell
cd path\to\auditshield

# Set up demo repo
.\scripts\setup_demo.ps1

# Create PR with violation (FAIL)
.\scripts\create_pr_violation.ps1

# Create PR with clean code (PASS)
.\scripts\create_pr_clean.ps1
```

### Automated Setup (Linux/Mac)

```bash
cd path/to/auditshield

chmod +x scripts/*.sh
./scripts/create_demo_repo.sh
./scripts/create_pr_violation.sh
./scripts/create_pr_clean.sh
```

### Manual Setup

1. Create a new repository
2. Add the AuditShield workflow file
3. Create a PR with vulnerable code:
   ```python
   query = f"SELECT * FROM users WHERE email = '{email}'"
   cursor.execute(query)
   ```
4. Create a PR with safe code:
   ```python
   query = "SELECT * FROM users WHERE email = %s"
   cursor.execute(query, (email,))
   ```

---

## Verification

### Check PR with Violation

- [ ] AuditShield workflow runs
- [ ] Comment posted with fix proposal
- [ ] Status check shows **FAIL** (`auditshield/compliance`)
- [ ] Merge blocked (if branch protection configured)

### Check PR with Clean Code

- [ ] AuditShield workflow runs
- [ ] Status check shows **PASS**
- [ ] No comments (no violations)
- [ ] Merge allowed

### Test Enforce Mode

1. Change workflow: `mode: enforce`
2. Push commit to PR with violation
3. Bot commits fix automatically
4. Status changes to **PASS**

---

## Troubleshooting

### "To get started with GitHub CLI, please run: gh auth login"

**Solution:** Authenticate GitHub CLI first:
```bash
gh auth login
```

### "Command not found: gh"

**Solution:** Install GitHub CLI from https://cli.github.com/

### "Script cannot find path"

**Solution:** Run scripts from the main AuditShield directory:
```bash
cd path/to/auditshield  # NOT from inside demo repo
.\scripts\create_pr_violation.ps1
```

### "Script execution is disabled" (Windows)

**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "Repository already exists"

**Solution:** Delete and recreate:
```bash
gh repo delete owner/repo --yes
# Then run setup script again
```

### Webhook returns 401

**Causes:**
- Invalid signature (check `WEBHOOK_SECRET` matches)
- Missing `GITHUB_TOKEN`
- Repository not in allowlist

**Debug:** Check server logs for specific error message.

### No status check appearing

**Causes:**
- Workflow not triggered (check workflow file)
- Permissions missing (need `statuses: write`)
- Workflow failed (check Actions tab)

---

## Next Steps

- [API Reference](./API_REFERENCE.md) - Webhook API documentation
- [Environment Variables](./ENVIRONMENT_VARIABLES.md) - Configuration reference
- [ROADMAP](../ROADMAP.md) - Upcoming features
- [Production Checklist](../PRODUCTION_CHECKLIST.md) - Deployment preparation

---

## Support

- **Issues:** [GitHub Issues](https://github.com/zariffromlatif/auditshield/issues)
- **Documentation:** This guide and linked references
