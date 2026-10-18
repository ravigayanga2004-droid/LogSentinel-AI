import csv
import io
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.common import Context, require_workspace_access, serialize
from app.db import aware, utcnow
from app.models import Alert, Event, Job, Note, Notification, Report, Rule, Source, Workspace
from app.privacy import redact_sensitive_fields, safe_cell
from app.resources import event_query, page, source_health
from app.schemas import ReportInput

router = APIRouter(prefix="/api", tags=["Analytics and reports"])
CLOSED = {"RESOLVED", "FALSE_POSITIVE", "SUPPRESSED"}


@router.get("/analytics")
def analytics(
    hours: float = Query(24, gt=0, le=8760),
    source_id: str = "",
    severity: str = "",
    service: str = "",
    source_host: str = "",
    event_type: str = "",
    username_hash: str = "",
    source_ip_hash: str = "",
    alert_status: str = "",
    ctx: Context = Depends(require_workspace_access),
):
    since = utcnow() - timedelta(hours=hours)
    eq = event_query(
        ctx.wid,
        {
            "hours": hours,
            "source_id": source_id,
            "severity": severity,
            "service": service,
            "source_host": source_host,
            "event_type": event_type,
            "username_hash": username_hash,
            "source_ip_hash": source_ip_hash,
        },
    )
    conditions = list(eq._where_criteria)
    aq = select(Alert).where(Alert.workspace_id == ctx.wid, Alert.created_at >= since)
    if source_id:
        aq = aq.where(Alert.source_id == source_id)
    if severity:
        aq = aq.where(Alert.severity == severity)
    if alert_status:
        aq = aq.where(Alert.status == alert_status)
    alert_conditions = list(aq._where_criteria)
    total = ctx.db.scalar(select(func.count()).select_from(Event).where(*conditions)) or 0
    anomalies = (
        ctx.db.scalar(
            select(func.count()).select_from(Event).where(*conditions, Event.anomaly_score > 0)
        )
        or 0
    )
    errors = (
        ctx.db.scalar(
            select(func.count())
            .select_from(Event)
            .where(*conditions, Event.severity.in_(["critical", "high"]))
        )
        or 0
    )
    failures = (
        ctx.db.scalar(
            select(func.count())
            .select_from(Event)
            .where(*conditions, Event.parse_status == "failed")
        )
        or 0
    )
    alert_counts: dict[str, int] = {
        str(row[0]): int(row[1])
        for row in (
            ctx.db.execute(
                select(Alert.status, func.count()).where(*alert_conditions).group_by(Alert.status)
            ).all()
        )
    }
    severity_counts: dict[str, int] = {
        str(row[0]): int(row[1])
        for row in (
            ctx.db.execute(
                select(Alert.severity, func.count())
                .where(*alert_conditions)
                .group_by(Alert.severity)
            ).all()
        )
    }
    interval = max(60, int(hours * 3600 / 48))
    epoch = (
        func.strftime("%s", Event.timestamp).cast(__import__("sqlalchemy").Integer)
        if ctx.db.get_bind().dialect.name == "sqlite"
        else func.extract("epoch", Event.timestamp)
    )
    bucket = func.floor(epoch / interval) * interval
    from sqlalchemy import case

    trend_rows = ctx.db.execute(
        select(
            bucket.label("bucket"),
            func.count(),
            func.sum(case((Event.event_type == "login_failed", 1), else_=0)),
            func.sum(case((Event.event_type == "login_success", 1), else_=0)),
            func.sum(case((Event.severity.in_(["critical", "high"]), 1), else_=0)),
        )
        .where(*conditions)
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    from datetime import UTC, datetime

    trend_map = {
        int(row[0]): {"events": row[1], "failed": row[2], "success": row[3], "errors": row[4]}
        for row in trend_rows
    }
    first_bucket, last_bucket = (
        int(since.timestamp()) // interval * interval,
        int(utcnow().timestamp()) // interval * interval,
    )
    trend = [
        {
            "time": datetime.fromtimestamp(point, UTC).isoformat(),
            **trend_map.get(point, {"events": 0, "failed": 0, "success": 0, "errors": 0}),
        }
        for point in range(first_bucket, last_bucket + 1, interval)
    ]

    def top(column):
        return [
            {"name": name or "Unknown", "value": count}
            for name, count in ctx.db.execute(
                select(column, func.count())
                .where(*conditions)
                .group_by(column)
                .order_by(func.count().desc())
                .limit(6)
            )
        ]

    source_rows = list(ctx.db.scalars(select(Source).where(Source.workspace_id == ctx.wid)))
    health = [source_health(ctx.db, source) for source in source_rows]
    recent = ctx.db.scalars(aq.order_by(Alert.created_at.desc()).limit(5))
    rule_names = {
        row.id: row.name for row in ctx.db.scalars(select(Rule).where(Rule.workspace_id == ctx.wid))
    }
    performance = [
        {
            "rule": rule_names.get(rule_id, "Archived rule"),
            "alerts": count,
            "false_positives": false_positives or 0,
        }
        for rule_id, count, false_positives in ctx.db.execute(
            select(
                Alert.rule_id,
                func.count(),
                func.sum(case((Alert.status == "FALSE_POSITIVE", 1), else_=0)),
            )
            .where(*alert_conditions)
            .group_by(Alert.rule_id)
        )
    ]
    return {
        "total_events": total,
        "events_per_minute": round(total / (hours * 60), 2),
        "open_alerts": sum(count for status, count in alert_counts.items() if status not in CLOSED),
        "high_alerts": severity_counts.get("high", 0) + severity_counts.get("critical", 0),
        "anomalies": anomalies,
        "error_rate": round(errors / max(total, 1) * 100, 2),
        "parse_failure_rate": round(failures / max(total, 1) * 100, 2),
        "trend": trend,
        "categories": top(Event.category),
        "http_status": top(Event.status_code),
        "top_users": top(Event.username_hash),
        "top_ips": top(Event.source_ip_hash),
        "top_sources": [
            {
                "name": next(
                    (source.name for source in source_rows if source.id == row["name"]), "Unknown"
                ),
                "value": row["value"],
            }
            for row in top(Event.source_id)
        ],
        "severity": [{"name": key, "value": value} for key, value in severity_counts.items()],
        "alert_status": [{"name": key, "value": value} for key, value in alert_counts.items()],
        "sources": health,
        "recent_alerts": [serialize(row) for row in recent],
        "performance": performance,
        "hours": hours,
    }


@router.get("/reports")
def reports(page_number: int = Query(1, ge=1), ctx: Context = Depends(require_workspace_access)):
    ctx.permit("export")
    return page(
        ctx.db,
        select(Report).where(Report.workspace_id == ctx.wid).order_by(Report.created_at.desc()),
        page_number,
    )


@router.post("/reports", status_code=202)
def create_report(data: ReportInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("export")
    if not ctx.workspace.settings.get("exports_enabled", True):
        raise HTTPException(403, "Exports are disabled by workspace policy")
    event_query(ctx.wid, data.filters)
    report = Report(
        workspace_id=ctx.wid,
        creator_id=ctx.user.id,
        title=data.title,
        format=data.format,
        filters=redact_sensitive_fields(data.filters),
    )
    ctx.db.add(report)
    ctx.db.flush()
    job = Job(
        workspace_id=ctx.wid, actor_id=ctx.user.id, kind="report", payload={"report_id": report.id}
    )
    ctx.db.add(job)
    ctx.audit("report.queued", "report", report.id)
    return serialize(report)


@router.get("/reports/{report_id}/download")
def download_report(report_id: str, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("export")
    if not ctx.workspace.settings.get("exports_enabled", True):
        raise HTTPException(403, "Exports are disabled by workspace policy")
    report = ctx.get(Report, report_id)
    if report.status != "completed":
        raise HTTPException(409, "Report is not ready")
    ctx.audit("report.downloaded", "report", report.id)
    return Response(
        report.content,
        media_type="text/csv" if report.format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="logsentinel-{report.id}.{report.format}"',
            "Cache-Control": "no-store",
        },
    )


def build_report(db, job):
    report = db.get(Report, job.payload["report_id"])
    if not report or report.workspace_id != job.workspace_id:
        raise ValueError("Report not found")
    workspace = db.get(Workspace, job.workspace_id)
    if not workspace.settings.get("exports_enabled", True):
        raise ValueError("Exports are disabled")
    query = event_query(job.workspace_id, report.filters).order_by(Event.timestamp).limit(10001)
    events = list(db.scalars(query))
    if len(events) > 10000:
        raise ValueError("Report exceeds 10,000 events; choose a narrower range")
    rows = [
        {
            "timestamp": aware(row.timestamp).isoformat(),
            "source_id": row.source_id,
            "severity": row.severity,
            "event_type": row.event_type,
            "message": row.message,
            "source_ip_hash": row.source_ip_hash,
            "username_hash": row.username_hash,
            "status_code": row.status_code,
            "parse_status": row.parse_status,
        }
        for row in events
    ]
    rows = (
        redact_sensitive_fields(
            rows, workspace.settings.get("privacy_mode", True), workspace.settings.get("masks", [])
        )
        if len(rows) <= 100
        else [
            redact_sensitive_fields(
                row,
                workspace.settings.get("privacy_mode", True),
                workspace.settings.get("masks", []),
            )
            for row in rows
        ]
    )
    if report.format == "csv":
        buffer = io.StringIO(newline="")
        columns = [
            "timestamp",
            "source_id",
            "severity",
            "event_type",
            "message",
            "source_ip_hash",
            "username_hash",
            "status_code",
            "parse_status",
        ]
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: safe_cell(value) for key, value in row.items()} for row in rows)
        report.content = buffer.getvalue()
    else:
        alerts = [
            serialize(row)
            for row in db.scalars(
                select(Alert)
                .where(
                    Alert.workspace_id == job.workspace_id,
                    Alert.created_at
                    >= utcnow() - timedelta(hours=float(report.filters.get("hours", 24))),
                )
                .limit(1000)
            )
        ]
        notes = [
            serialize(row)
            for row in db.scalars(
                select(Note)
                .where(Note.workspace_id == job.workspace_id)
                .order_by(Note.created_at.desc())
                .limit(1000)
            )
        ]
        report.content = json.dumps(
            {
                "title": report.title,
                "creator_id": report.creator_id,
                "generated_at": utcnow().isoformat(),
                "filters": report.filters,
                "disclaimer": "Authorized defensive monitoring only. Anomalies do not establish malicious intent. Event output is redacted; alert and note context is workspace-wide within stated limits.",
                "events": rows,
                "alerts": alerts,
                "notes": notes,
                "source_health": [
                    source_health(db, row)
                    for row in db.scalars(
                        select(Source).where(Source.workspace_id == job.workspace_id)
                    )
                ],
            },
            ensure_ascii=True,
        )
    report.status = "completed"
    db.add(
        Notification(
            workspace_id=job.workspace_id,
            user_id=job.actor_id,
            title=f"Report ready: {report.title}",
            link="/reports",
        )
    )
    job.result = {"report_id": report.id, "events": len(rows)}
