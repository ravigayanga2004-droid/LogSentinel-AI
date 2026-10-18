import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

Json = JSON().with_variant(JSONB, "postgresql")


def uid() -> str:
    return str(uuid.uuid4())


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scoped(Identity):
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)


class Workspace(Identity, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(100))
    settings: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Member(Base):
    __tablename__ = "workspace_members"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))


class AuthSession(Identity, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ResetToken(Identity, Base):
    __tablename__ = "password_reset_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Source(Scoped, Base):
    __tablename__ = "log_sources"
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30), default="application")
    parser: Mapped[str] = mapped_column(String(30), default="auto")
    description: Mapped[str] = mapped_column(Text, default="")
    host: Mapped[str] = mapped_column(String(100), default="")
    environment: Mapped[str] = mapped_column(String(30), default="production")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    silence_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_parse_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class APIKey(Scoped, Base):
    __tablename__ = "api_keys"
    source_id: Mapped[str] = mapped_column(ForeignKey("log_sources.id"))
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(12))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Scoped, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)
    kind: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("log_sources.id"))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    error: Mapped[str | None] = mapped_column(String(200))


class Event(Scoped, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source_id", "fingerprint", "dedup_bucket"),
        Index("ix_events_workspace_time", "workspace_id", "timestamp"),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("log_sources.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    dedup_bucket: Mapped[int] = mapped_column(Integer)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    source_host: Mapped[str] = mapped_column(String(100), default="")
    service: Mapped[str] = mapped_column(String(100), default="", index=True)
    username_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_ip_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, index=True)
    url_path: Mapped[str] = mapped_column(String(1000), default="")
    http_method: Mapped[str] = mapped_column(String(16), default="")
    outcome: Mapped[str] = mapped_column(String(30), default="unknown")
    parser_name: Mapped[str] = mapped_column(String(40))
    parser_version: Mapped[str] = mapped_column(String(10), default="1.0")
    parse_status: Mapped[str] = mapped_column(String(20), default="parsed", index=True)
    anomaly_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)


class Rule(Scoped, Base):
    __tablename__ = "detection_rules"
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    severity: Mapped[str] = mapped_column(String(20), default="high")
    threshold: Mapped[int] = mapped_column(Integer, default=5)
    window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=30)
    group_by: Mapped[str] = mapped_column(String(30), default="source_ip_hash")
    config: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Baseline(Scoped, Base):
    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("source_id", "feature"),)
    source_id: Mapped[str] = mapped_column(ForeignKey("log_sources.id"))
    feature: Mapped[str] = mapped_column(String(40), default="events_per_5m")
    stats: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Alert(Scoped, Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("workspace_id", "dedup_key"),)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("detection_rules.id"))
    rule_version: Mapped[int] = mapped_column(Integer, default=1)
    source_id: Mapped[str] = mapped_column(ForeignKey("log_sources.id"))
    dedup_key: Mapped[str] = mapped_column(String(64))
    explanation: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_count: Mapped[int] = mapped_column(Integer)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    tags: Mapped[list[str]] = mapped_column(Json, default=list)
    resolution_reason: Mapped[str] = mapped_column(Text, default="")
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)


class Note(Scoped, Base):
    __tablename__ = "alert_notes"
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[str]] = mapped_column(Json, default=list)


class SavedSearch(Scoped, Base):
    __tablename__ = "saved_searches"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    filters: Mapped[dict[str, Any]] = mapped_column(Json)


class Report(Scoped, Base):
    __tablename__ = "reports"
    title: Mapped[str] = mapped_column(String(100))
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    format: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    filters: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    content: Mapped[str] = mapped_column(Text, default="")


class Audit(Scoped, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    details: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)


class Notification(Scoped, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    link: Mapped[str] = mapped_column(String(200), default="/alerts")
    read_by: Mapped[list[str]] = mapped_column(Json, default=list)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
