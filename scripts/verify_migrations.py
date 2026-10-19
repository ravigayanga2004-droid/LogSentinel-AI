"""Verify a clean migration and schema drift in a disposable SQLite database."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="logsentinel-migration-") as directory:
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{Path(directory).as_posix()}/clean.db",
        "ENVIRONMENT": "development",
    }
    for arguments in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(
            [sys.executable, "-m", "alembic", *arguments], cwd=root, env=environment, check=True
        )
print("Clean upgrade, schema check, downgrade and re-upgrade passed.")
