# Security Policy

## Supported versions

We release security updates for the **latest major version** of Fixpoint. Please keep your copy or Action reference up to date.

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

---

## Reporting a vulnerability

If you believe you've found a **security vulnerability** in Fixpoint (e.g. in the webhook server, auth, or code execution), please report it responsibly.

**Do not** open a public GitHub issue for security-sensitive findings.

### How to report

1. **Email:** [iwebai.space@gmail.com](mailto:iwebai.space@gmail.com) with subject `[Fixpoint Security]` and a description of the issue.
2. **Or** use [GitHub Security Advisories](https://github.com/IWEBai/fixpoint/security/advisories/new) (requires a GitHub account).

Include:

- What you did (steps to reproduce).
- What you expected vs what happened.
- Your environment (OS, Python version, how you run Fixpoint).

We'll respond as soon as we can and will work with you on a fix and disclosure timeline.

### What to expect

- We'll confirm receipt of your report.
- We'll assess the finding and may ask for more details.
- We'll work on a fix and keep you updated.
- We'll credit you in the advisory/release notes (unless you prefer to stay anonymous).

---

## Security practices in Fixpoint

- Webhook requests are verified with HMAC-SHA256.
- Replay protection via delivery ID tracking.
- No secrets in logs or URLs.
- Rate limiting to reduce abuse.

---

*Fixpoint by [IWEB](https://www.iwebai.space)*
