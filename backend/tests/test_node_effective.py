from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.node_effective_service import effective_settings
from tests.conftest import make_node


def _node(**overrides) -> SimpleNamespace:
    values = {
        "name": "ap-01",
        "address": "10.0.0.10",
        "model": "airos",
        "group_name": "APs",
        "input": None,
        "port": None,
        "username": None,
        "password_ciphertext": None,
        "enable_ciphertext": None,
        "vars_ciphertext": None,
        "output": None,
        "prompt": None,
        "timeout_seconds": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _config(**overrides) -> dict:
    values = {
        "input": {"default": "ssh, telnet"},
        "output": {"default": "git"},
        "timeout": 20,
        "prompt": "^global# $",
        "vars": {},
        "models": {},
        "username": None,
        "password": None,
    }
    values.update(overrides)
    return values


def _resolve(node: SimpleNamespace, config: dict | None = None, groups: dict | None = None) -> dict:
    return effective_settings(
        node,
        config=config or _config(),
        groups=groups or {},
        node_password=None,
        node_enable=None,
    )


def test_effective_values_use_node_over_every_other_scope():
    node = _node(
        input="ssh",
        port=2222,
        username="node-user",
        password_ciphertext=None,
        output="git",
        timeout_seconds=30,
        prompt="^node# $",
    )
    groups = {
        "APs": {
            "username": "group-user",
            "password": "group-pass",
            "models": {"airos": {"username": "model-user", "password": "model-pass"}},
        }
    }
    result = effective_settings(
        node,
        config=_config(username="global-user", password="global-pass"),
        groups=groups,
        node_password="node-pass",
        node_enable="node-enable",
    )

    assert result["input"] == {"value": "ssh", "source": "node", "source_detail": None}
    assert result["port"] == {"value": "2222", "source": "node", "source_detail": None}
    assert result["username"] == {"value": "node-user", "source": "node", "source_detail": None}
    assert result["password"] == {"set": True, "source": "node", "source_detail": None}
    assert result["enable"]["set"] is True
    assert result["enable"]["source"] == "node"
    assert result["output"] == {"value": "git", "source": "node", "source_detail": None}
    assert result["timeout_seconds"] == {"value": 30, "source": "node", "source_detail": None}
    assert result["prompt"] == {"value": "^node# $", "source": "node", "source_detail": None}


def test_effective_credentials_fall_back_to_group_model_then_group():
    groups = {
        "APs": {
            "username": "group-user",
            "password": "group-pass",
            "models": {"airos": {"username": "model-user", "password": "model-pass"}},
        }
    }
    result = _resolve(_node(), groups=groups)

    assert result["username"] == {"value": "model-user", "source": "group_model", "source_detail": "APs/airos"}
    assert result["password"] == {"set": True, "source": "group_model", "source_detail": "APs/airos"}

    groups["APs"]["models"] = {}
    result = _resolve(_node(), groups=groups)
    assert result["username"] == {"value": "group-user", "source": "group", "source_detail": "APs"}
    assert result["password"] == {"set": True, "source": "group", "source_detail": "APs"}


def test_effective_credentials_fall_back_to_model_and_global_config():
    config = _config(
        models={"airos": {"username": "model-user", "password": "model-pass"}},
        username="global-user",
        password="global-pass",
    )
    result = _resolve(_node(), config=config)
    assert result["username"] == {"value": "model-user", "source": "model", "source_detail": "airos"}
    assert result["password"] == {"set": True, "source": "model", "source_detail": "airos"}

    result = _resolve(_node(), config=_config(username="global-user", password="global-pass"))
    assert result["username"] == {"value": "global-user", "source": "config", "source_detail": "username"}
    assert result["password"] == {"set": True, "source": "config", "source_detail": "password"}


def test_effective_input_output_timeout_and_port_come_from_config_defaults():
    result = _resolve(_node())

    assert result["input"] == {"value": "ssh, telnet", "source": "config", "source_detail": "input.default"}
    assert result["output"] == {"value": "git", "source": "config", "source_detail": "output.default"}
    assert result["timeout_seconds"] == {"value": 20, "source": "config", "source_detail": "timeout"}
    assert result["port"] == {"value": "22 (SSH), 23 (TELNET)", "source": "default", "source_detail": None}
    assert result["prompt"] == {"value": None, "source": "model_or_config", "source_detail": None}


def test_effective_port_uses_group_vars():
    groups = {"APs": {"vars": {"ssh_port": 2222}, "models": {"airos": {"vars": {"telnet_port": 2323}}}}}
    result = _resolve(_node(), groups=groups)
    assert result["port"] == {
        "value": "2222 (SSH), 2323 (TELNET)",
        "source": "mixed",
        "source_detail": None,
    }


def test_effective_passwords_are_never_returned():
    result = _resolve(_node(), config=_config(password="super-secret"))
    serialized = json.dumps(result)
    assert "super-secret" not in serialized
    assert result["password"]["set"] is True
    assert "value" not in result["password"]


def test_node_detail_exposes_effective_values_for_operators(client: TestClient, admin):
    created = admin.post(
        "/api/nodes",
        json=make_node(
            name="ap-01",
            model="airos",
            group_name=None,
            input=None,
            port=None,
            username=None,
            password=None,
            enable=None,
            output=None,
            prompt=None,
            timeout_seconds=None,
            vars={},
        ),
    )
    assert created.status_code == 201, created.text
    node_id = created.json()["node"]["id"]

    body = admin.get(f"/api/nodes/{node_id}").json()
    effective = body["effective"]
    assert effective["input"]["value"] == "ssh, telnet"
    assert effective["input"]["source"] == "config"
    assert effective["output"]["value"] == "git"
    assert effective["timeout_seconds"]["value"] == 20
    assert effective["port"]["value"] == "22 (SSH), 23 (TELNET)"
    assert effective["username"]["source"] == "missing"
    assert effective["password"]["set"] is False
    assert effective["prompt"]["source"] == "model_or_config"


def test_node_detail_hides_effective_values_from_viewers(client: TestClient, admin, login_as):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    node_id = created.json()["node"]["id"]
    viewer_user = admin.post(
        "/api/users",
        json={"username": "viewer-one", "password": "ViewerPassw0rd!", "role": "viewer", "language": "es"},
    )
    assert viewer_user.status_code == 201, viewer_user.text

    viewer = login_as(client, "viewer-one", "ViewerPassw0rd!")
    body = viewer.get(f"/api/nodes/{node_id}").json()
    assert "effective" not in body


def test_node_list_does_not_include_effective_values(client: TestClient, admin):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201

    body = admin.get("/api/nodes").json()
    assert "effective" not in body["items"][0]
