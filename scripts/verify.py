"""Authoritative local/CI quality verification entrypoint.

Runs the same checks in one place so local and CI validation stay aligned:
1) Ruff lint on source + tests + scripts
2) Pytest suite
3) FastAPI startup/import sanity
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_step(name: str, command: list[str], env: dict[str, str]) -> None:
    print(f"\n==> {name}")
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", ".")
    env.setdefault("DATABASE_URL", "sqlite:///./.quality_gate.db")

    python = sys.executable

    _run_step("Lint (ruff)", [python, "-m", "ruff", "check", "src", "tests", "scripts"], env)
    _run_step("Tests (pytest)", [python, "-m", "pytest", "-q"], env)
    _run_step(
        "Startup sanity (app import/create)",
        [python, "-c", "from src.app import create_app; create_app(); print('startup-ok')"],
        env,
    )

    print("\n✅ Quality verification passed.")


if __name__ == "__main__":
    main()
