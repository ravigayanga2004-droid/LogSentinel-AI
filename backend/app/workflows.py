from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.common import Context, require_workspace_access, serialize
from app.db import utcnow
from app.detection import evaluate_rule
from app.models import (
    Alert,
    AlertEvent,
    Audit,
    Baseline,
    Event,
    Job,
    Member,
    Note,
    Notification,
    Rule,
    Source,
)
from app.privacy import redact_text
from app.resources import page
from app.schemas import AlertUpdate, NoteInput, RuleInput

router = APIRouter(prefix="/api", tags=["Detection and investigations"])


def validate_rule_config(config: dict):
    fields = {
        "source_ids",
        "service",
        "paths",
        "excluded_ip_hashes",
        "excluded_user_hashes",
        "expected_processes",
        "start_hour",
        "end_hour",
    }
    if config.keys() - fields:
        raise HTTPException(422, "Unsupported rule configuration field")
    for key, value in config.items():
        if key in {"start_hour", "end_hour"}:
            if not isinstance(value, int) or not 0 <= value <= 24:
                raise HTTPException(422, "Hours must be integers between 0 and 24 (UTC)")
        elif key == "service":
            if not isinstance(value, str) or len(value) > 100:
                raise HTTPException(422, "Service must be a short string")
        elif (
            not isinstance(value, list)
            or len(value) > 100
            or not all(isinstance(item, str) and 0 < len(item) <= 200 for item in value)
        ):
            raise HTTPException(422, "Rule lists must contain at most 100 short, nonempty strings")
    if config.get("start_hour", 6) >= config.get("end_hour", 22):
        raise HTTPException(422, "End hour must follow start hour")


@router.get("/rules")
def rules(ctx: Context = Depends(require_workspace_access)):
    return {
        "items": [
            serialize(rule)
            for rule in ctx.db.scalars(
                select(Rule).where(Rule.workspace_id == ctx.wid).order_by(Rule.name)
            )
        ]
    }


@router.post("/rules", status_code=201)
def add_rule(data: RuleInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("rules")
    validate_rule_config(data.config)
    for source_id in data.config.get("source_ids", []):
        ctx.get(Source, source_id)
    rule = Rule(workspace_id=ctx.wid, updated_by=ctx.user.id, **data.model_dump())
    ctx.db.add(rule)
    ctx.db.flush()
    ctx.audit("rule.created", "rule", rule.id)
    return serialize(rule)


@router.get("/rules/{rule_id}")
def get_rule(rule_id: str, ctx: Context = Depends(require_workspace_access)):
    return serialize(ctx.get(Rule, rule_id))


@router.put("/rules/{rule_id}")
def edit_rule(rule_id: str, data: RuleInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("rules")
    validate_rule_config(data.config)
    for source_id in data.config.get("source_ids", []):
        ctx.get(Source, source_id)
    rule = ctx.get(Rule, rule_id)
    for key, value in data.model_dump().items():
        setattr(rule, key, value)
    rule.version += 1
    rule.updated_by = ctx.user.id
    ctx.audit("rule.updated", "rule", rule.id, {"version": rule.version})
    return serialize(rule)


@router.post("/rules/{rule_id}/test")
def test_rule(rule_id: str, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("rules")
    rule = ctx.get(Rule, rule_id)
    matches: list[dict] = []
    for source in ctx.db.scalars(select(Source).where(Source.workspace_id == ctx.wid)):
        if rule.config.get("source_ids") and source.id not in rule.config["source_ids"]:
            continue
        matches.extend(
            {"source": source.name, **match} for match in evaluate_rule(ctx.db, rule, source)
        )
    return {"test_only": True, "matches": matches}


@router.post("/detection/run", status_code=202)
def detect(ctx: Context = Depends(require_workspace_access)):
    ctx.permit("rules")
    job = Job(workspace_id=ctx.wid, actor_id=ctx.user.id, kind="detection", payload={})
    ctx.db.add(job)
    ctx.db.flush()
    ctx.audit("detection.queued", "job", job.id)
    return serialize(job)


@router.post("/baselines/{baseline_id}/reset")
def reset_baseline(baseline_id: str, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("rules")
    row = ctx.get(Baseline, baseline_id)
    row.stats = {"trusted": False, "samples": 0, "reset_at": utcnow().isoformat()}
    row.version += 1
    ctx.audit("baseline.reset", "baseline", row.id)
    return serialize(row)


@router.get("/alerts")
def alerts(
    q: str = Query("", max_length=200),
    severity: str = "",
    status: str = "",
    source_id: str = "",
    assignee_id: str = "",
    hours: float = Query(168, gt=0, le=8760),
    page_number: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    ctx: Context = Depends(require_workspace_access),
):
    query = select(Alert).where(
        Alert.workspace_id == ctx.wid, Alert.created_at >= utcnow() - timedelta(hours=hours)
    )
    if q:
        query = query.where(Alert.title.ilike(f"%{q}%"))
    for key, value in {
        "severity": severity,
        "status": status,
        "source_id": source_id,
        "assignee_id": assignee_id,
    }.items():
        if value:
            query = query.where(getattr(Alert, key) == value)
    return page(ctx.db, query.order_by(Alert.created_at.desc()), page_number, page_size)


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: str, ctx: Context = Depends(require_workspace_access)):
    alert = ctx.get(Alert, alert_id)
    evidence = ctx.db.scalars(
        select(Event)
        .join(AlertEvent, Event.id == AlertEvent.event_id)
        .where(AlertEvent.alert_id == alert.id, Event.workspace_id == ctx.wid)
        .order_by(Event.timestamp)
        .limit(100)
    )
    notes = ctx.db.scalars(
        select(Note)
        .where(Note.alert_id == alert.id, Note.workspace_id == ctx.wid)
        .order_by(Note.created_at)
    )
    history = ctx.db.scalars(
        select(Audit)
        .where(Audit.workspace_id == ctx.wid, Audit.entity_id == alert.id)
        .order_by(Audit.created_at)
        .limit(200)
    )
    similar = ctx.db.scalars(
        select(Alert)
        .where(Alert.workspace_id == ctx.wid, Alert.rule_id == alert.rule_id, Alert.id != alert.id)
        .order_by(Alert.created_at.desc())
        .limit(5)
    )
    return {
        **serialize(alert),
        "events": [serialize(row) for row in evidence],
        "notes": [serialize(row) for row in notes],
        "history": [serialize(row) for row in history],
        "similar": [serialize(row) for row in similar],
    }


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: str, data: AlertUpdate, ctx: Context = Depends(require_workspace_access)
):
    ctx.permit("investigate")
    alert = ctx.get(Alert, alert_id)
    values = data.model_dump(exclude_unset=True)
    if (
        "assignee_id" in values
        and values["assignee_id"]
        and not ctx.db.get(Member, (ctx.wid, values["assignee_id"]))
    ):
        raise HTTPException(422, "Assignee must belong to this workspace")
    status = values.get("status")
    if status in {"RESOLVED", "FALSE_POSITIVE"} and not (
        values.get("resolution_reason") or alert.resolution_reason
    ):
        raise HTTPException(422, "A resolution reason is required")
    if status == "SUPPRESSED":
        if not data.suppression_minutes:
            raise HTTPException(422, "Suppression requires an expiration")
        alert.suppressed_until = utcnow() + timedelta(minutes=data.suppression_minutes)
    elif status:
        alert.suppressed_until = None
    if status in {"RESOLVED", "FALSE_POSITIVE"}:
        alert.resolved_at = utcnow()
    elif status:
        alert.resolved_at = None
    for key, value in values.items():
        if key == "suppression_minutes":
            continue
        if key in {"status", "severity", "tags", "resolution_reason"} and value is None:
            raise HTTPException(422, "This field cannot be null")
        if key == "tags":
            value = [redact_text(item)[:40] for item in value]
        if key == "resolution_reason":
            value = redact_text(value)
        setattr(alert, key, value)
    ctx.audit("alert.updated", "alert", alert.id, {"fields": list(values), "status": alert.status})
    ctx.db.add(
        Notification(
            workspace_id=ctx.wid,
            user_id=alert.assignee_id,
            title=f"Alert updated: {alert.title}",
            link=f"/alerts/{alert.id}",
        )
    )
    return serialize(alert)


@router.post("/alerts/{alert_id}/notes", status_code=201)
def add_note(alert_id: str, data: NoteInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("investigate")
    alert = ctx.get(Alert, alert_id)
    for event_id in data.evidence:
        ctx.get(Event, event_id)
    note = Note(
        workspace_id=ctx.wid,
        alert_id=alert.id,
        author_id=ctx.user.id,
        body=redact_text(data.body, masks=ctx.workspace.settings.get("masks", [])),
        evidence=data.evidence,
    )
    ctx.db.add(note)
    ctx.db.flush()
    ctx.audit("alert.note_added", "alert", alert.id)
    return serialize(note)


@router.get("/notifications")
def notifications(
    page_number: int = Query(1, ge=1), ctx: Context = Depends(require_workspace_access)
):
    from sqlalchemy import or_

    return page(
        ctx.db,
        select(Notification)
        .where(
            Notification.workspace_id == ctx.wid,
            or_(Notification.user_id == ctx.user.id, Notification.user_id.is_(None)),
        )
        .order_by(Notification.created_at.desc()),
        page_number,
    )


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str, ctx: Context = Depends(require_workspace_access)):
    notification = ctx.get(Notification, notification_id)
    if notification.user_id and notification.user_id != ctx.user.id:
        raise HTTPException(404, "Notification not found")
    notification.read_by = list(set([*notification.read_by, ctx.user.id]))
    return serialize(notification)
