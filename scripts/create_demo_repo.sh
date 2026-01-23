#!/bin/bash
# Script to create and set up the demo repository for AuditShield

set -e

REPO_NAME="autopatcher-demo-python"
GITHUB_USER="zariffromlatif"

echo "Creating demo repository: $REPO_NAME"

# Create repository
gh repo create "$REPO_NAME" --public --clone

cd "$REPO_NAME"

# Create initial README
cat > README.md << 'EOF'
# AuditShield Demo Repository

This repository demonstrates AuditShield in action.

## What You'll See

- **PR with violation** → Warn mode comment + FAIL status check
- **PR with clean code** → PASS status check

## Try It Yourself

1. Fork this repository
2. Create a PR with SQL injection vulnerability
3. Watch AuditShield propose a fix (warn mode)
4. Switch to enforce mode to auto-apply fixes

## Learn More

- [AuditShield Documentation](https://github.com/zariffromlatif/auditshield)
- [Installation Guide](https://github.com/zariffromlatif/auditshield#install)
EOF

# Create workflow directory
mkdir -p .github/workflows

# Create AuditShield workflow
cat > .github/workflows/auditshield.yml << 'EOF'
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

      - name: AuditShield (warn-first)
        uses: zariffromlatif/auditshield@v0.1.0
        with:
          mode: warn
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
EOF

# Create initial main branch file
cat > app.py << 'EOF'
# Demo repository for AuditShield
# This file will be modified in PRs to demonstrate violations and fixes
EOF

# Commit and push initial setup
git add .
git commit -m "Initial commit: AuditShield demo repository"
git push origin main

echo "✅ Demo repository created: https://github.com/$GITHUB_USER/$REPO_NAME"
echo ""
echo "Next steps:"
echo "1. Run scripts/create_pr_violation.sh to create PR A"
echo "2. Run scripts/create_pr_clean.sh to create PR B"
echo "3. Configure required check in GitHub Settings → Branches"
