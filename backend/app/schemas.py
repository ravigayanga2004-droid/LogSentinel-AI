from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

RoleName = Literal["administrator", "analyst", "viewer", "source_admin"]
Severity = Literal["critical", "high", "medium", "low", "info"]
RuleKind = Literal["failed_login", "success_after_failures", "http_401", "http_403", "error_spike", "volume_spike", "sensitive_path", "new_entity", "many_users", "many_sources", "unusual_process", "source_silence", "parser_failure", "out_of_hours", "severity_spike", "statistical"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SetupInput(LoginInput):
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    workspace: str = Field(default="My workspace", min_length=1, max_length=100)


class ForgotInput(Input):
    email: EmailStr


class ResetInput(Input):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=12, max_length=128)


class SourceInput(Input):
    name: str = Field(min_length=1, max_length=100)
    type: Literal["linux_auth", "web", "application", "database", "firewall", "cloud", "custom"] = "application"
    parser: Literal["auto", "json", "linux_auth", "nginx", "apache", "key_value", "generic", "windows"] = "auto"
    description: str = Field(default="", max_length=2000)
    host: str = Field(default="", max_length=100)
    environment: str = Field(default="production", max_length=30)
    enabled: bool = True
    silence_minutes: int = Field(default=60, ge=1, le=10080)


class ParserInput(Input):
    text: str = Field(min_length=1, max_length=65536)
    parser: str = Field(default="auto", max_length=30)


class RuleInput(Input):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    kind: RuleKind = "failed_login"
    enabled: bool = True
    severity: Severity = "high"
    threshold: int = Field(default=5, ge=1, le=100000)
    window_minutes: int = Field(default=5, ge=1, le=10080)
    cooldown_minutes: int = Field(default=30, ge=1, le=10080)
    group_by: Literal["source_ip_hash", "username_hash", "service", "source_id"] = "source_ip_hash"
    config: dict = Field(default_factory=dict)


class AlertUpdate(Input):
    status: Literal["NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE", "SUPPRESSED", "REOPENED"] | None = None
    severity: Severity | None = None
    assignee_id: str | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    resolution_reason: str | None = Field(default=None, max_length=2000)
    suppression_minutes: int | None = Field(default=None, ge=1, le=43200)


class NoteInput(Input):
    body: str = Field(min_length=1, max_length=5000)
    evidence: list[str] = Field(default_factory=list, max_length=100)


class UserInput(Input):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: RoleName = "viewer"


class MemberUpdate(Input):
    role: RoleName


class ProfileInput(Input):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="UTC", max_length=64)


class PasswordInput(Input):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)


class NameInput(Input):
    name: str = Field(min_length=1, max_length=100)


class PolicyInput(Input):
    event_retention_days: int = Field(default=30, ge=1, le=3650)
    alert_retention_days: int = Field(default=180, ge=1, le=3650)
    audit_retention_days: int = Field(default=365, ge=30, le=3650)
    privacy_mode: bool = True
    masks: list[str] = Field(default_factory=list, max_length=50)
    exports_enabled: bool = True
    duplicate_window_minutes: int = Field(default=60, ge=1, le=1440)


class ReportInput(Input):
    title: str = Field(default="Security investigation report", min_length=1, max_length=100)
    format: Literal["csv", "json"] = "json"
    filters: dict = Field(default_factory=dict)


class SearchInput(Input):
    name: str = Field(min_length=1, max_length=100)
    filters: dict = Field(default_factory=dict)


class BatchInput(Input):
    events: list[dict] = Field(min_length=1, max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=100)
