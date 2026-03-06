# Open-Core Boundary

This note defines what remains open source (Fixpoint OSS) versus what is reserved for commercial/enterprise editions. The goal is to preserve a clean architecture boundary and avoid later churn.

## Open Source (Fixpoint OSS)

- Scanning engine and orchestrator
- Deterministic fixers (base rules)
- GitHub Action and CLI
- Baseline mode
- Safety rails
- SARIF export
- Local configuration (`.fixpoint.yml`)

These constitute the adoption engine and must remain OSS.

## Reserved for Enterprise / Private

- Organization dashboard
- Policy management UI
- Multi-repo analytics
- Compliance exports (SOC2 / ISO)
- Advanced rule packs
- Centralized exception management
- SSO / RBAC
- SaaS-hosted scanning service

These are withheld for commercial editions.

## Notes

- The core repository remains MIT-licensed. This boundary clarifies intent for future enterprise modules and SaaS packaging.
- No source-code collection is permitted; only metadata may be used for future telemetry (see threat model for privacy constraints).
