"""Check tracked files against local deployment secrets without printing secret values."""

import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")  # noqa: S607 -- fixed local Git command
secrets = []
for filename in (".env", ".env.docker"):
    path = root / filename
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key in {"SECRET_KEY", "POSTGRES_PASSWORD", "SMTP_PASSWORD"} and len(value) >= 16:
                    secrets.append(value.encode())
violations = []
for filename in filter(None, tracked):
    if filename in {".env", ".env.docker"}:
        violations.append(filename)
        continue
    data = (root / filename).read_bytes()
    if any(value in data for value in secrets) or re.search(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}", data
    ):
        violations.append(filename)
if violations:
    raise SystemExit("Secret-like material found in tracked paths: " + ", ".join(violations))
print(
    f"Checked {len(list(filter(None, tracked)))} tracked files: no local deployment secrets or private-key/token signatures found."
)
