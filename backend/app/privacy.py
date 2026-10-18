import re
from typing import Any
from urllib.parse import urlsplit

from app.security import entity_hash

SENSITIVE = re.compile(r"password|passwd|secret|token|cookie|authorization|api.?key|credential|session.?id|email|ssn|personal", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
SECRET_VALUE = re.compile(r'''(?i)(["']?(?:password|passwd|secret|token|api[_-]?key|cookie|authorization|session[_-]?id)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|(?:Bearer\s+)?[^\s,;}&]+)''')
BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;\"']+")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(r"(?<!\w)(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:.]{0,39}(?!\w)")


def redact_text(value: str, privacy: bool = True, masks: list[str] | None = None) -> str:
    value = SECRET_VALUE.sub(lambda m: m[1] + "[REDACTED]", str(value))
    value = BEARER.sub("Bearer [REDACTED]", value)
    value = EMAIL.sub("[EMAIL]", value)
    if privacy:
        value = IPV4.sub("[IP]", value)
        value = IPV6.sub("[IP]", value)
    # Literal field values only: administrators cannot introduce regex denial of service.
    for mask in masks or []:
        if mask:
            value = value.replace(mask, "[MASKED]")
    return value[:16000]


def redact_sensitive_fields(value: Any, privacy: bool = True, masks: list[str] | None = None) -> Any:
    if isinstance(value, dict):
        return {str(k)[:100]: "[REDACTED]" if SENSITIVE.search(str(k)) else redact_sensitive_fields(v, privacy, masks) for k, v in list(value.items())[:100]}
    if isinstance(value, list):
        return [redact_sensitive_fields(v, privacy, masks) for v in value[:100]]
    if isinstance(value, str):
        return redact_text(value, privacy, masks)
    return value


def safe_path(value: str) -> str:
    # Query strings and fragments can contain arbitrary credentials; never store them.
    try:
        return redact_text(urlsplit(value).path)[:1000]
    except ValueError:
        return "[INVALID PATH]"


def safe_cell(value: Any) -> str:
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def redact_event(parsed: dict, masks: list[str] | None = None, privacy: bool = True) -> dict:
    original = dict(parsed)
    cleaned = redact_sensitive_fields(parsed, privacy, masks)
    cleaned["username_hash"] = entity_hash(str(original.get("username", "")))
    cleaned["source_ip_hash"] = entity_hash(str(original.get("source_ip", "")))
    cleaned.pop("username", None)
    cleaned.pop("source_ip", None)
    cleaned["url_path"] = safe_path(str(original.get("url_path", "")))
    # Structured user names may also appear embedded in a human readable message.
    username = str(original.get("username", ""))
    if username and len(username) >= 2:
        cleaned = redact_sensitive_fields(cleaned, privacy, [*(masks or []), username])
    return cleaned
