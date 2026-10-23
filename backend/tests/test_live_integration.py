from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("OXIDIZED_UI_TEST_URL")
USERNAME = os.environ.get("OXIDIZED_UI_TEST_USERNAME", "admin")
PASSWORD = os.environ.get("OXIDIZED_UI_TEST_PASSWORD")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not BASE_URL or not PASSWORD, reason="set OXIDIZED_UI_TEST_URL and OXIDIZED_UI_TEST_PASSWORD"),
]


def test_live_compose_stack() -> None:
    assert BASE_URL is not None
    assert PASSWORD is not None
    with httpx.Client(base_url=BASE_URL.rstrip("/"), headers={"Origin": BASE_URL.rstrip("/")}, timeout=30) as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        assert health.json()["database"] == "ok"
        assert health.json()["config_writable"] is True

        meta = client.get("/api/meta")
        assert meta.status_code == 200
        assert not meta.json()["setup_required"], "complete the first-run setup before running this test"

        login = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert login.status_code == 200, login.text
        session = client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["csrf_token"]

        status = client.get("/api/status")
        assert status.status_code == 200, status.text
        payload = status.json()
        assert payload["nodes"]["total"] >= 1, "create at least one node before running the contract test"
        assert payload["oxidized"]["container_running"] is True
        assert payload["oxidized"]["api_online"] is True
        assert payload["oxidized"]["state"] == "online"

        nodes = client.get("/api/nodes")
        assert nodes.status_code == 200
        assert nodes.json()["total"] >= 1
        node = nodes.json()["items"][0]
        if node.get("last_backup_at"):
            current = client.get(f"/api/nodes/{node['id']}/config")
            assert current.status_code == 200
            assert "node not found" not in current.text
            assert current.text.strip()

            versions = client.get(f"/api/nodes/{node['id']}/versions")
            assert versions.status_code == 200
            assert versions.json()["available"] is True
            if versions.json()["versions"]:
                oid = versions.json()["versions"][0]["oid"]
                content = client.get(f"/api/nodes/{node['id']}/versions/{oid}")
                assert content.status_code == 200
                assert "node not found" not in content.json()["content"]
                assert content.json()["content"].strip()

        config = client.get("/api/config")
        assert config.status_code == 200
        assert config.json()["applied"] is not None

        logs = client.get("/api/logs", params={"tail": 20})
        assert logs.status_code == 200
        assert isinstance(logs.json()["lines"], list)
