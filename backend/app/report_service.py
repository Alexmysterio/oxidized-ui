from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .compliance_service import list_templates
from .compliance_service import report as compliance_report
from .errors import AppError
from .jobs import Job
from .models import BackupRun, Node, NodeConfigState
from .models import Job as JobModel
from .notifications import notify_report_ready
from .security import AuthContext
from .settings import settings
from .system_service import ensure_system_settings
from .timeutil import ensure_utc, to_iso, utcnow

REPORTS_DIR = settings.data_dir / "reports"


def _backup_rows(db: Session, cutoff) -> list[dict[str, Any]]:
    rows = db.execute(select(BackupRun, Node).join(Node, Node.id == BackupRun.node_id, isouter=True)).all()
    result: list[dict[str, Any]] = []
    for run, node in rows:
        finished = ensure_utc(run.finished_at)
        if finished is None or finished < cutoff:
            continue
        result.append(
            {
                "node_id": run.node_id,
                "node": run.node_name or (node.name if node else ""),
                "group": run.group_name or (node.group_name if node else ""),
                "status": run.status,
                "finished_at": finished,
            }
        )
    return result


def build_report(db: Session, days: int = 7) -> dict[str, Any]:
    cutoff = utcnow() - timedelta(days=days)
    runs = _backup_rows(db, cutoff)
    per_node: dict[str, dict[str, Any]] = {}
    for run in runs:
        entry = per_node.setdefault(
            run["node"],
            {
                "node": run["node"],
                "group": run["group"] or "",
                "ok": 0,
                "failed": 0,
                "last_success": None,
                "last_failure": None,
            },
        )
        if run["status"] == "success":
            entry["ok"] += 1
            if entry["last_success"] is None or run["finished_at"] > entry["last_success"]:
                entry["last_success"] = run["finished_at"]
        else:
            entry["failed"] += 1
            if entry["last_failure"] is None or run["finished_at"] > entry["last_failure"]:
                entry["last_failure"] = run["finished_at"]

    failed_jobs = db.scalar(
        select(func.count(JobModel.id)).where(
            JobModel.status == "failed",
            JobModel.finished_at.is_not(None),
            JobModel.finished_at >= cutoff,
        )
    ) or 0
    changes = list(
        db.execute(
            select(Node.name, NodeConfigState.last_changed_at)
            .join(NodeConfigState, NodeConfigState.node_id == Node.id)
            .where(NodeConfigState.last_changed_at >= cutoff)
            .order_by(NodeConfigState.last_changed_at.desc())
        ).all()
    )
    compliance_summary: dict[str, int] = {}
    try:
        if list_templates(db):
            ctx = AuthContext(
                user_id=0,
                username="system",
                role="admin",
                language="es",
                theme="system",
                session_id=0,
                session_token="",
                csrf_token="",
                scope_groups=None,
            )
            report = compliance_report(db, ctx=ctx, limit=200)
            compliance_summary = dict(report["summary"])
    except Exception:  # noqa: BLE001 - compliance is best-effort in reports
        compliance_summary = {"error": 1}

    total_ok = sum(item["ok"] for item in per_node.values())
    total_failed = sum(item["failed"] for item in per_node.values())
    return {
        "generated_at": utcnow(),
        "days": days,
        "nodes": sorted(per_node.values(), key=lambda item: item["node"]),
        "failed_jobs": int(failed_jobs),
        "changes": [{"node": name, "changed_at": ensure_utc(when)} for name, when in changes],
        "compliance": compliance_summary,
        "totals": {
            "ok": total_ok,
            "failed": total_failed,
            "nodes": len(per_node),
            "changes": len(changes),
        },
    }


def render_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "key", "value"])
    writer.writerow(["meta", "generated_at", to_iso(report["generated_at"])])
    writer.writerow(["meta", "days", report["days"]])
    writer.writerow(["summary", "backups_ok", report["totals"]["ok"]])
    writer.writerow(["summary", "backups_failed", report["totals"]["failed"]])
    writer.writerow(["summary", "failed_jobs", report["failed_jobs"]])
    writer.writerow(["summary", "config_changes", report["totals"]["changes"]])
    for key, value in report["compliance"].items():
        writer.writerow(["compliance", key, value])
    writer.writerow([])
    writer.writerow(["node", "group", "backups_ok", "backups_failed", "last_success", "last_failure"])
    for item in report["nodes"]:
        writer.writerow(
            [
                item["node"],
                item["group"],
                item["ok"],
                item["failed"],
                to_iso(item["last_success"]) or "",
                to_iso(item["last_failure"]) or "",
            ]
        )
    writer.writerow([])
    writer.writerow(["config_change", "node", "changed_at"])
    for item in report["changes"]:
        writer.writerow(["config_change", item["node"], to_iso(item["changed_at"])])
    return buffer.getvalue()


def summary_text(report: dict[str, Any], site_name: str) -> str:
    totals = report["totals"]
    return (
        f"{site_name} weekly report: {totals['ok']} successful and {totals['failed']} failed backups "
        f"across {totals['nodes']} nodes, {report['failed_jobs']} failed jobs, "
        f"{totals['changes']} configuration changes"
    )


def _upload_report(db: Session, filename: str, payload: bytes) -> bool:
    from .export_service import configured, upload_bytes

    if not configured(db):
        return False
    try:
        upload_bytes(db, filename, payload)
        return True
    except AppError:
        return False


def generate_report(db: Session, *, trigger: str) -> dict[str, Any]:
    report = build_report(db)
    content = render_csv(report)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"report-{utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    path = REPORTS_DIR / filename
    path.write_text(content, encoding="utf-8")
    uploaded = _upload_report(db, filename, content.encode("utf-8"))
    row = ensure_system_settings(db)
    row.report_last_run_at = utcnow()
    db.commit()
    site = row.site_name
    notify_report_ready(db, summary_text(report, site), uploaded)
    return {
        "filename": filename,
        "bytes": len(content),
        "uploaded": uploaded,
        "trigger": trigger,
        "totals": report["totals"],
    }


def run_report_job(db: Session, job: Job) -> dict[str, Any]:
    return generate_report(db, trigger=str(job.payload.get("trigger") or "manual"))


def list_reports() -> list[dict[str, Any]]:
    if not REPORTS_DIR.is_dir():
        return []
    items = []
    for path in sorted(REPORTS_DIR.glob("report-*.csv"), reverse=True)[:50]:
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "bytes": stat.st_size,
                "created_at": to_iso(datetime.fromtimestamp(stat.st_mtime, tz=UTC)),
            }
        )
    return items


def report_path(filename: str):
    if "/" in filename or "\\" in filename or not filename.startswith("report-") or not filename.endswith(".csv"):
        raise AppError("validation.invalid_format", params={"field": "filename"})
    path = REPORTS_DIR / filename
    if not path.is_file():
        raise AppError("app.not_found", params={"id": filename})
    return path


def run_due_report(db: Session) -> int:
    row = ensure_system_settings(db)
    if not row.report_enabled:
        return 0
    now = utcnow()
    if now.weekday() != int(row.report_weekday or 0):
        return 0
    if now.hour < int(row.report_hour or 0):
        return 0
    last = ensure_utc(row.report_last_run_at)
    if last is not None and last > now - timedelta(days=6):
        return 0
    active = db.scalar(select(JobModel).where(JobModel.kind == "report", JobModel.status.in_(("queued", "running"))))
    if active is not None:
        return 0
    from .jobs import create_and_submit

    create_and_submit(
        db,
        kind="report",
        actor_id=None,
        payload={"trigger": "schedule"},
        progress_total=1,
        runner=run_report_job,
    )
    return 1


def run_report_now(db: Session, *, actor: AuthContext) -> Job:
    from .jobs import create_and_submit

    active = db.scalar(select(JobModel).where(JobModel.kind == "report", JobModel.status.in_(("queued", "running"))))
    if active is not None:
        raise AppError("job.already_running", params={"job_id": active.id})
    return create_and_submit(
        db,
        kind="report",
        actor_id=actor.user_id,
        payload={"trigger": "manual"},
        progress_total=1,
        runner=run_report_job,
    )
