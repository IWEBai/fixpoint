# Create GitHub Release for v0.1.0

## Option 1: Using GitHub CLI

```bash
gh release create v0.1.0 \
  --title "v0.1.0 - Warn-First Release" \
  --notes-file RELEASE_NOTES.md
```

## Option 2: Using GitHub Web UI

1. Go to: https://github.com/zariffromlatif/auditshield/releases/new
2. Tag: `v0.1.0`
3. Title: `v0.1.0 - Warn-First Release`
4. Description: Copy content from `RELEASE_NOTES.md`
5. Click "Publish release"

## Option 3: Using GitHub API

```bash
curl -X POST \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/zariffromlatif/auditshield/releases \
  -d @- << EOF
{
  "tag_name": "v0.1.0",
  "name": "v0.1.0 - Warn-First Release",
  "body": "$(cat RELEASE_NOTES.md | sed 's/$/\\n/' | tr -d '\n')",
  "draft": false,
  "prerelease": false
}
EOF
```
