# PowerShell script to create PR B: Clean Code (PASS)

$REPO_NAME = "autopatcher-demo-python"
$BRANCH = "feature/add-safe-user-lookup"

Write-Host "Creating PR B: Clean Code (PASS)" -ForegroundColor Green

# Check if repo exists locally, if not, clone it
if (-not (Test-Path $REPO_NAME)) {
    Write-Host "Demo repo not found locally. Cloning..." -ForegroundColor Yellow
    $GITHUB_USER = "zariffromlatif"
    gh repo clone "$GITHUB_USER/$REPO_NAME"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Could not clone demo repo. Run scripts/setup_demo.ps1 first" -ForegroundColor Red
        exit 1
    }
}

Set-Location $REPO_NAME

# Make sure we're on main
git checkout main
git pull origin main

# Create branch
git checkout -b $BRANCH

# Add safe code (parameterized query)
@"
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Safe parameterized query
    query = "SELECT * FROM users WHERE email = ?"
    cursor.execute(query, (email,))
    
    return cursor.fetchone()
"@ | Out-File -FilePath app.py -Encoding utf8

git add app.py
git commit -m "Add safe user lookup function"
git push origin $BRANCH

# Create PR
$PR_OUTPUT = gh pr create --title "Add safe user lookup" --body "Adds safe user lookup function"
$PR_URL = $PR_OUTPUT | Select-String -Pattern "https://github.com/.*/pull/\d+" | ForEach-Object { $_.Matches.Value }

Write-Host "`n✅ PR B created: $PR_URL" -ForegroundColor Green
Write-Host "`nExpected result:" -ForegroundColor Yellow
Write-Host "- ✅ Status check shows PASS (auditshield/compliance)"
Write-Host "- ✅ No comments (no violations)"
Write-Host "- ✅ Merge allowed"
Write-Host "`nUpdate README.md with this PR link:" -ForegroundColor Cyan
Write-Host "Replace: https://github.com/zariffromlatif/autopatcher-demo-python/pull/2"
Write-Host "With: $PR_URL"

# Return to original directory
Set-Location ..
