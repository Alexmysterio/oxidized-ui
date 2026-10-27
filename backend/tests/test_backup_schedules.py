from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.backup_schedule_service import run_due
from app.db import SessionLocal
from app.models import BackupSchedule, Job, Node
from app.timeutil import utcnow
from tests.conftest import make_node


def _create_node(admin, name: str, group: str | None = None) -> int:
    created = admin.post("/api/nodes", json=make_node(name=name))
    assert created.status_code == 201, created.text
    node_id = int(created.json()["node"]["id"])
    if group:
        with SessionLocal() as db:
            node = db.get(Node, node_id)
            assert node is not None
            node.group_name = group
            db.commit()
    return node_id


def _wait_for_job(admin, job_id: int) -> dict:
    job = {}
    for _ in range(60):
        job = admin.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            break
    return job


def test_single_node_backup_job_exposes_the_node_name(client: TestClient, admin):
    node_id = _create_node(admin, "PTP-N3-N2", group="ptp")

    response = admin.post(f"/api/nodes/{node_id}/backup")
    assert response.status_code == 202, response.text
    job = _wait_for_job(admin, response.json()["id"])

    assert job["kind"] == "backup_node"
    assert job["node_id"] == node_id
    assert job["node_name"] == "PTP-N3-N2"


def test_schedule_list_reports_scope_counts_and_oxidized_interval(client: TestClient, admin):
    _create_node(admin, "core-1", group="core")
    _create_node(admin, "edge-1", group="edge")
    _create_node(admin, "edge-2", group="edge")

    created = admin.post("/api/backups/schedules", json={"group_name": "edge", "interval_minutes": 360})
    assert created.status_code == 201, created.text
    assert created.json()["node_count"] == 2

    body = admin.get("/api/backups/schedules").json()
    assert body["total_nodes"] == 3
    assert body["oxidized_interval_seconds"] > 0
    groups = {group["name"]: group["node_count"] for group in body["groups"]}
    assert groups["edge"] == 2
    assert groups["core"] == 1
    assert body["items"][0]["group_name"] == "edge"
    assert body["items"][0]["node_count"] == 2


def test_schedule_skipped_by_a_running_bulk_job_is_not_reported_as_run(client: TestClient, admin):
    _create_node(admin, "core-1", group="core")
    with SessionLocal() as db:
        db.add(Job(kind="backup_all", status="running", progress_total=1))
        schedule = BackupSchedule(
            group_name="core",
            interval_minutes=60,
            next_run_at=utcnow() - timedelta(minutes=1),
            last_run_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id

    with SessionLocal() as db:
        assert run_due(db) == 0

    body = admin.get("/api/backups/schedules").json()
    stored = next(item for item in body["items"] if item["id"] == schedule_id)
    assert stored["last_run_at"].startswith("2026-10-01")
    next_run = datetime.fromisoformat(stored["next_run_at"])
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=UTC)
    assert next_run - utcnow() < timedelta(minutes=10)
