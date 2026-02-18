"""
Isolation and sandboxing primitives for Fixpoint (design placeholder).

Future work will move execution of scan/fix jobs into isolated
containers or sandboxed environments. This module documents the
intended responsibilities and provides a small interface that callers
can build against without enforcing any particular runtime today.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, ContextManager
from contextlib import contextmanager


@dataclass
class IsolationConfig:
    """
    Configuration for an isolated execution environment.

    This is deliberately minimal; concrete implementations may extend
    it with container image names, resource limits, etc.
    """

    enabled: bool = False
    workdir: Optional[Path] = None
    extra_env: Optional[Dict[str, str]] = None


@contextmanager
def isolated_workspace(
    repo_path: Path,
    config: Optional[IsolationConfig] = None,
) -> ContextManager[Path]:
    """
    Context manager that yields a workspace path suitable for running
    scans / fixes in isolation.

    Today this is a thin wrapper that simply yields `repo_path`
    unchanged when isolation is disabled. In future, this may:
    - Create a throwaway container with a bind-mounted repo.
    - Clone the repo into a sandbox directory with restricted perms.
    """
    _cfg = config or IsolationConfig(enabled=False)
    # For now, we simply yield the original path. The interface is here
    # so that future callers can opt in to sandboxing without changing
    # their control flow.
    try:
        yield Path(repo_path)
    finally:
        # Placeholder for future cleanup logic (e.g. deleting temp dirs,
        # stopping containers). No-op for now.
        return

