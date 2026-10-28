from __future__ import annotations

import json
import struct
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.docker_api import _Demuxer, parse_level, split_timestamp
from app.errors import AppError
from app.oxidized import OxidizedClient, OxidizedNode, OxidizedVersion
from app.version_service import _live_group
from tests.conftest import make_node


def test_oxidized_client_contract(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path == "/nodes.json":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "r1",
                        "full_name": "core/r1",
                        "ip": "10.0.0.1",
                        "group": "core",
                        "model": "ios",
                        "last": {
                            "start": "2026-10-21 16:00:00 +0000",
                            "end": "2026-10-21 16:00:10 +0000",
                            "status": "success",
                            "time": 10,
                        },
                        "vars": {"password": "do-not-leak"},
                        "mtime": "2026-10-21 16:00:11 +0000",
                    }
                ],
            )
        if path == "/reload.json":
            return httpx.Response(200, json="reloaded list of nodes")
        if path.startswith("/node/next/"):
            return httpx.Response(200, json="ok")
        if path.startswith("/node/fetch/"):
            assert path == "/node/fetch/core/r1.json"
            return httpx.Response(200, json=["line one\n", "line two\n"])
        if path == "/node/version":
            assert request.url.params["node_full"] == "core/r1"
            return httpx.Response(
                200,
                json=[{"oid": "abc123", "time": "2026-10-21 16:00:10 +0000", "author": "me", "message": "m"}],
            )
        if path == "/node/version/view":
            assert request.url.params["oid"] == "abc123"
            return httpx.Response(200, json=["hostname r1\n", "interface Gi0/1\n"])
        if path == "/nodes/conf_search.json":
            return httpx.Response(200, json=[{"node": "r1", "full_name": "core/r1"}])
        return httpx.Response(404)

    client = OxidizedClient("http://oxidized.test")
    monkeypatch.setattr(
        client,
        "_client",
        lambda: httpx.Client(
            base_url="http://oxidized.test",
            transport=httpx.MockTransport(handler),
            timeout=5,
        ),
    )
    nodes = client.list_nodes()
    assert nodes[0].name == "r1"
    assert nodes[0].group == "core"
    assert not hasattr(nodes[0], "vars")
    assert nodes[0].status == "success"
    client.reload()
    client.next_node("r1")
    assert client.fetch_config("r1", "core") == "line one\nline two\n"
    versions = client.versions("r1", "core")
    assert versions[0].oid == "abc123"
    assert client.version_content("r1", "core", "abc123") == "hostname r1\ninterface Gi0/1\n"
    assert client.search_configs("interface") == [{"name": "r1", "full_name": "core/r1"}]
    assert len(calls) >= 7


def test_oxidized_client_omits_implicit_default_group(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path == "/node/fetch/r1.json":
            return httpx.Response(200, json=["hostname r1\n"])
        if path == "/node/version":
            assert request.url.params["node_full"] == "r1"
            return httpx.Response(
                200,
                json=[{"oid": "abc123", "time": "2026-10-21 16:00:10 +0000", "author": "me", "message": "m"}],
            )
        if path == "/node/version/view":
            assert request.url.params["group"] == ""
            return httpx.Response(200, json=["hostname r1\n"])
        return httpx.Response(404)

    client = OxidizedClient("http://oxidized.test")
    monkeypatch.setattr(
        client,
        "_client",
        lambda: httpx.Client(base_url="http://oxidized.test", transport=httpx.MockTransport(handler)),
    )
    assert client.fetch_config("r1", "default") == "hostname r1\n"
    assert client.versions("r1", "default")[0].oid == "abc123"
    assert client.version_content("r1", "default", "abc123") == "hostname r1\n"
    assert [call.url.path for call in calls] == ["/node/fetch/r1.json", "/node/version", "/node/version/view"]


def test_live_group_normalizes_default(monkeypatch):
    class FakeClient:
        def __init__(self, group):
            self.group = group

        def list_nodes(self):
            return [
                OxidizedNode(
                    name="r1",
                    full_name="r1",
                    address=None,
                    group=self.group,
                    model="ios",
                    status=None,
                    last_started=None,
                    last_finished=None,
                    last_time=None,
                    mtime=None,
                )
            ]

    node = type("FakeNode", (), {"name": "r1"})()
    assert _live_group(FakeClient("default"), node) is None
    assert _live_group(FakeClient(None), node) is None
    assert _live_group(FakeClient("core"), node) == "core"


def test_oxidized_client_rejects_marker_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["node not found"])

    client = OxidizedClient("http://oxidized.test")
    monkeypatch.setattr(
        client,
        "_client",
        lambda: httpx.Client(base_url="http://oxidized.test", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(AppError) as caught:
        client.fetch_config("r1")
    assert caught.value.code == "oxidized.bad_response"
    assert caught.value.params == {"reason": "node_not_found"}


def test_oxidized_client_upstream_errors(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="broken")

    client = OxidizedClient("http://oxidized.test")
    monkeypatch.setattr(
        client,
        "_client",
        lambda: httpx.Client(base_url="http://oxidized.test", transport=httpx.MockTransport(handler)),
    )
    try:
        client.list_nodes()
    except Exception as exc:
        from app.errors import AppError

        assert isinstance(exc, AppError)
        assert exc.code == "oxidized.bad_response"
    else:
        raise AssertionError("expected AppError")


def test_docker_demux_and_log_parsing():
    line = "2026-10-21T16:00:00.123456789Z W [123:456] something broke\n"
    data = line.encode()
    frame = b"\x02\x00\x00\x00" + struct.pack(">I", len(data)) + data
    demux = _Demuxer()
    assert demux.feed(frame) == [("stderr", data)]
    timestamp, text = split_timestamp(data.decode().strip())
    assert timestamp is not None
    assert "W [" in text
    assert parse_level(text, "stderr") == "warn"


def test_internal_log_endpoints(client: TestClient, admin):
    snapshot = admin.get("/api/logs")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert len(body["lines"]) == 2
    errors = admin.get("/api/logs?level=error")
    assert errors.status_code == 200
    assert len(errors.json()["lines"]) == 1
    assert errors.json()["lines"][0]["level"] == "error"
    download = admin.get("/api/logs/download")
    assert download.status_code == 200
    assert "connection failed" in download.text
    assert "attachment" in download.headers["content-disposition"].lower()

    with admin.raw.stream("GET", "/api/logs/stream", headers=admin.headers) as response:
        assert response.status_code == 200
        text = "\n".join(response.iter_lines())
    assert "event: ready" in text
    assert "event: log" in text
    assert "Oxidized starting" in text


def test_versions_diff_and_download(client: TestClient, admin, fake_clients):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    node = created.json()["node"]
    fake_clients.oxidized.nodes = [
        OxidizedNode(
            name="core-sw-01",
            full_name="core-sw-01",
            address="10.20.0.11",
            group=None,
            model="ios",
            status="success",
            last_started=datetime(2026, 10, 21, tzinfo=UTC),
            last_finished=datetime(2026, 10, 21, 0, 1, tzinfo=UTC),
            last_time=1,
            mtime=None,
        )
    ]
    fake_clients.oxidized.versions_map["core-sw-01"] = [
        OxidizedVersion("a1b2c3", datetime(2026, 10, 21, 0, 1, tzinfo=UTC), "me", "new"),
        OxidizedVersion("d4e5f6", datetime(2026, 10, 20, 0, 1, tzinfo=UTC), "me", "old"),
    ]
    fake_clients.oxidized.contents = {
        "a1b2c3": "hostname new\ninterface Gi0/1\n",
        "d4e5f6": "hostname old\ninterface Gi0/1\n",
    }
    fake_clients.oxidized.current_configs = {"core-sw-01": "hostname current\ninterface Gi0/2\n"}
    versions = admin.get(f"/api/nodes/{node['id']}/versions")
    assert versions.status_code == 200, versions.text
    assert versions.json()["available"] is True
    assert len(versions.json()["versions"]) == 2
    content = admin.get(f"/api/nodes/{node['id']}/versions/a1b2c3")
    assert content.status_code == 200
    assert "hostname new" in content.json()["content"]
    diff = admin.get(f"/api/nodes/{node['id']}/diff?from_oid=d4e5f6&to_oid=a1b2c3")
    assert diff.status_code == 200, diff.text
    assert diff.json()["stats"]["additions"] >= 1
    download = admin.get(f"/api/nodes/{node['id']}/download?oid=a1b2c3")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    current = admin.get(f"/api/nodes/{node['id']}/config")
    assert current.status_code == 200
    assert "interface Gi0/2" in current.text
    assert "node not found" not in current.text

    golden = admin.put(f"/api/nodes/{node['id']}/golden", json={"oid": "a1b2c3"})
    assert golden.status_code == 200, golden.text
    assert golden.json()["golden_oid"] == "a1b2c3"
    detail = admin.get(f"/api/nodes/{node['id']}")
    assert detail.json()["golden_oid"] == "a1b2c3"
    missing = admin.put(f"/api/nodes/{node['id']}/golden", json={"oid": "ffffff"})
    assert missing.status_code == 404
    cleared = admin.put(f"/api/nodes/{node['id']}/golden", json={"oid": None})
    assert cleared.status_code == 200
    assert cleared.json()["golden_oid"] is None


def test_search_and_system_settings(client: TestClient, admin, fake_clients):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    fake_clients.oxidized.search_results = [{"name": "core-sw-01", "full_name": "core-sw-01"}]
    search = admin.post("/api/search/configs", json={"query": "interface"})
    assert search.status_code == 200
    assert search.json()["matches"][0]["name"] == "core-sw-01"
    glob = admin.get("/api/search?q=core")
    assert glob.status_code == 200
    assert glob.json()["nodes"][0]["name"] == "core-sw-01"
    settings_response = admin.get("/api/system/settings")
    assert settings_response.status_code == 200
    invalid = admin.patch("/api/system/settings", json={"oxidized_api_url": "not-a-url"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "system.invalid_setting"
    updated = admin.patch("/api/system/settings", json={"timezone": "Europe/Madrid"})
    assert updated.status_code == 200
    assert updated.json()["timezone"] == "Europe/Madrid"
    tested = admin.post("/api/system/test", json={"target": "oxidized"})
    assert tested.status_code == 200


def test_audit_contains_no_secrets(client: TestClient, admin):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    audit = admin.get("/api/audit")
    assert audit.status_code == 200
    body = audit.json()
    assert body["total"] >= 2
    serialized = json.dumps(body)
    assert "device-password" not in serialized
    assert "enable-password" not in serialized
    assert "setup.completed" in {item["action_code"] for item in body["items"]}


def test_dashboard_and_node_status_are_observed(client: TestClient, admin, fake_clients):
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201
    node = created.json()["node"]
    fake_clients.oxidized.nodes = [
        OxidizedNode(
            name="core-sw-01",
            full_name="core-sw-01",
            address="10.20.0.11",
            group=None,
            model="ios",
            status="success",
            last_started=datetime(2026, 10, 21, tzinfo=UTC),
            last_finished=datetime(2026, 10, 21, 0, 1, tzinfo=UTC),
            last_time=60,
            mtime=datetime(2026, 10, 21, 0, 2, tzinfo=UTC),
        )
    ]
    status = admin.get("/api/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["oxidized"]["state"] == "online"
    assert body["nodes"]["total"] == 1
    assert body["nodes"]["ok"] == 1
    assert body["backups"]["last_success_at"] is not None
    assert len(body["activity"]) >= 1
    node_status = admin.get(f"/api/nodes/{node['id']}/status?refresh=true")
    assert node_status.status_code == 200
    assert node_status.json()["status"] == "ok"
