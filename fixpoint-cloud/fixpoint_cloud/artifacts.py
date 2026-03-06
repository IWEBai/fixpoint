from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def canonical_artifact_path(path: Path, artifact_root: Path) -> str:
    """Return a safe, relative path under artifact_root.

    Falls back to the filename if the path cannot be relativized (defensive
    against paths outside the root).
    """

    try:
        rel = path.resolve().relative_to(artifact_root.resolve())
        return rel.as_posix()
    except Exception:
        return path.name


def sanitize_artifact_paths(paths: Optional[dict[str, Any]], artifact_root: Path) -> Optional[Dict[str, str]]:
    if not paths:
        return {} if paths == {} else None

    sanitized: Dict[str, str] = {}
    for key, value in paths.items():
        if value is None:
            continue
        candidate = Path(str(value))
        sanitized[key] = canonical_artifact_path(candidate, artifact_root)
    return sanitized
