"""Cross-platform project commands; uses the workspace virtual environment when present."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    interpreter = str(PYTHON) if PYTHON.exists() else sys.executable
    commands = {
        "dev": [
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        "start": [
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
            "--no-server-header",
        ],
        "test": ["-m", "pytest"],
        "lint": ["-m", "ruff", "check", "backend", "scripts"],
        "format": ["-m", "ruff", "format", "backend", "scripts"],
        "typecheck": ["-m", "mypy", "backend/app"],
        "db:migrate": ["-m", "alembic", "revision", "--autogenerate"],
        "db:upgrade": ["-m", "alembic", "upgrade", "head"],
        "db:seed": ["-m", "app.cli", "seed"],
        "worker": ["-m", "app.worker"],
    }
    name = sys.argv[1] if len(sys.argv) > 1 else "help"
    if name == "test:watch":
        from watchfiles import watch

        subprocess.run([interpreter, "-m", "pytest", *sys.argv[2:]], cwd=ROOT, check=False)
        for _ in watch(ROOT / "backend"):
            subprocess.run([interpreter, "-m", "pytest", *sys.argv[2:]], cwd=ROOT, check=False)
        return
    if name not in commands:
        print(
            "Usage: python scripts/manage.py COMMAND [arguments]\nCommands: "
            + ", ".join([*commands, "test:watch"])
        )
        raise SystemExit(0 if name == "help" else 2)
    raise SystemExit(
        subprocess.run(
            [interpreter, *commands[name], *sys.argv[2:]], cwd=ROOT, check=False
        ).returncode
    )


if __name__ == "__main__":
    main()
