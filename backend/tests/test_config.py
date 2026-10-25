from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.settings import settings
from tests.conftest import make_node


def _wait_job(admin, job_id: int, timeout: float = 8.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = admin.get(f"/api/jobs/{job_id}")
        assert last.status_code == 200, last.text
        if last.json()["status"] in {"succeeded", "failed", "cancelled"}:
            return last.json()
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {last.text if last else 'no response'}")


def test_config_view_and_catalog(client: TestClient, admin):
    response = admin.get("/api/config")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["applied"]["status"] == "applied"
    assert data["config"]["output"]["default"] == "git"
    assert "source.default" in data["managed_keys"]
    assert "X-Oxidized-Source-Token" not in data["editable_yaml"]
    assert "X-Oxidized-Source-Token" in data["effective_yaml_preview"]
    assert settings.oxidized_source_token not in data["effective_yaml_preview"]
    assert data["drift"]["detected"] is False
    catalog = admin.get("/api/config/catalog")
    assert catalog.status_code == 200
    body = catalog.json()
    assert "interval" in {field["path"] for field in body["fields"]}
    assert "ios" in body["models"]
    assert body["model_vendors"]["routeros"] == "MikroTik"
    assert set(body["model_vendors"]) == set(body["models"])


def test_config_validation_and_managed_keys(client: TestClient, admin):
    config = admin.get("/api/config").json()["config"]
    config["interval"] = 90
    validated = admin.post("/api/config/validate", json={"config": config})
    assert validated.status_code == 200, validated.text
    assert validated.json()["editable_yaml"]

    managed = "source:\n  default: http\n"
    rejected = admin.post("/api/config/validate", json={"yaml": managed})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "config.managed_key_modified"

    invalid = admin.post("/api/config/validate", json={"yaml": "interval: [\n"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "config.invalid_yaml"


def test_config_draft_and_apply(client: TestClient, admin, fake_clients):
    current = admin.get("/api/config").json()
    config = current["config"]
    config["interval"] = 120
    draft = admin.post(
        "/api/config/draft",
        json={
            "config": config,
            "expected_revision_id": current["applied"]["id"],
            "origin": "form",
            "note": "test interval",
        },
    )
    assert draft.status_code == 201, draft.text
    revision_id = draft.json()["revision"]["id"]
    assert draft.json()["requires_apply"] is True

    restart_false = admin.post(
        "/api/config/apply",
        json={"revision_id": revision_id, "restart": False},
    )
    assert restart_false.status_code == 422
    assert restart_false.json()["error"]["code"] == "config.restart_required"

    applied = admin.post(
        "/api/config/apply",
        json={"revision_id": revision_id, "restart": True},
    )
    assert applied.status_code == 202, applied.text
    job = _wait_job(admin, applied.json()["id"])
    assert job["status"] == "succeeded", job
    assert fake_clients.docker.restart_calls == 1
    text = settings.config_file.read_text(encoding="utf-8")
    assert "interval: 120" in text
    assert "source:" in text
    assert "X-Oxidized-Source-Token" in text
    assert settings.oxidized_source_token in text
    refreshed = admin.get("/api/config").json()
    assert refreshed["applied"]["id"] == revision_id
    assert refreshed["draft"] is None


def test_group_draft_requires_apply_and_gates_nodes(client: TestClient, admin, fake_clients):
    created = admin.post(
        "/api/groups",
        json={
            "name": "core",
            "username": "group-user",
            "password": "group-password",
            "enable": "group-enable",
            "vars": {"ssh_no_keepalive": True},
        },
    )
    assert created.status_code == 201, created.text
    group = created.json()["group"]
    assert group["has_password"] is True
    assert group["has_enable"] is True
    assert "password" not in group
    assert "enable" not in group["vars"]

    pending_node = admin.post("/api/nodes", json=make_node(name="pending-node", group_name="core"))
    assert pending_node.status_code == 422
    assert pending_node.json()["error"]["code"] == "node.group_not_applied"

    groups = admin.get("/api/groups").json()
    assert groups["requires_admin_apply"] is True
    assert groups["groups"][0]["state"] == "draft"

    revision_id = created.json()["revision_id"]
    applied = admin.post("/api/config/apply", json={"revision_id": revision_id, "restart": True})
    assert applied.status_code == 202, applied.text
    job = _wait_job(admin, applied.json()["id"])
    assert job["status"] == "succeeded", job

    groups = admin.get("/api/groups").json()
    assert groups["groups"][0]["state"] == "applied"
    node = admin.post("/api/nodes", json=make_node(name="core-node", group_name="core"))
    assert node.status_code == 201, node.text
    assert node.json()["node"]["group_name"] == "core"


def test_config_rollback_and_revision_history(client: TestClient, admin, fake_clients):
    first = admin.get("/api/config").json()
    config = first["config"]
    config["interval"] = 111
    draft_one = admin.post(
        "/api/config/draft",
        json={"config": config, "expected_revision_id": first["applied"]["id"], "origin": "form"},
    )
    assert draft_one.status_code == 201, draft_one.text
    revision_one = draft_one.json()["revision"]["id"]
    applied_one = admin.post("/api/config/apply", json={"revision_id": revision_one, "restart": True})
    assert _wait_job(admin, applied_one.json()["id"])["status"] == "succeeded"

    current = admin.get("/api/config").json()
    second_config = current["config"]
    second_config["interval"] = 222
    draft_two = admin.post(
        "/api/config/draft",
        json={
            "config": second_config,
            "expected_revision_id": current["applied"]["id"],
            "origin": "form",
        },
    )
    assert draft_two.status_code == 201, draft_two.text
    second_id = draft_two.json()["revision"]["id"]
    applied_two = admin.post("/api/config/apply", json={"revision_id": second_id, "restart": True})
    assert applied_two.status_code == 202
    assert _wait_job(admin, applied_two.json()["id"])["status"] == "succeeded"
    assert "interval: 222" in settings.config_file.read_text(encoding="utf-8")

    restored = admin.post(
        f"/api/config/revisions/{revision_one}/restore",
        json={"note": "rollback interval"},
    )
    assert restored.status_code == 201, restored.text
    restored_id = restored.json()["revision"]["id"]
    applied_restore = admin.post("/api/config/apply", json={"revision_id": restored_id, "restart": True})
    assert applied_restore.status_code == 202
    assert _wait_job(admin, applied_restore.json()["id"])["status"] == "succeeded"
    assert "interval: 111" in settings.config_file.read_text(encoding="utf-8")
    revisions = admin.get("/api/config/revisions").json()
    assert revisions["total"] >= 3
    diff = admin.get(f"/api/config/revisions/{restored_id}/diff?against={second_id}")
    assert diff.status_code == 200
    assert diff.json()["to"] == restored_id


def test_config_apply_restart_failure_is_visible(client: TestClient, admin, fake_clients):
    current = admin.get("/api/config").json()
    config = current["config"]
    config["interval"] = 333
    draft = admin.post(
        "/api/config/draft",
        json={"config": config, "expected_revision_id": current["applied"]["id"], "origin": "form"},
    )
    revision_id = draft.json()["revision"]["id"]
    fake_clients.docker.fail_restart = True
    apply_response = admin.post("/api/config/apply", json={"revision_id": revision_id, "restart": True})
    assert apply_response.status_code == 202
    job = _wait_job(admin, apply_response.json()["id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "oxidized.restart_failed"
    applied = admin.get("/api/config").json()["applied"]
    assert applied["id"] != revision_id
    assert "interval: 333" not in settings.config_file.read_text(encoding="utf-8")


def test_config_yaml_roundtrip_and_regex(client: TestClient, admin):
    from app.config_model import (
        default_config,
        editable_yaml,
        load_editable_yaml,
        render_effective_config,
    )

    config = default_config()
    config["group_map"] = [
        {"match": "/^edge-/", "is_regex": True, "target": "core"},
        {"match": "legacy", "is_regex": False, "target": "old"},
    ]
    text = editable_yaml(config)
    assert "!ruby/regexp" in text
    parsed = load_editable_yaml(text)
    assert parsed["group_map"][0]["match"] == "/^edge-/"
    assert parsed["group_map"][0]["is_regex"] is True
    rendered = render_effective_config(parsed)
    assert "default: http" in rendered
    assert "vars_map: {}" in rendered
    assert "X-Oxidized-Source-Token" in rendered


def test_config_health_failure_rolls_back(client: TestClient, admin, fake_clients, monkeypatch):
    from app import config_service

    current = admin.get("/api/config").json()
    config = current["config"]
    config["interval"] = 444
    draft = admin.post(
        "/api/config/draft",
        json={"config": config, "expected_revision_id": current["applied"]["id"], "origin": "form"},
    )
    revision_id = draft.json()["revision"]["id"]
    monkeypatch.setattr(config_service, "HEALTH_TIMEOUT_SECONDS", 0.2)
    fake_clients.oxidized.fail_api = True
    apply_response = admin.post("/api/config/apply", json={"revision_id": revision_id, "restart": True})
    assert apply_response.status_code == 202
    job = _wait_job(admin, apply_response.json()["id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "config.health_check_failed"
    applied = admin.get("/api/config").json()["applied"]
    assert applied["id"] != revision_id
    assert "interval: 444" not in settings.config_file.read_text(encoding="utf-8")


def test_schedule_config_apply(client: TestClient, admin):
    current = admin.get("/api/config").json()
    config = current["config"]
    config["interval"] = 555
    draft = admin.post(
        "/api/config/draft",
        json={"config": config, "expected_revision_id": current["applied"]["id"], "origin": "form"},
    )
    revision_id = draft.json()["revision"]["id"]
    run_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    scheduled = admin.post("/api/config/schedule", json={"revision_id": revision_id, "run_at": run_at})
    assert scheduled.status_code == 201, scheduled.text
    assert scheduled.json()["status"] == "pending"
    listed = admin.get("/api/config/schedule")
    assert listed.status_code == 200
    assert any(item["revision_id"] == revision_id for item in listed.json()["items"])
    cancelled = admin.delete(f"/api/config/schedule/{scheduled.json()['id']}")
    assert cancelled.status_code == 204


def test_group_can_be_created_without_credentials(client: TestClient, admin, fake_clients):
    created = admin.post("/api/groups", json={"name": "empty-group"})
    assert created.status_code == 201, created.text
    assert created.json()["group"]["name"] == "empty-group"
