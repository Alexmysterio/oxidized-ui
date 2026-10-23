from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD, make_node

OPERATOR_PASSWORD = "OperatorPassw0rd!"
VIEWER_PASSWORD = "ViewerPassw0rd!"


def _create_user(admin, username: str, password: str, role: str) -> int:
    response = admin.post(
        "/api/users",
        json={"username": username, "password": password, "role": role, "language": "es"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_rbac_is_enforced_in_backend(client: TestClient, admin, login_as, fake_clients):
    _create_user(admin, "oper", OPERATOR_PASSWORD, "operator")
    _create_user(admin, "view", VIEWER_PASSWORD, "viewer")
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    node_id = created.json()["node"]["id"]

    operator = login_as(client, "oper", OPERATOR_PASSWORD)
    operator_node = operator.post("/api/nodes", json=make_node(name="oper-node"))
    assert operator_node.status_code == 201
    assert operator.get("/api/logs").status_code == 200
    assert operator.get("/api/groups").status_code == 200
    forbidden_config = operator.get("/api/config")
    assert forbidden_config.status_code == 403
    assert forbidden_config.json()["error"]["code"] == "auth.forbidden"
    assert operator.get("/api/users").status_code == 403
    assert operator.get("/api/audit").status_code == 403
    assert operator.post("/api/oxidized/restart").status_code == 403

    viewer = login_as(client, "view", VIEWER_PASSWORD)
    visible = viewer.get(f"/api/nodes/{node_id}")
    assert visible.status_code == 200
    payload = visible.json()
    assert "username" not in payload
    assert "vars" not in payload
    assert "has_password" not in payload
    assert payload["input"] == "ssh"
    assert payload["port"] == 22
    assert viewer.post("/api/nodes", json=make_node(name="nope")).status_code == 403
    assert viewer.get("/api/logs").status_code == 403
    assert viewer.get("/api/jobs").status_code == 403
    assert viewer.get("/api/groups").status_code == 403
    assert viewer.get("/api/config").status_code == 403

    # The viewer can still read the dashboard, nodes and version endpoints.
    assert viewer.get("/api/status").status_code == 200
    assert viewer.get("/api/nodes").status_code == 200


def test_last_admin_protections(client: TestClient, admin):
    me = admin.get("/api/auth/session").json()["user"]
    last = admin.delete(f"/api/users/{me['id']}")
    assert last.status_code == 409
    assert last.json()["error"]["code"] == "user.self_delete"
    created = admin.post(
        "/api/users",
        json={"username": "secondadmin", "password": ADMIN_PASSWORD, "role": "admin", "language": "es"},
    )
    assert created.status_code == 201
    demote = admin.patch(
        f"/api/users/{me['id']}",
        json={"role": "viewer"},
    )
    # There is still another active admin, so this is allowed.
    assert demote.status_code == 200
