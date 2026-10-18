from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select

from app.common import Context, create_audit_log, require_workspace_access, serialize
from app.db import utcnow
from app.detection import seed_rules
from app.models import (
    Alert,
    Audit,
    Event,
    Job,
    Member,
    Note,
    Notification,
    Report,
    User,
    Workspace,
)
from app.resources import page
from app.schemas import MemberUpdate, NameInput, PolicyInput, UserInput
from app.security import hash_password

router = APIRouter(prefix="/api", tags=["Workspace administration"])


@router.get("/members")
def members(ctx: Context = Depends(require_workspace_access)):
    rows = ctx.db.execute(
        select(User, Member.role)
        .join(Member, User.id == Member.user_id)
        .where(Member.workspace_id == ctx.wid)
        .order_by(User.name)
    )
    return {
        "items": [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email if ctx.member.role == "administrator" else "",
                "role": role,
                "active": user.active,
            }
            for user, role in rows
        ]
    }


@router.post("/members", status_code=201)
def add_member(data: UserInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    if ctx.db.scalar(select(User).where(User.email == str(data.email).lower())):
        raise HTTPException(
            409,
            "This account already exists; use the administrator CLI to grant membership with identity verification",
        )
    user = User(
        name=data.name, email=str(data.email).lower(), password_hash=hash_password(data.password)
    )
    ctx.db.add(user)
    ctx.db.flush()
    ctx.db.add(Member(workspace_id=ctx.wid, user_id=user.id, role=data.role))
    ctx.audit("member.created", "user", user.id, {"role": data.role})
    return {"id": user.id, "name": user.name, "email": user.email, "role": data.role}


@router.patch("/members/{user_id}")
def change_role(user_id: str, data: MemberUpdate, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    ctx.db.scalar(select(Workspace).where(Workspace.id == ctx.wid).with_for_update())
    member = ctx.db.get(Member, (ctx.wid, user_id))
    if not member:
        raise HTTPException(404, "Member not found")
    if member.role == "administrator" and data.role != "administrator":
        admins = (
            ctx.db.scalar(
                select(func.count())
                .select_from(Member)
                .where(Member.workspace_id == ctx.wid, Member.role == "administrator")
            )
            or 0
        )
        if admins < 2:
            raise HTTPException(409, "Keep at least one workspace administrator")
    member.role = data.role
    ctx.audit("member.role_changed", "user", user_id, {"role": data.role})
    return {"id": user_id, "role": member.role}


@router.post("/workspaces", status_code=201)
def create_workspace(data: NameInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    workspace = Workspace(name=data.name, settings={})
    ctx.db.add(workspace)
    ctx.db.flush()
    ctx.db.add(Member(workspace_id=workspace.id, user_id=ctx.user.id, role="administrator"))
    seed_rules(ctx.db, workspace.id, ctx.user.id)
    create_audit_log(
        ctx.db, workspace.id, ctx.user.id, "workspace.created", "workspace", workspace.id
    )
    return serialize(workspace)


@router.get("/settings")
def settings(ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    return {
        "workspace": serialize(ctx.workspace),
        "policy": PolicyInput(**ctx.workspace.settings).model_dump(),
        "raw_storage_enabled": False,
        "outbound_integrations_enabled": False,
    }


@router.put("/settings")
def update_settings(data: PolicyInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    if any(len(value) > 200 for value in data.masks):
        raise HTTPException(422, "Mask values must contain at most 200 characters")
    ctx.workspace.settings = data.model_dump()
    ctx.audit("policy.updated", "workspace", ctx.wid)
    return {"policy": ctx.workspace.settings}


def retention_counts(db, workspace):
    policy = PolicyInput(**workspace.settings)
    now = utcnow()
    return {
        "events": db.scalar(
            select(func.count())
            .select_from(Event)
            .where(
                Event.workspace_id == workspace.id,
                Event.timestamp < now - timedelta(days=policy.event_retention_days),
            )
        )
        or 0,
        "alerts": db.scalar(
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.workspace_id == workspace.id,
                Alert.updated_at < now - timedelta(days=policy.alert_retention_days),
                Alert.status.in_(["RESOLVED", "FALSE_POSITIVE"]),
            )
        )
        or 0,
        "audit_logs": db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(
                Audit.workspace_id == workspace.id,
                Audit.created_at < now - timedelta(days=policy.audit_retention_days),
            )
        )
        or 0,
    }


@router.get("/retention/preview")
def preview_retention(ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    return {
        "counts": retention_counts(ctx.db, ctx.workspace),
        "policy": PolicyInput(**ctx.workspace.settings).model_dump(),
    }


@router.post("/retention/run", status_code=202)
def run_retention(ctx: Context = Depends(require_workspace_access)):
    ctx.permit("admin")
    job = Job(workspace_id=ctx.wid, actor_id=ctx.user.id, kind="retention", payload={})
    ctx.db.add(job)
    ctx.db.flush()
    ctx.audit("retention.queued", "job", job.id)
    return serialize(job)


def apply_retention(db, job):
    workspace = db.get(Workspace, job.workspace_id)
    counts = retention_counts(db, workspace)
    policy = PolicyInput(**workspace.settings)
    now = utcnow()
    db.execute(
        delete(Event).where(
            Event.workspace_id == workspace.id,
            Event.timestamp < now - timedelta(days=policy.event_retention_days),
        )
    )
    stale_alerts = select(Alert.id).where(
        Alert.workspace_id == workspace.id,
        Alert.updated_at < now - timedelta(days=policy.alert_retention_days),
        Alert.status.in_(["RESOLVED", "FALSE_POSITIVE"]),
    )
    db.execute(
        delete(Note).where(Note.workspace_id == workspace.id, Note.alert_id.in_(stale_alerts))
    )
    db.execute(delete(Alert).where(Alert.id.in_(stale_alerts)))
    db.execute(
        delete(Audit).where(
            Audit.workspace_id == workspace.id,
            Audit.created_at < now - timedelta(days=policy.audit_retention_days),
        )
    )
    # Report content is a second copy of event data; expire it with event retention.
    db.execute(
        delete(Report).where(
            Report.workspace_id == workspace.id,
            Report.created_at < now - timedelta(days=policy.event_retention_days),
        )
    )
    db.execute(
        delete(Notification).where(
            Notification.workspace_id == workspace.id,
            Notification.created_at < now - timedelta(days=policy.event_retention_days),
        )
    )
    job.result = counts
    create_audit_log(db, workspace.id, job.actor_id, "retention.completed", "job", job.id, counts)


@router.get("/audit")
def audit(
    q: str = Query("", max_length=100),
    page_number: int = Query(1, ge=1),
    ctx: Context = Depends(require_workspace_access),
):
    ctx.permit("audit")
    query = select(Audit).where(Audit.workspace_id == ctx.wid)
    if q:
        query = query.where(Audit.action.ilike(f"%{q}%"))
    return page(ctx.db, query.order_by(Audit.created_at.desc()), page_number)
