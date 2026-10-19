from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common import create_audit_log
from app.db import aware, utcnow
from app.models import Alert, AlertEvent, Baseline, Event, Notification, Rule, Source
from app.security import digest
from app.statistics import anomaly, baseline

RULE_DEFAULTS = [
    ("Failed login burst", "failed_login", "high", 5),
    ("Success after failed logins", "success_after_failures", "critical", 5),
    ("Repeated unauthorized responses", "http_401", "medium", 10),
    ("Repeated forbidden responses", "http_403", "high", 10),
    ("Server error spike", "error_spike", "high", 10),
    ("Unusual request volume", "volume_spike", "medium", 200),
    ("Sensitive endpoint access", "sensitive_path", "medium", 5),
    ("Previously unseen entity", "new_entity", "low", 3),
    ("Multiple usernames from one source", "many_users", "high", 5),
    ("One username from many sources", "many_sources", "high", 5),
    ("Unusual service or process", "unusual_process", "medium", 3),
    ("Log source silence", "source_silence", "medium", 60),
    ("Repeated parser failures", "parser_failure", "medium", 3),
    ("Out-of-hours authentication", "out_of_hours", "low", 3),
    ("Sudden severity increase", "severity_spike", "high", 10),
    ("Statistical volume anomaly", "statistical", "medium", 1),
]


def seed_rules(db: Session, wid: str, actor: str):
    if db.scalar(select(Rule.id).where(Rule.workspace_id == wid).limit(1)):
        return
    for name, kind, severity, threshold in RULE_DEFAULTS:
        db.add(
            Rule(
                workspace_id=wid,
                name=name,
                kind=kind,
                severity=severity,
                threshold=threshold,
                group_by="username_hash" if kind == "many_sources" else "source_ip_hash",
                updated_by=actor,
                description="Review evidence and expected operational activity before drawing conclusions.",
                config={},
            )
        )


def matches(event: Event, kind: str, config: dict) -> bool:
    if event.source_ip_hash in config.get(
        "excluded_ip_hashes", []
    ) or event.username_hash in config.get("excluded_user_hashes", []):
        return False
    if config.get("service") and event.service != config["service"]:
        return False
    if kind in {"failed_login", "success_after_failures"}:
        return event.event_type in (
            {"login_failed", "login_success"}
            if kind == "success_after_failures"
            else {"login_failed"}
        )
    if kind.startswith("http_"):
        return event.status_code == int(kind[5:])
    if kind == "error_spike":
        return bool(
            (event.status_code and event.status_code >= 500)
            or event.severity in {"high", "critical"}
        )
    if kind == "sensitive_path":
        return any(
            event.url_path.startswith(prefix)
            for prefix in config.get("paths", ["/admin", "/.env", "/wp-admin", "/internal"])
        )
    if kind == "parser_failure":
        return event.parse_status == "failed"
    if kind == "out_of_hours":
        return event.category == "authentication" and not config.get("start_hour", 6) <= aware(
            event.timestamp
        ).hour < config.get("end_hour", 22)
    if kind == "severity_spike":
        return event.severity in {"high", "critical"}
    if kind == "unusual_process":
        return bool(event.details.get("process")) and event.details.get(
            "process"
        ) not in config.get("expected_processes", ["sshd", "nginx", "postgres"])
    return True


def evaluate_rule(db: Session, rule: Rule, source: Source, now=None) -> list[dict]:
    now = now or utcnow()
    start = now - timedelta(minutes=rule.window_minutes)
    if rule.kind == "source_silence":
        minutes = (now - aware(source.last_event_at or source.created_at)).total_seconds() / 60
        threshold = max(rule.threshold, source.silence_minutes)
        return (
            [
                {
                    "group": source.id,
                    "observed": round(minutes, 1),
                    "threshold": threshold,
                    "events": [],
                    "first": source.last_event_at or source.created_at,
                    "last": now,
                    "unit": "minutes without ingestion",
                }
            ]
            if minutes >= threshold
            else []
        )
    if rule.kind == "statistical":
        stats_row = db.scalar(
            select(Baseline).where(
                Baseline.source_id == source.id, Baseline.feature == "events_per_5m"
            )
        )
        if not stats_row:
            return []
        from sqlalchemy import func

        value = (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.source_id == source.id,
                    Event.timestamp >= now - timedelta(minutes=5),
                    Event.timestamp <= now,
                )
            )
            or 0
        )
        result = anomaly(value, stats_row.stats)
        return (
            [
                {
                    "group": source.id,
                    **result,
                    "events": [],
                    "first": now - timedelta(minutes=5),
                    "last": now,
                    "unit": "events per five minutes",
                    "model_version": stats_row.version,
                }
            ]
            if result["triggered"]
            else []
        )
    groups: dict = defaultdict(
        lambda: {
            "events": [],
            "observed": 0,
            "users": set(),
            "ips": set(),
            "failures": 0,
            "success_after": False,
            "first": None,
            "last": None,
        }
    )
    query = (
        select(Event)
        .where(
            Event.workspace_id == rule.workspace_id,
            Event.source_id == source.id,
            Event.timestamp >= start,
            Event.timestamp <= now,
        )
        .order_by(Event.timestamp, Event.id)
    )
    for event in db.scalars(query.execution_options(yield_per=500)):
        if rule.kind == "many_sources" and not event.username_hash:
            continue
        if rule.kind == "many_users" and (not event.username_hash or not event.source_ip_hash):
            continue
        if rule.kind == "new_entity" and not getattr(event, rule.group_by):
            continue
        if not matches(event, rule.kind, rule.config):
            continue
        group_key = getattr(event, rule.group_by) or source.id
        group = groups[group_key]
        group["observed"] += 1 + event.duplicates if rule.kind == "parser_failure" else 1
        if len(group["events"]) < 100:
            group["events"].append(event.id)
        if event.username_hash:
            group["users"].add(event.username_hash)
        if event.source_ip_hash:
            group["ips"].add(event.source_ip_hash)
        if event.event_type == "login_failed":
            group["failures"] += 1
        elif event.event_type == "login_success" and group["failures"] >= rule.threshold:
            group["success_after"] = True
        group["first"] = group["first"] or event.timestamp
        group["last"] = event.timestamp
    results = []
    for key, group in groups.items():
        observed = (
            len(group["users"])
            if rule.kind == "many_users"
            else len(group["ips"])
            if rule.kind == "many_sources"
            else group["observed"]
        )
        trigger = observed >= rule.threshold
        if rule.kind == "success_after_failures":
            observed, trigger = group["failures"], group["success_after"]
        if rule.kind == "new_entity" and trigger:
            column = getattr(Event, rule.group_by)
            prior = db.scalar(
                select(Event.id)
                .where(Event.source_id == source.id, Event.timestamp < start, column == key)
                .limit(1)
            )
            # Require history from the source before calling an entity new.
            history = db.scalar(
                select(Event.id)
                .where(Event.source_id == source.id, Event.timestamp < start)
                .limit(1)
            )
            trigger = prior is None and history is not None
        if trigger:
            results.append(
                {
                    "group": key,
                    "observed": observed,
                    "threshold": rule.threshold,
                    "events": group["events"],
                    "first": group["first"],
                    "last": group["last"],
                    "unit": "matching events"
                    if rule.kind not in {"many_users", "many_sources"}
                    else "distinct entities",
                }
            )
    return results


def update_baselines(db: Session, wid: str, source_id: str | None = None):
    now = utcnow()
    sources = select(Source).where(Source.workspace_id == wid)
    if source_id:
        sources = sources.where(Source.id == source_id)
    for source in db.scalars(sources):
        row = db.scalar(
            select(Baseline).where(
                Baseline.source_id == source.id, Baseline.feature == "events_per_5m"
            )
        )
        # Exclude the active five-minute window to avoid training on the anomaly being tested.
        start = now - timedelta(hours=24)
        reset_at = row.stats.get("reset_at") if row else None
        if reset_at:
            from app.parsers import parse_timestamp

            start = max(start, parse_timestamp(reset_at))
        end = now - timedelta(minutes=5)
        counts: dict[int, float] = defaultdict(float)
        first = None
        for timestamp in db.scalars(
            select(Event.timestamp)
            .where(Event.source_id == source.id, Event.timestamp >= start, Event.timestamp < end)
            .execution_options(yield_per=1000)
        ):
            point = int(aware(timestamp).timestamp()) // 300
            first = min(first or point, point)
            counts[point] += 1
        last = int(end.timestamp()) // 300
        values = [counts[bucket] for bucket in range(first, last)] if first is not None else []
        stats = baseline(values)
        if reset_at:
            stats["reset_at"] = reset_at
        row = db.scalar(
            select(Baseline).where(
                Baseline.source_id == source.id, Baseline.feature == "events_per_5m"
            )
        )
        if row:
            row.stats = stats
        else:
            db.add(Baseline(workspace_id=wid, source_id=source.id, stats=stats))
    db.flush()


def run_detection(db: Session, wid: str, source_id: str | None = None) -> int:
    now = utcnow()
    update_baselines(db, wid, source_id)
    sources = list(
        db.scalars(select(Source).where(Source.workspace_id == wid, Source.enabled.is_(True)))
    )
    rules = list(db.scalars(select(Rule).where(Rule.workspace_id == wid, Rule.enabled.is_(True))))
    created = 0
    for rule in rules:
        for source in sources:
            if source_id and source.id != source_id:
                continue
            if rule.config.get("source_ids") and source.id not in rule.config["source_ids"]:
                continue
            for match in evaluate_rule(db, rule, source, now):
                group = match["group"]
                previous = db.scalar(
                    select(Alert)
                    .where(
                        Alert.workspace_id == wid,
                        Alert.rule_id == rule.id,
                        Alert.source_id == source.id,
                    )
                    .order_by(Alert.created_at.desc())
                    .limit(100)
                )
                # Query the matching group in JSON portably through a bounded rule/source set.
                candidates = db.scalars(
                    select(Alert)
                    .where(
                        Alert.workspace_id == wid,
                        Alert.rule_id == rule.id,
                        Alert.source_id == source.id,
                        Alert.created_at >= now - timedelta(days=31),
                    )
                    .order_by(Alert.created_at.desc())
                )
                previous = next(
                    (item for item in candidates if item.explanation.get("group") == group), None
                )
                if previous and (
                    (previous.suppressed_until and aware(previous.suppressed_until) > now)
                    or aware(previous.created_at) > now - timedelta(minutes=rule.cooldown_minutes)
                ):
                    continue
                bucket = int(now.timestamp()) // (rule.cooldown_minutes * 60)
                dedup = digest(f"{rule.id}:{rule.version}:{source.id}:{group}:{bucket}")
                explanation = {
                    "condition": rule.kind,
                    "observed": match["observed"],
                    "threshold": match["threshold"],
                    "window_minutes": 5 if rule.kind == "statistical" else rule.window_minutes,
                    "group": group,
                    "source_name": source.name,
                    "unit": match["unit"],
                    "summary": f"{source.name} produced {match['observed']} {match['unit']}; configured threshold is {match['threshold']}.",
                    "limitation": "Anomaly detection is probabilistic. This observation does not prove malicious intent; verify authorized activity and data quality.",
                    "steps": [
                        "Review the chronological evidence and affected entity hashes.",
                        "Compare with change records, maintenance and normal service activity.",
                        "Confirm findings with the system owner before taking any response action.",
                    ],
                    "baseline": match.get("expected"),
                    "model_version": match.get("model_version"),
                }
                try:
                    with db.begin_nested():
                        alert = Alert(
                            workspace_id=wid,
                            title=rule.name,
                            description=rule.description,
                            severity=rule.severity,
                            confidence=match.get(
                                "confidence",
                                min(
                                    0.95,
                                    0.65 + match["observed"] / max(match["threshold"], 1) * 0.05,
                                ),
                            ),
                            rule_id=rule.id,
                            rule_version=rule.version,
                            source_id=source.id,
                            dedup_key=dedup,
                            explanation=explanation,
                            first_seen=match["first"],
                            last_seen=match["last"],
                            event_count=int(match["observed"]),
                        )
                        db.add(alert)
                        db.flush()
                        for event_id in match["events"]:
                            db.add(AlertEvent(alert_id=alert.id, event_id=event_id))
                            event = db.get(Event, event_id)
                            if event:
                                event.anomaly_score = max(event.anomaly_score, alert.confidence)
                        db.add(
                            Notification(
                                workspace_id=wid,
                                title=f"{rule.severity.title()} alert: {rule.name}",
                                link=f"/alerts/{alert.id}",
                            )
                        )
                        create_audit_log(db, wid, None, "alert.created", "alert", alert.id)
                    created += 1
                except IntegrityError:
                    continue
    return created
