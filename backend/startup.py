"""Validated container startup for migrations, optional demo data, and the API."""

from __future__ import annotations

import os
import subprocess
import sys

from .settings import get_settings


def main() -> None:
    """Validate configuration before changing the database or starting the API."""

    settings = get_settings()
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    if settings.seed_demo_data:
        subprocess.run([sys.executable, "-m", "backend.seed"], check=True)
    os.execvp(
        "uvicorn",
        ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
