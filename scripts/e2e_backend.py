"""Isolated disposable browser-test server; never opens the development database."""

import os
import secrets
import sys
import tempfile
import threading
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))


def main():
    with tempfile.TemporaryDirectory(prefix="logsentinel-browser-") as directory:
        os.chdir(root)
        os.environ.update(
            DATABASE_URL=f"sqlite:///{Path(directory).as_posix()}/browser.db",
            ENVIRONMENT="development",
            SECRET_KEY=secrets.token_hex(32),
            PUBLIC_ORIGIN="http://127.0.0.1:5174",
            COOKIE_SECURE="false",
        )
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(root / "alembic.ini")), "head")
        from app import ingestion

        ingestion.STAGING = Path(directory) / "staging"
        from app.seed import seed

        seed()
        from app.db import engine
        from app.worker import run_once

        stop = threading.Event()

        def worker():
            while not stop.is_set():
                run_once()
                stop.wait(0.5)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        import uvicorn

        try:
            uvicorn.run(
                "app.main:app", host="127.0.0.1", port=8010, log_level="warning", access_log=False
            )
        finally:
            stop.set()
            thread.join(timeout=15)
            engine.dispose()


if __name__ == "__main__":
    main()
