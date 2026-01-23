#!/bin/bash
# Create PR A: Violation (FAIL + Comment)

set -e

REPO_NAME="autopatcher-demo-python"
BRANCH="feature/add-user-lookup"

echo "Creating PR A: Violation (FAIL + Comment)"

cd "$REPO_NAME" || { echo "Error: Demo repo not found. Run scripts/create_demo_repo.sh first"; exit 1; }

# Create branch
git checkout -b "$BRANCH"

# Add vulnerable code (SQL injection)
cat > app.py << 'EOF'
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    
    return cursor.fetchone()
EOF

git add app.py
git commit -m "Add user lookup function"
git push origin "$BRANCH"

# Create PR
PR_URL=$(gh pr create --title "Add user lookup" --body "Adds user lookup function" --json url --jq .url)

echo "✅ PR A created: $PR_URL"
echo ""
echo "Expected result:"
echo "- ✅ AuditShield posts comment with proposed fix (diff preview)"
echo "- ✅ Status check shows FAIL (auditshield/compliance)"
echo "- ✅ Merge blocked (if required check configured)"
echo ""
echo "Update README.md with this PR link:"
echo "Replace: https://github.com/zariffromlatif/autopatcher-demo-python/pull/1"
echo "With: $PR_URL"
