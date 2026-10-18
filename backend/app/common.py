from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Audit, AuthSession, Member, User, Workspace
from app.privacy import redact_sensitive_fields
from app.security import digest, is_expired, require_permission

HIDDEN = {"password_hash", "token_hash", "csrf_hash", "payload", "content", "dedup_key"}


def serialize(obj) -> dict[str, Any]:
    result = {}
    for column in inspect(obj).mapper.column_attrs:
        if column.key in HIDDEN:
            continue
        value = getattr(obj, column.key)
        if isinstance(value, datetime):
            from app.db import aware
            value = aware(value).isoformat()
        result[column.key] = value
    return result


def create_audit_log(db: Session, workspace_id: str, actor_id: str | None, action: str, entity_type: str, entity_id: str = "", details: dict | None = None):
    db.add(Audit(workspace_id=workspace_id, actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, details=redact_sensitive_fields(details or {})))


def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get("ls_session", "")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(raw))) if raw else None
    if not session or is_expired(session.expires_at):
        raise HTTPException(401, "Please sign in to continue")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Please sign in to continue")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        import hmac
        if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(403, "Security token missing or expired. Refresh and try again.")
    request.state.session = session
    return user


class Context:
    def __init__(self, db: Session, user: User, member: Member, workspace: Workspace):
        self.db, self.user, self.member, self.workspace = db, user, member, workspace
        self.wid = workspace.id

    def permit(self, permission: str):
        require_permission(self.member.role, permission)

    def get(self, model, resource_id: str):
        resource = self.db.scalar(select(model).where(model.id == resource_id, model.workspace_id == self.wid))
        if not resource:
            raise HTTPException(404, "Resource not found in this workspace")
        return resource

    def audit(self, action: str, model: str, entity_id: str = "", details: dict | None = None):
        create_audit_log(self.db, self.wid, self.user.id, action, model, entity_id, details)


def require_workspace_access(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)) -> Context:
    wid = request.headers.get("x-workspace-id")
    query = select(Member).where(Member.user_id == user.id)
    if wid:
        query = query.where(Member.workspace_id == wid)
    member = db.scalar(query.order_by(Member.workspace_id))
    if not member:
        raise HTTPException(403, "Workspace access denied")
    workspace = db.get(Workspace, member.workspace_id)
    if not workspace:
        raise HTTPException(403, "Workspace access denied")
    return Context(db, user, member, workspace)
