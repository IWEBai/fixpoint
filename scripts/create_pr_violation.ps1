# PowerShell script to create PR A: Violation (FAIL + Comment)

$REPO_NAME = "autopatcher-demo-python"
$BRANCH = "feature/add-user-lookup"

Write-Host "Creating PR A: Violation (FAIL + Comment)" -ForegroundColor Green

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

# Create branch
git checkout -b $BRANCH

# Add vulnerable code (SQL injection)
@"
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    
    return cursor.fetchone()
"@ | Out-File -FilePath app.py -Encoding utf8

git add app.py
git commit -m "Add user lookup function"
git push origin $BRANCH

# Create PR
$PR_OUTPUT = gh pr create --title "Add user lookup" --body "Adds user lookup function"
$PR_URL = $PR_OUTPUT | Select-String -Pattern "https://github.com/.*/pull/\d+" | ForEach-Object { $_.Matches.Value }

Write-Host "`n✅ PR A created: $PR_URL" -ForegroundColor Green
Write-Host "`nExpected result:" -ForegroundColor Yellow
Write-Host "- ✅ AuditShield posts comment with proposed fix (diff preview)"
Write-Host "- ✅ Status check shows FAIL (auditshield/compliance)"
Write-Host "- ✅ Merge blocked (if required check configured)"
Write-Host "`nUpdate README.md with this PR link:" -ForegroundColor Cyan
Write-Host "Replace: https://github.com/zariffromlatif/autopatcher-demo-python/pull/1"
Write-Host "With: $PR_URL"

# Return to original directory
Set-Location ..
