# Installing Fixpoint as a GitHub App

Install Fixpoint on your GitHub organization or personal account with one click.

## Direct Install

**[Install Fixpoint](https://github.com/apps/fixpoint-security/installations/new)**

1. Click the link above.
2. Choose which repositories to install (all repos, or select specific ones).
3. Authorize the app.

That's it. Fixpoint will start scanning pull requests in the repositories you selected.

## Permissions

Fixpoint requests:

| Permission | Purpose |
|------------|---------|
| **Contents** (read/write) | Clone repos, apply fixes, push commits |
| **Pull requests** (read/write) | Post comments, read PR diffs |
| **Statuses** (read/write) | Set compliance status checks |

## What Happens After Install

- When you open or update a pull request, Fixpoint scans changed files for vulnerabilities.
- In **warn mode** (default): Fixpoint posts comments with proposed fixes.
- In **enforce mode**: Fixpoint applies fixes and commits automatically.

## Free Beta

Fixpoint is free during the beta. No billing, no credit card required.

## Support

Questions? [support@fixpoint.dev](mailto:support@fixpoint.dev)
