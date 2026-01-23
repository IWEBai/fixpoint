# PowerShell script to set up demo repository for AuditShield

$REPO_NAME = "autopatcher-demo-python"
$GITHUB_USER = "zariffromlatif"

Write-Host "Creating demo repository: $REPO_NAME" -ForegroundColor Green

# Check if repo already exists
$repoExists = gh repo view "$GITHUB_USER/$REPO_NAME" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Repository already exists on GitHub. Cloning..." -ForegroundColor Yellow
    if (Test-Path $REPO_NAME) {
        Write-Host "Local directory already exists. Removing..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $REPO_NAME
    }
    gh repo clone "$GITHUB_USER/$REPO_NAME"
} else {
    # Create new repository
    Write-Host "Creating new repository..." -ForegroundColor Green
    gh repo create $REPO_NAME --public --clone
}

Set-Location $REPO_NAME

# Create initial README
@"
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

- [AuditShield Documentation](https://github.com/$GITHUB_USER/auditshield)
- [Installation Guide](https://github.com/$GITHUB_USER/auditshield#install)
"@ | Out-File -FilePath README.md -Encoding utf8

# Create workflow directory
New-Item -ItemType Directory -Force -Path .github\workflows | Out-Null

# Create AuditShield workflow
@"
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
          ref: `${{ github.head_ref }}
          fetch-depth: 0

      - name: AuditShield (warn-first)
        uses: $GITHUB_USER/auditshield@v0.1.0
        with:
          mode: warn
          base_branch: `${{ github.base_ref }}
        env:
          GITHUB_TOKEN: `${{ secrets.GITHUB_TOKEN }}
"@ | Out-File -FilePath .github\workflows\auditshield.yml -Encoding utf8

# Create initial main branch file
@"
# Demo repository for AuditShield
# This file will be modified in PRs to demonstrate violations and fixes
"@ | Out-File -FilePath app.py -Encoding utf8

# Commit and push initial setup
git add .
git commit -m "Initial commit: AuditShield demo repository"
git push origin main

Write-Host "`n✅ Demo repository created: https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Run scripts/create_pr_violation.ps1 to create PR A"
Write-Host "2. Run scripts/create_pr_clean.ps1 to create PR B"
Write-Host "3. Configure required check in GitHub Settings → Branches"
