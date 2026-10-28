from __future__ import annotations

import csv
import io
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.crypto import decrypt_optional
from app.models import Node
from app.settings import settings
from tests.conftest import make_node


def test_node_crud_write_only_secrets_and_internal_source(client: TestClient, admin, fake_clients, db_session):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201, created.text
    node = created.json()["node"]
    assert node["name"] == "core-sw-01"
    assert node["has_password"] is True
    assert node["has_enable"] is True
    assert "password" not in node
    assert "enable" not in node
    assert node["warnings"] == []
    assert fake_clients.oxidized.reload_calls == 1

    with db_session as db:
        row = db.scalar(select(Node).where(Node.id == node["id"]))
        assert row is not None
        assert row.password_ciphertext != "device-password"
        assert decrypt_optional(row.password_ciphertext) == "device-password"

    unauthorized = client.get("/api/internal/source/nodes")
    assert unauthorized.status_code == 401
    source = client.get(
        "/api/internal/source/nodes",
        headers={"X-Oxidized-Source-Token": settings.oxidized_source_token},
    )
    assert source.status_code == 200
    payload = source.json()
    assert payload[0]["name"] == "core-sw-01"
    assert payload[0]["password"] == "device-password"
    assert payload[0]["vars"]["enable"] == "enable-password"
    assert payload[0]["vars"]["ssh_port"] == 22

    listed = admin.get("/api/nodes")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = admin.patch(f"/api/nodes/{node['id']}", json={"port": 2222})
    assert updated.status_code == 200, updated.text
    assert updated.json()["node"]["has_password"] is True
    source = client.get(
        "/api/internal/source/nodes",
        headers={"X-Oxidized-Source-Token": settings.oxidized_source_token},
    )
    assert source.json()[0]["vars"]["ssh_port"] == 2222

    cleared = admin.patch(f"/api/nodes/{node['id']}", json={"clear_password": True})
    assert cleared.status_code == 200
    assert cleared.json()["node"]["has_password"] is False

    deleted = admin.delete(f"/api/nodes/{node['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1
    assert deleted.json()["reload_status"] == "recovered"
    assert fake_clients.docker.restart_calls == 1
    assert admin.get("/api/nodes").json()["total"] == 0


def test_node_validation_and_duplicates(client: TestClient, admin):
    first = admin.post("/api/nodes", json=make_node())
    assert first.status_code == 201
    duplicate = admin.post("/api/nodes", json=make_node(name="CORE-SW-01"))
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "node.duplicate_name"
    invalid = admin.post("/api/nodes", json=make_node(name="bad/name"))
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] in {"node.invalid_name", "validation.failed"}
    bad_model = admin.post("/api/nodes", json=make_node(name="r2", model=" "))
    assert bad_model.status_code == 422


def test_node_bulk_actions(client: TestClient, admin, fake_clients):
    for index in range(3):
        response = admin.post("/api/nodes", json=make_node(name=f"r{index}"))
        assert response.status_code == 201, response.text
    ids = [item["id"] for item in admin.get("/api/nodes").json()["items"]]
    backup = admin.post("/api/nodes/bulk", json={"action": "backup", "ids": ids})
    assert backup.status_code == 202
    assert "job_id" in backup.json()
    for _ in range(50):
        job = admin.get(f"/api/jobs/{backup.json()['job_id']}")
        if job.json()["status"] in {"succeeded", "failed"}:
            break
    assert job.status_code == 200
    assert set(fake_clients.oxidized.next_calls) == {"r0", "r1", "r2"}
    deleted = admin.post("/api/nodes/bulk", json={"action": "delete", "ids": ids})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 3


def test_node_bulk_test_connection(client: TestClient, admin, monkeypatch):
    for index in range(2):
        assert admin.post("/api/nodes", json=make_node(name=f"t{index}")).status_code == 201
    ids = [item["id"] for item in admin.get("/api/nodes").json()["items"]]
    monkeypatch.setattr(
        "app.node_test_service.test_connection",
        lambda _db, node: {
            "authenticated": True,
            "message": "ok",
            "ping": True,
            "tcp": True,
            "ssh": True,
        },
    )
    response = admin.post("/api/nodes/bulk", json={"action": "test_connection", "ids": ids})
    assert response.status_code == 200, response.text
    assert response.json()["tested"] == 2
    assert response.json()["succeeded"] == 2
    assert response.json()["failed"] == []


def test_csv_import_export_never_exports_secrets(client: TestClient, admin):
    exported = admin.get("/api/nodes/export.csv")
    assert exported.status_code == 200
    assert "password" in exported.text.splitlines()[0]
    csv_body = (
        "name,address,model,group,input,port,username,password,enable,vars\n"
        'r1,10.0.0.1,ios,,ssh,22,netops,secret-pass,secret-enable,"{""remove_secret"":true}"\n'
    )
    imported = admin.post(
        "/api/nodes/import",
        files={"file": ("nodes.csv", csv_body, "text/csv")},
        data={"mode": "skip_existing", "dry_run": "false"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 1
    assert imported.json()["errors"] == []
    exported = admin.get("/api/nodes/export.csv")
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert rows[0]["name"] == "r1"
    assert rows[0]["password"] == ""
    assert rows[0]["enable"] == ""
    assert json.loads(rows[0]["vars"])["remove_secret"] is True


def test_node_source_optional_path_and_auth(client: TestClient, admin):
    assert admin.post("/api/nodes", json=make_node()).status_code == 201
    headers = {"X-Oxidized-Source-Token": settings.oxidized_source_token}
    one = client.get("/api/internal/source/nodes/core-sw-01", headers=headers)
    assert one.status_code == 200
    assert len(one.json()) == 1
    missing = client.get(
        "/api/internal/source/nodes/core-sw-01",
        headers={"X-Oxidized-Source-Token": "wrong"},
    )
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "internal_source.unauthorized"


def test_node_ping_endpoint(client: TestClient, admin, fake_clients, monkeypatch):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    node_id = created.json()["node"]["id"]

    monkeypatch.setattr(
        "app.routers.nodes.ping_host",
        lambda address: {
            "reachable": True,
            "address": address,
            "sent": 3,
            "received": 3,
            "rtt_ms": 1.25,
            "message": "ok",
        },
    )
    response = admin.post(f"/api/nodes/{node_id}/ping")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "reachable": True,
        "address": "10.20.0.11",
        "sent": 3,
        "received": 3,
        "rtt_ms": 1.25,
        "message": "ok",
    }

    audit = admin.get("/api/audit", params={"action": "node.ping_tested"})
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert audit.json()["items"][0]["target_id"] == str(node_id)


def test_connection_test_includes_ping(client: TestClient, admin, db_session, monkeypatch):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    node_id = created.json()["node"]["id"]

    from app import node_test_service

    monkeypatch.setattr(
        node_test_service,
        "ping_host",
        lambda _address: {
            "reachable": True,
            "address": "10.20.0.11",
            "sent": 3,
            "received": 3,
            "rtt_ms": 2.5,
            "message": "ok",
        },
    )

    def unreachable(*_args, **_kwargs):
        raise OSError("unreachable")

    monkeypatch.setattr(node_test_service.socket, "create_connection", unreachable)

    with db_session as db:
        node = db.get(Node, node_id)
        result = node_test_service.test_connection(db, node)

    assert result["ping"] is True
    assert result["ping_rtt_ms"] == 2.5
    assert result["ping_message"] == "ok"
    assert result["tcp"] is False
    assert result["message"] == "tcp: OSError"
