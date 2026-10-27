from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import notifications
from app.config_alert_service import detect_config_changes
from app.db import SessionLocal
from app.maintenance_service import scoped_node_ids
from app.models import (
    BackupSchedule,
    Job,
    Node,
    NodeConfigState,
    NodeRetry,
    NodeStatusCache,
)
from app.oxidized import OxidizedNode
from app.retry_service import plan_retries, run_due_retries
from app.timeutil import utcnow
from tests.conftest import make_node

OPERATOR_PASSWORD = "OperatorPassw0rd!"


def _node(admin, name: str, group: str | None = None) -> int:
    response = admin.post("/api/nodes", json=make_node(name=name))
    assert response.status_code == 201, response.text
    node_id = int(response.json()["node"]["id"])
    if group:
        with SessionLocal() as db:
            node = db.get(Node, node_id)
            assert node is not None
            node.group_name = group
            db.commit()
    return node_id


def _failed_cache(node_id: int, when: datetime | None = None) -> None:
    moment = when or utcnow()
    with SessionLocal() as db:
        cache = db.get(NodeStatusCache, node_id)
        if cache is None:
            cache = NodeStatusCache(node_id=node_id, observed_at=moment)
            db.add(cache)
        cache.status = "fail"
        cache.last_failure_at = moment
        cache.last_success_at = moment - timedelta(days=1)
        cache.observed_at = moment
        db.commit()


def test_schedule_can_be_disabled_and_rescheduled(client: TestClient, admin):
    created = admin.post("/api/backups/schedules", json={"group_name": None, "interval_minutes": 1440})
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    patched = admin.patch(f"/api/backups/schedules/{schedule_id}", json={"enabled": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["enabled"] is False

    rescheduled = admin.patch(
        f"/api/backups/schedules/{schedule_id}", json={"interval_minutes": 360, "enabled": True}
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["interval_minutes"] == 360
    assert rescheduled.json()["enabled"] is True


def test_maintenance_window_skips_retries_and_schedules(client: TestClient, admin):
    node_id = _node(admin, "core-1", group="core")
    _failed_cache(node_id)
    start = utcnow() - timedelta(minutes=5)
    end = utcnow() + timedelta(hours=1)
    created = admin.post(
        "/api/maintenance",
        json={
            "scope_type": "group",
            "group_name": "core",
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "reason": "window",
        },
    )
    assert created.status_code == 201, created.text
    with SessionLocal() as db:
        assert node_id in scoped_node_ids(db)
        plan_retries(db)
        retry = db.get(NodeRetry, node_id)
        assert retry is not None
        retry.next_attempt_at = utcnow() - timedelta(minutes=1)
        db.commit()
        assert run_due_retries(db) == 0
        job = db.query(Job).filter(Job.kind == "backup_node").count()
        assert job == 0

    with SessionLocal() as db:
        db.add(
            BackupSchedule(
                group_name="core",
                interval_minutes=60,
                next_run_at=utcnow() - timedelta(minutes=1),
            )
        )
        db.commit()

    from app.backup_schedule_service import run_due as run_due_schedules

    with SessionLocal() as db:
        assert run_due_schedules(db) == 0

    windows = admin.get("/api/maintenance").json()["items"]
    assert windows and windows[0]["active"] is True

    assert admin.delete(f"/api/maintenance/{windows[0]['id']}").status_code == 204


def test_retry_plan_and_backoff(client: TestClient, admin, fake_clients):
    node_id = _node(admin, "retry-1")
    _failed_cache(node_id)

    with SessionLocal() as db:
        plan_retries(db)
        retry = db.get(NodeRetry, node_id)
        assert retry is not None and retry.attempts == 0
        retry.next_attempt_at = utcnow() - timedelta(minutes=1)
        db.commit()

    with SessionLocal() as db:
        assert run_due_retries(db) == 1

    with SessionLocal() as db:
        retry = db.get(NodeRetry, node_id)
        assert retry is not None and retry.attempts == 1
        assert retry.next_attempt_at > utcnow()
    for _ in range(60):
        if fake_clients.oxidized.next_calls:
            break
        import time

        time.sleep(0.05)
    assert fake_clients.oxidized.next_calls == ["retry-1"]


def test_config_change_detection_notifies_once(client: TestClient, admin, fake_clients, monkeypatch):
    node_id = _node(admin, "change-1")
    sent: list[str] = []

    def _fake_send(row, *, text, event):
        sent.append(event)
        return True

    monkeypatch.setattr(notifications, "_send_channel", _fake_send)
    channel = admin.post(
        "/api/system/notifications",
        json={
            "name": "ops",
            "kind": "webhook",
            "events": ["config.changed"],
            "config": {"url": "https://example.invalid/hook"},
        },
    )
    assert channel.status_code == 201, channel.text

    first = OxidizedNode(
        name="change-1",
        full_name="change-1",
        address="10.0.0.1",
        group=None,
        model="ios",
        status="success",
        last_started=utcnow(),
        last_finished=utcnow(),
        last_time=1.0,
        mtime=utcnow(),
    )
    fake_clients.oxidized.current_configs["change-1"] = "hostname A\n"
    with SessionLocal() as db:
        assert detect_config_changes(db, [first]) == 0

    second = replace(first, mtime=utcnow() + timedelta(minutes=5))
    fake_clients.oxidized.current_configs["change-1"] = "hostname B\n"
    with SessionLocal() as db:
        assert detect_config_changes(db, [second]) == 1
        state = db.get(NodeConfigState, node_id)
        assert state is not None and state.last_changed_at is not None

    third = replace(first, mtime=utcnow() + timedelta(minutes=10))
    with SessionLocal() as db:
        assert detect_config_changes(db, [third]) == 0
    assert sent.count("config.changed") == 1


def test_compliance_templates_and_report(client: TestClient, admin, fake_clients):
    node_id = _node(admin, "compliant-1", group="core")
    _node(admin, "deviating-1", group="core")
    fake_clients.oxidized.nodes = [
        OxidizedNode(
            name="compliant-1",
            full_name="compliant-1",
            address="10.0.0.1",
            group="core",
            model="ios",
            status="success",
            last_started=utcnow(),
            last_finished=utcnow(),
            last_time=1.0,
            mtime=utcnow(),
        ),
        OxidizedNode(
            name="deviating-1",
            full_name="deviating-1",
            address="10.0.0.2",
            group="core",
            model="ios",
            status="success",
            last_started=utcnow(),
            last_finished=utcnow(),
            last_time=1.0,
            mtime=utcnow(),
        ),
    ]
    fake_clients.oxidized.current_configs["compliant-1"] = "hostname core\n"
    fake_clients.oxidized.current_configs["deviating-1"] = "hostname other\n"

    template = admin.post(
        "/api/compliance/templates",
        json={"name": "core-baseline", "scope_type": "group", "scope_value": "core", "content": "hostname core\n"},
    )
    assert template.status_code == 201, template.text

    report = admin.get("/api/compliance/report").json()
    by_name = {item["name"]: item for item in report["items"]}
    assert by_name["compliant-1"]["status"] == "compliant"
    assert by_name["deviating-1"]["status"] == "deviating"
    assert by_name["deviating-1"]["template_name"] == "core-baseline"

    detail = admin.get(f"/api/compliance/report/{node_id}")
    assert detail.status_code == 200
    assert detail.json()["compliant"] is True

    assert admin.delete(f"/api/compliance/templates/{template.json()['id']}").status_code == 204


def test_preferences_roundtrip(client: TestClient, admin):
    defaults = admin.get("/api/me/preferences").json()
    assert defaults == {"favorites": [], "saved_filters": []}

    updated = admin.patch(
        "/api/me/preferences",
        json={"favorites": [3, 1, 3], "saved_filters": [{"name": "core", "query": "group=core&sort=name"}]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["favorites"] == [3, 1]
    assert updated.json()["saved_filters"][0]["name"] == "core"


def test_group_scope_limits_nodes_and_actions(client: TestClient, admin, login_as, fake_clients):
    scoped_id = _node(admin, "scoped-1", group="core")
    _node(admin, "other-1", group="edge")

    created = admin.post(
        "/api/users",
        json={
            "username": "grupo",
            "password": OPERATOR_PASSWORD,
            "role": "operator",
            "language": "es",
            "scope_groups": ["core"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["scope_groups"] == ["core"]

    operator = login_as(client, "grupo", OPERATOR_PASSWORD)
    listed = operator.get("/api/nodes").json()
    assert [item["name"] for item in listed["items"]] == ["scoped-1"]
    assert operator.get(f"/api/nodes/{scoped_id}").status_code == 200
    with SessionLocal() as db:
        other_id = db.scalar(select(Node.id).where(Node.name == "other-1"))
    assert other_id is not None
    assert operator.get(f"/api/nodes/{other_id}").status_code == 404
    forbidden = operator.post(f"/api/nodes/{other_id}/backup")
    assert forbidden.status_code == 404

    search = operator.get("/api/search", params={"q": "other"}).json()
    assert search["nodes"] == []

def test_digest_is_sent_once_per_day(client: TestClient, admin, monkeypatch):
    from app.notifications import send_due_digests
    from app.system_service import ensure_system_settings

    sent: list[str] = []

    def _fake_send(row, *, text, event):
        sent.append(event)
        return True

    monkeypatch.setattr(notifications, "_send_channel", _fake_send)
    created = admin.post(
        "/api/system/notifications",
        json={
            "name": "digest",
            "kind": "webhook",
            "events": ["job.failed"],
            "digest_enabled": True,
            "config": {"url": "https://example.invalid/hook"},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["digest_enabled"] is True

    with SessionLocal() as db:
        row = ensure_system_settings(db)
        row.digest_enabled = True
        row.digest_hour = utcnow().hour
        row.timezone = None
        db.commit()

    with SessionLocal() as db:
        send_due_digests(db)
    assert sent.count("digest") == 1
    with SessionLocal() as db:
        send_due_digests(db)
    assert sent.count("digest") == 1


def test_export_configuration_masks_secrets(client: TestClient, admin):
    response = admin.put(
        "/api/system/export",
        json={
            "kind": "sftp",
            "interval_hours": 24,
            "enabled": True,
            "config": {
                "host": "backup.example.invalid",
                "username": "oxidized",
                "password": "super-secret-password",
                "remote_dir": "/backups",
                "passphrase": "export-passphrase-123",
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["target"]["host"] == "backup.example.invalid"
    assert body["target"]["has_secret"] is True
    assert "password" not in response.text
    assert "passphrase" not in response.text
    assert body["enabled"] is True
