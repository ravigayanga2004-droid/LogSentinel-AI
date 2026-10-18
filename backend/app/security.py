import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import aware, utcnow
from app.models import RateBucket

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

# Permissions are explicit, version-controlled policy rather than editable database grants.
PERMISSIONS = {
    "administrator": {
        "read",
        "investigate",
        "sources",
        "ingest",
        "rules",
        "export",
        "admin",
        "audit",
    },
    "analyst": {"read", "investigate", "ingest", "rules", "export"},
    "viewer": {"read"},
    "source_admin": {"read", "sources", "ingest"},
}


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Passwords must contain 12–128 characters")
    return hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def token() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def entity_hash(value: str) -> str:
    if not value:
        return ""
    return hmac.new(
        get_settings().secret_key.encode(), value.strip().lower().encode(), hashlib.sha256
    ).hexdigest()


def require_permission(role: str, permission: str):
    if permission not in PERMISSIONS.get(role, set()):
        raise HTTPException(403, "Your workspace role does not permit this action")


def rate_limit(db: Session, key: str, limit: int, seconds: int):
    """Database backed, atomic counters shared by all API processes."""
    key = digest(key)
    now = utcnow()
    bucket = db.get(RateBucket, key)
    if not bucket:
        try:
            with db.begin_nested():
                db.add(RateBucket(key=key, count=0, expires_at=now + timedelta(seconds=seconds)))
                db.flush()
        except IntegrityError:
            pass
    db.execute(
        update(RateBucket)
        .where(RateBucket.key == key, RateBucket.expires_at <= now)
        .values(count=0, expires_at=now + timedelta(seconds=seconds))
    )
    db.execute(update(RateBucket).where(RateBucket.key == key).values(count=RateBucket.count + 1))
    count = db.scalar(select(RateBucket.count).where(RateBucket.key == key)) or 0
    # Persist failed attempts even when the route returns an authentication error.
    db.commit()
    if count > limit:
        raise HTTPException(
            429, "Too many attempts. Please try again later.", headers={"Retry-After": str(seconds)}
        )


def is_expired(value) -> bool:
    return aware(value) <= utcnow()
