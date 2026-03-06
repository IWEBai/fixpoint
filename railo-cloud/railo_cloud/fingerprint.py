from __future__ import annotations

import hashlib


def compute_run_fingerprint(
    *,
    repo_owner: str,
    repo_name: str,
    base_ref: str | None,
    head_ref: str | None,
    head_sha: str | None,
    engine_mode: str | None,
    fixpoint_mode: str | None,
    max_runtime_seconds: int | None,
    artifact_root: str | None,
    engine_version: str | None = None,
) -> str:
    """Return a stable hex fingerprint for a run configuration.

    The fingerprint is purely deterministic over inputs and intended for
    idempotency/deduplication. It does *not* include payload contents.
    """

    normalized = {
        "repo": f"{repo_owner}/{repo_name}".lower(),
        "base": (base_ref or "").strip(),
        "head": (head_ref or "").strip(),
        "sha": (head_sha or "").strip(),
        "engine_mode": (engine_mode or "").strip(),
        "fixpoint_mode": (fixpoint_mode or "").strip(),
        "max_runtime": str(max_runtime_seconds) if max_runtime_seconds is not None else "",
        "artifact_root": (artifact_root or "").strip(),
        "engine_version": (engine_version or "").strip(),
    }

    seed = "\n".join(f"{k}={v}" for k, v in sorted(normalized.items()))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()
