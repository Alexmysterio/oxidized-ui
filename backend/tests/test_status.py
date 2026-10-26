from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import NodeStatusCache
from app.oxidized import OxidizedClient, OxidizedNode
from tests.conftest import make_node


def _set_cache(node_id: int, **values) -> None:
    with SessionLocal() as db:
        cache = db.get(NodeStatusCache, node_id)
        if cache is None:
            cache = NodeStatusCache(node_id=node_id, observed_at=datetime.now(UTC))
            db.add(cache)
        for key, value in values.items():
            setattr(cache, key, value)
        db.commit()


def _create_node(admin: TestClient) -> int:
    created = admin.post("/api/nodes", json=make_node())
    assert created.status_code == 201, created.text
    return int(created.json()["node"]["id"])


def test_status_uses_last_success_when_oxidized_reports_never(client: TestClient, admin):
    node_id = _create_node(admin)
    finished = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    _set_cache(
        node_id,
        status="never",
        last_started_at=finished - timedelta(seconds=45),
        last_finished_at=finished,
        last_success_at=finished,
        last_failure_at=None,
        duration_seconds=45,
    )

    status = admin.get(f"/api/nodes/{node_id}/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status"] == "ok"
    assert body["last_status_raw"] == "never"
    assert body["last_success_at"] is not None
    assert body["last_finished_at"] is not None

    listed = admin.get("/api/nodes")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "ok"
    assert listed.json()["items"][0]["last_backup_at"] is not None


def test_status_prefers_the_most_recent_observed_outcome(client: TestClient, admin):
    node_id = _create_node(admin)
    success = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    _set_cache(
        node_id,
        status=None,
        last_success_at=success,
        last_failure_at=success + timedelta(hours=1),
    )

    body = admin.get(f"/api/nodes/{node_id}/status").json()
    assert body["status"] == "failed"


def test_status_is_never_without_a_live_or_observed_result(client: TestClient, admin):
    node_id = _create_node(admin)
    _set_cache(node_id, status=None, last_success_at=None, last_failure_at=None)

    body = admin.get(f"/api/nodes/{node_id}/status").json()
    assert body["status"] == "never"


def test_dashboard_counts_match_the_derived_status(client: TestClient, admin):
    node_id = _create_node(admin)
    _set_cache(node_id, status="never", last_success_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC))

    body = admin.get("/api/status").json()
    assert body["nodes"]["ok"] == 1
    assert body["nodes"]["never"] == 0
    assert body["nodes"]["failed"] == 0


def test_refresh_preserves_the_last_success_after_an_oxidized_restart(
    client: TestClient, admin, fake_clients
):
    node_id = _create_node(admin)
    started = datetime(2026, 10, 20, 11, 59, 15, tzinfo=UTC)
    finished = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    _set_cache(
        node_id,
        status="success",
        last_started_at=started,
        last_finished_at=finished,
        last_success_at=finished,
        last_failure_at=None,
        duration_seconds=45,
    )
    fake_clients.oxidized.nodes = [
        OxidizedNode(
            name="core-sw-01",
            full_name="core-sw-01",
            address="10.20.0.11",
            group=None,
            model="ios",
            status="never",
            last_started=None,
            last_finished=None,
            last_time=None,
            mtime=None,
        )
    ]

    body = admin.get(f"/api/nodes/{node_id}/status?refresh=true").json()
    assert body["status"] == "ok"
    assert body["last_status_raw"] == "never"
    assert body["last_success_at"] is not None
    assert body["last_finished_at"] is not None

    with SessionLocal() as db:
        cache = db.get(NodeStatusCache, node_id)
        assert cache is not None
        assert cache.duration_seconds == 45
        assert cache.last_started_at is not None


def test_list_nodes_reads_the_top_level_status_when_last_is_absent(monkeypatch):
    client = OxidizedClient()
    response = httpx.Response(
        200,
        json=[
            {
                "name": "core-sw-01",
                "status": "success",
                "time": "2026-10-20 12:00:00 UTC",
                "last": None,
                "mtime": "2026-10-20 12:00:00 UTC",
            }
        ],
    )
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: response)

    nodes = client.list_nodes()

    assert nodes[0].status == "success"
    assert nodes[0].last_finished == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def test_metrics_report_the_derived_status(client: TestClient, admin):
    node_id = _create_node(admin)
    _set_cache(node_id, status="never", last_success_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC))

    text = client.get("/api/metrics").text
    assert 'oxidized_ui_nodes_total{status="ok"} 1' in text
    assert 'oxidized_ui_nodes_total{status="never"}' not in text
    assert 'oxidized_ui_node_status{node="core-sw-01",status="ok"} 1' in text
