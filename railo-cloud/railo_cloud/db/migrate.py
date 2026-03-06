from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def _find_project_root() -> Path:
    """Locate the project root that holds alembic.ini (handles container layout)."""
    here = Path(__file__).resolve()
    candidates = [here.parents[3], here.parents[2]]  # /app and /app/railo-cloud
    for candidate in candidates:
        if (candidate / "alembic.ini").exists():
            return candidate
    raise FileNotFoundError(f"Could not find alembic.ini near {here}")


def run() -> None:
    project_root = _find_project_root()
    config_path = project_root / "alembic.ini"

    alembic_cfg = Config(str(config_path))
    # Ensure script location is explicit when invoked programmatically
    alembic_cfg.set_main_option("script_location", str(project_root / "migrations"))
    command.upgrade(alembic_cfg, "head")
    print("Applied Alembic migrations")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
