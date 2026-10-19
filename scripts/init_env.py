"""Generate local secrets without overwriting any existing configuration."""

import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--docker", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
target = root / (".env.docker" if args.docker else ".env")
if target.exists():
    raise SystemExit(f"{target.name} already exists; no changes made.")
origin = "http://localhost:8080" if args.docker else "http://localhost:5173"
target.write_text(
    f"ENVIRONMENT=development\nDATABASE_URL=sqlite:///./data/development.db\nSECRET_KEY={secrets.token_hex(32)}\nCOOKIE_SECURE=false\nPUBLIC_ORIGIN={origin}\nPOSTGRES_PASSWORD={secrets.token_hex(24)}\n",
    encoding="utf-8",
)
print(f"Created {target.name} with fresh secrets. This file is excluded from Git.")
