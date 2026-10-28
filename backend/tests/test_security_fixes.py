from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ConfigTemplate, Node, NodeTemplate, User
from app.yaml_codec import load_yaml
from tests.conftest import ADMIN_PASSWORD, make_node

OPERATOR_PASSWORD = "OperatorPassw0rd!"
VIEWER_PASSWORD = "ViewerPassw0rd!"


def _node(admin, name: str, group: str | None = None, **extra) -> int:
    response = admin.post("/api/nodes", json=make_node(name=name, **extra))
    assert response.status_code == 201, response.text
    node_id = int(response.json()["node"]["id"])
    if group:
        with SessionLocal() as db:
            node = db.get(Node, node_id)
            assert node is not None
            node.group_name = group
            db.commit()
    return node_id


def _user(admin, username: str, password: str, role: str, scope: list[str] | None = None) -> int:
    response = admin.post(
        "/api/users",
        json={"username": username, "password": password, "role": role, "language": "es", "scope_groups": scope},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_api_tokens_are_clamped_and_revoked(client: TestClient, admin, login_as, monkeypatch):
    admin_id = admin.get("/api/auth/session").json()["user"]["id"]
    created = admin.post("/api/auth/tokens", json={"name": "admin-token", "role": "admin", "days": 1})
    assert created.status_code == 201, created.text
    raw = created.json()["token"]
    headers = {"Authorization": f"Bearer {raw}"}

    second_admin = _user(admin, "admin2", ADMIN_PASSWORD, "admin")
    login_as(client, "admin2", ADMIN_PASSWORD)

    with SessionLocal() as db:
        user = db.get(User, admin_id)
        assert user is not None
        user.role = "viewer"
        db.commit()

    forbidden = client.get("/api/users", headers=headers)
    assert forbidden.status_code == 403
    assert client.get("/api/nodes", headers=headers).status_code == 200

    second = login_as(client, "admin2", ADMIN_PASSWORD)
    reset = second.post(f"/api/users/{admin_id}/password", json={"new_password": "AnotherPassw0rd!"})
    assert reset.status_code == 204, reset.text
    assert client.get("/api/nodes", headers=headers).status_code == 401
    assert second_admin


def test_scoped_operator_cannot_touch_other_groups(client: TestClient, admin, login_as, fake_clients):
    core = _node(admin, "core-1", group="core")
    edge = _node(admin, "edge-1", group="edge")
    _user(admin, "scoped", OPERATOR_PASSWORD, "operator", scope=["core"])

    edge_job = admin.post(f"/api/nodes/{edge}/backup")
    assert edge_job.status_code == 202
    edge_job_id = edge_job.json()["id"]
    schedule = admin.post("/api/backups/schedules", json={"group_name": "edge", "interval_minutes": 60})
    assert schedule.status_code == 201

    operator = login_as(client, "scoped", OPERATOR_PASSWORD)
    assert operator.get(f"/api/jobs/{edge_job_id}").status_code == 404
    assert operator.delete(f"/api/jobs/{edge_job_id}").status_code == 404
    assert operator.delete(f"/api/backups/schedules/{schedule.json()['id']}").status_code == 404
    assert operator.get("/api/logs").status_code == 403
    groups = operator.get("/api/groups").json()["groups"]
    assert all(group["name"] == "core" for group in groups)
    status = operator.get("/api/status").json()
    assert status["nodes"]["total"] == 1
    assert operator.get(f"/api/nodes/{core}").status_code == 200


def test_templates_are_encrypted_and_not_visible_to_viewers(client: TestClient, admin, login_as):
    created = admin.post(
        "/api/node-templates",
        json={"name": "secret-vars", "model": "ios", "vars": {"auth_password": "super-secret"}},
    )
    assert created.status_code == 201, created.text
    with SessionLocal() as db:
        row = db.scalar(select(NodeTemplate).where(NodeTemplate.name == "secret-vars"))
        assert row is not None and "_ciphertext" in row.vars
        assert "super-secret" not in str(row.vars)

    template = admin.post(
        "/api/compliance/templates",
        json={"name": "secret-config", "scope_type": "global", "content": "snmp community secret\n"},
    )
    assert template.status_code == 201, template.text
    with SessionLocal() as db:
        row = db.scalar(select(ConfigTemplate).where(ConfigTemplate.name == "secret-config"))
        assert row is not None and row.content.startswith("enc:v1:")
        assert "secret" not in row.content

    _user(admin, "viewer1", VIEWER_PASSWORD, "viewer")
    viewer = login_as(client, "viewer1", VIEWER_PASSWORD)
    assert viewer.get("/api/node-templates").status_code == 403
    assert viewer.get("/api/compliance/templates").status_code == 403
    assert viewer.get("/api/compliance/report").status_code == 403


def test_yaml_python_tags_are_rejected():
    from app.errors import AppError

    try:
        load_yaml("a: !!python/object/apply:os.getpid []")
    except AppError as exc:
        assert exc.code == "config.invalid_yaml"
    else:
        raise AssertionError("python YAML tags must be rejected")


def test_sites_ignores_non_finite_coordinates(client: TestClient, admin):
    _node(admin, "nan-site", tags={"site": "Madrid", "latitude": "nan", "longitude": "1"})
    response = admin.get("/api/nodes/sites", params={"tag": "Site"})
    assert response.status_code == 200, response.text
    node = response.json()["sites"][0]["nodes"][0]
    assert node["latitude"] is None


def test_loopback_targets_are_rejected(client: TestClient, admin):
    node_id = _node(admin, "loopback", address="127.0.0.1")
    ping = admin.post(f"/api/nodes/{node_id}/ping")
    assert ping.status_code == 422
    assert ping.json()["error"]["code"] == "node.forbidden_target"


def test_metrics_requires_a_token(client: TestClient, monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "metrics_token", "")
    assert client.get("/api/metrics").status_code == 401


def test_operator_can_enable_mfa(client: TestClient, admin, login_as):
    import pyotp

    _user(admin, "mfa-op", OPERATOR_PASSWORD, "operator")
    operator = login_as(client, "mfa-op", OPERATOR_PASSWORD)
    status = operator.get("/api/auth/mfa")
    assert status.status_code == 200, status.text
    setup = operator.post("/api/auth/mfa/setup")
    assert setup.status_code == 200, setup.text
    code = pyotp.TOTP(setup.json()["secret"]).now()
    enabled = operator.post("/api/auth/mfa/enable", json={"code": code})
    assert enabled.status_code == 200, enabled.text
    assert operator.get("/api/auth/mfa").json()["enabled"] is True


def test_health_history_is_recorded_with_alerts_disabled(client: TestClient, admin, monkeypatch):
    from app import poller
    from app.health_service import process_health  # noqa: F401 - imported for parity
    from app.models import HealthSample
    from app.system_service import ensure_system_settings

    with SessionLocal() as db:
        row = ensure_system_settings(db)
        row.health_alerts_enabled = False
        db.commit()
        before = db.query(HealthSample).count()
    monkeypatch.setattr(poller, "_last_health", None)
    with SessionLocal() as db:
        poller.check_health(db)
        after = db.query(HealthSample).count()
    assert after == before + 1


def test_locale_files_are_not_heuristically_cached():
    from app.main import _static_cache_headers

    assert _static_cache_headers("locales/es.json") == {"Cache-Control": "no-cache"}
    assert _static_cache_headers("index.html") == {"Cache-Control": "no-cache"}
    assets = _static_cache_headers("assets/index-abc123.js")["Cache-Control"]
    assert "immutable" in assets
    assert _static_cache_headers("favicon.svg") == {}

