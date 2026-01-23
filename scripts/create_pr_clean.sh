#!/bin/bash
# Create PR B: Clean Code (PASS)

set -e

REPO_NAME="autopatcher-demo-python"
BRANCH="feature/add-safe-user-lookup"

echo "Creating PR B: Clean Code (PASS)"

cd "$REPO_NAME" || { echo "Error: Demo repo not found. Run scripts/create_demo_repo.sh first"; exit 1; }

# Make sure we're on main
git checkout main
git pull origin main

# Create branch
git checkout -b "$BRANCH"

# Add safe code (parameterized query)
cat > app.py << 'EOF'
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Safe parameterized query
    query = "SELECT * FROM users WHERE email = ?"
    cursor.execute(query, (email,))
    
    return cursor.fetchone()
EOF

git add app.py
git commit -m "Add safe user lookup function"
git push origin "$BRANCH"

# Create PR
PR_URL=$(gh pr create --title "Add safe user lookup" --body "Adds safe user lookup function" --json url --jq .url)

echo "✅ PR B created: $PR_URL"
echo ""
echo "Expected result:"
echo "- ✅ Status check shows PASS (auditshield/compliance)"
echo "- ✅ No comments (no violations)"
echo "- ✅ Merge allowed"
echo ""
echo "Update README.md with this PR link:"
echo "Replace: https://github.com/zariffromlatif/autopatcher-demo-python/pull/2"
echo "With: $PR_URL"
