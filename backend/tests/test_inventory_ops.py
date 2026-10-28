from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.facts_service import parse_facts
from app.models import Node, SiteLocation
from app.node_service import migrate_legacy_coordinate_tags
from app.oxidized import OxidizedNode
from app.site_service import migrate_site_coordinates
from app.timeutil import utcnow
from tests.conftest import make_node


def _node(admin, name: str, group: str | None = None, model: str = "ios") -> int:
    response = admin.post("/api/nodes", json=make_node(name=name, model=model))
    assert response.status_code == 201, response.text
    node_id = int(response.json()["node"]["id"])
    if group:
        with SessionLocal() as db:
            node = db.get(Node, node_id)
            assert node is not None
            node.group_name = group
            db.commit()
    return node_id


def _live(name: str, group: str | None = None, model: str = "ios") -> OxidizedNode:
    return OxidizedNode(
        name=name,
        full_name=name,
        address="10.0.0.1",
        group=group,
        model=model,
        status="success",
        last_started=utcnow(),
        last_finished=utcnow(),
        last_time=1.0,
        mtime=utcnow(),
    )


def _wait(admin, job_id: int) -> dict:
    job: dict = {}
    for _ in range(100):
        job = admin.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            break
        import time

        time.sleep(0.05)
    return job


def test_node_tags_filter_and_bulk(client: TestClient, admin):
    created = admin.post(
        "/api/nodes",
        json=make_node(name="tagged-1", tags={"site": "madrid", "criticality": "high"}),
    )
    assert created.status_code == 201, created.text
    assert created.json()["node"]["tags"] == {"Site": "Madrid", "Criticality": "High"}

    listed = admin.get("/api/nodes", params={"tag_key": "Site", "tag_value": "madrid"}).json()
    assert [item["name"] for item in listed["items"]] == ["tagged-1"]

    other = _node(admin, "tagged-2")
    updated = admin.post(
        "/api/nodes/bulk",
        json={"action": "set_tags", "ids": [other], "tags": {"site": "barcelona"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["updated"] == 1

    catalog = admin.get("/api/nodes/tags").json()["items"]
    assert {"key": "Site", "value": "Barcelona", "count": 1} in catalog
    filtered = admin.get("/api/nodes", params={"tag_key": "Site", "tag_value": "barcelona"}).json()
    assert filtered["items"][0]["name"] == "tagged-2"


def test_node_templates_crud_and_apply(client: TestClient, admin, fake_clients):
    created = admin.post(
        "/api/node-templates",
        json={
            "name": "ios-access",
            "model": "ios",
            "input": "ssh",
            "port": 22,
            "username": "netops",
            "vars": {"ssh_no_keepalive": True},
        },
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    applied = admin.post(f"/api/node-templates/{template_id}/apply", json={"name": "access-1", "address": "10.0.0.9"})
    assert applied.status_code == 201, applied.text
    node = applied.json()["node"]
    assert node["model"] == "ios"
    assert node["port"] == 22
    assert node["tags"] == {}

    templates = admin.get("/api/node-templates").json()["items"]
    assert templates[0]["name"] == "ios-access"
    assert admin.delete(f"/api/node-templates/{template_id}").status_code == 204


def test_facts_parse_collect_and_search(client: TestClient, admin, fake_clients):
    parsed = parse_facts(
        "Cisco IOS Software, Version 15.2(4)E7\nProcessor board ID FTX1234ABCD\nrouter uptime is 3 weeks, 2 days\n"
    )
    assert parsed["serial"] == "FTX1234ABCD"
    assert parsed["os_version"].startswith("15.2")
    assert "3 weeks" in (parsed["uptime"] or "")

    node_id = _node(admin, "facts-1")
    fake_clients.oxidized.nodes = [_live("facts-1")]
    fake_clients.oxidized.current_configs["facts-1"] = (
        "hostname facts-1\nCisco IOS Software, Version 17.3.4\nProcessor board ID ABC123XYZ\n"
        "facts-1 uptime is 1 day, 2 hours\n"
    )

    collected = admin.post(f"/api/nodes/{node_id}/facts/collect")
    assert collected.status_code == 200, collected.text
    assert collected.json()["serial"] == "ABC123XYZ"

    detail = admin.get(f"/api/nodes/{node_id}").json()
    assert detail["facts"]["os_version"] == "17.3.4"

    search = admin.get("/api/search", params={"q": "ABC123XYZ"}).json()
    assert [item["name"] for item in search["nodes"]] == ["facts-1"]


def test_job_priority_rules_apply(client: TestClient, admin):
    node_id = _node(admin, "prio-1", group="critical")
    rule = admin.post(
        "/api/backups/priority-rules",
        json={"scope_type": "group", "scope_key": "critical", "priority": 1},
    )
    assert rule.status_code == 201, rule.text

    tag_rule = admin.post(
        "/api/backups/priority-rules",
        json={"scope_type": "tag", "scope_key": "tier", "scope_value": "edge", "priority": 3},
    )
    assert tag_rule.status_code == 201, tag_rule.text

    job = admin.post(f"/api/nodes/{node_id}/backup")
    assert job.status_code == 202, job.text
    assert job.json()["priority"] == 1

    rules = admin.get("/api/backups/priority-rules").json()["items"]
    assert len(rules) == 2
    assert admin.delete(f"/api/backups/priority-rules/{rule.json()['id']}").status_code == 204


def test_reconciliation_detects_and_imports(client: TestClient, admin, fake_clients):
    _node(admin, "known-1")
    fake_clients.oxidized.nodes = [_live("known-1"), _live("new-1", group="core")]

    report = admin.get("/api/reconciliation")
    assert report.status_code == 200, report.text
    body = report.json()
    assert [item["name"] for item in body["missing_in_ui"]] == ["new-1"]
    assert body["missing_in_oxidized"] == []

    imported = admin.post("/api/reconciliation/import", json={"names": ["new-1"]})
    assert imported.status_code == 202, imported.text
    assert imported.json()["imported"][0]["name"] == "new-1"
    with SessionLocal() as db:
        assert db.scalar(select(Node).where(Node.name == "new-1")) is not None


def test_health_panel(client: TestClient, admin):
    health = admin.get("/api/system/health")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["disk"]["percent"] >= 0
    assert body["jobs"]["queued"] >= 0
    assert "migration" in body
    assert admin.get("/api/system/settings").json()["backup_batch_size"] >= 1


def test_scheduled_report_and_download(client: TestClient, admin):
    response = admin.post("/api/system/reports/run")
    assert response.status_code == 202, response.text
    job = _wait(admin, response.json()["id"])
    assert job["status"] == "succeeded", job

    listing = admin.get("/api/system/reports")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert items
    formats = {item["format"] for item in items}
    assert formats == {"csv", "pdf"}
    csv_item = next(item for item in items if item["format"] == "csv")

    download = admin.get(f"/api/system/reports/{csv_item['filename']}")
    assert download.status_code == 200
    assert "summary" in download.text and "generated_at" in download.text
    pdf_item = next(item for item in items if item["format"] == "pdf")
    pdf = admin.get(f"/api/system/reports/{pdf_item['filename']}")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_export_verification(client: TestClient, admin):
    configured = admin.put(
        "/api/system/export",
        json={
            "kind": "sftp",
            "interval_hours": 24,
            "enabled": False,
            "config": {
                "host": "backup.example.invalid",
                "username": "oxidized",
                "password": "secret-password",
                "remote_dir": "/backups",
                "passphrase": "export-passphrase-123",
            },
        },
    )
    assert configured.status_code == 200, configured.text

    verified = admin.post("/api/system/export/verify", json={})
    assert verified.status_code == 200, verified.text
    assert verified.json()["ok"] is True
    assert verified.json()["has_database"] is True
    assert len(verified.json()["sha256"]) == 64

def test_sites_grouping_and_map(client: TestClient, admin):
    first = admin.post("/api/nodes", json=make_node(name="site-a", tags={"site": "madrid"}))
    assert first.status_code == 201, first.text
    second = admin.post("/api/nodes", json=make_node(name="site-b", tags={"site": "madrid"}))
    assert second.status_code == 201, second.text
    admin.post("/api/nodes", json=make_node(name="site-c", tags={"site": "barcelona"}))
    admin.post("/api/nodes", json=make_node(name="site-d", tags={"site": "barcelona"}))

    saved = admin.put(
        "/api/nodes/sites",
        json={"site": "Madrid", "coordinates": "40\u00b030'00.0\"N 3\u00b036'00.0\"W"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["latitude"] == pytest.approx(40.5)
    assert admin.put(
        "/api/nodes/sites",
        json={"site": "Barcelona", "coordinates": "41.4, 2.2"},
    ).status_code == 200

    sites = admin.get("/api/nodes/sites", params={"tag": "Site"}).json()
    assert sites["total"] == 4
    names = {site["name"]: site for site in sites["sites"]}
    assert names["Madrid"]["count"] == 2
    assert names["Madrid"]["latitude"] == pytest.approx(40.5)
    assert names["Madrid"]["longitude"] == pytest.approx(-3.6)
    assert {node["name"] for node in names["Madrid"]["nodes"]} == {"site-a", "site-b"}
    assert "latitude" not in names["Madrid"]["nodes"][0]
    assert names["Barcelona"]["count"] == 2
    assert names["Barcelona"]["latitude"] == 41.4


def test_site_coordinates_validation_and_clear(client: TestClient, admin):
    admin.post("/api/nodes", json=make_node(name="site-validation", tags={"site": "valencia"}))

    invalid = admin.put(
        "/api/nodes/sites",
        json={"site": "Valencia", "coordinates": "not coordinates"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "site.invalid_coordinates"

    saved = admin.put(
        "/api/nodes/sites",
        json={"site": "Valencia", "coordinates": "39.4699, -0.3763"},
    )
    assert saved.status_code == 200, saved.text

    cleared = admin.put("/api/nodes/sites", json={"site": "Valencia", "coordinates": None})
    assert cleared.status_code == 200
    assert cleared.json()["latitude"] is None
    site = next(
        item
        for item in admin.get("/api/nodes/sites", params={"tag": "Site"}).json()["sites"]
        if item["name"] == "Valencia"
    )
    assert site["latitude"] is None
    assert site["longitude"] is None


def test_node_coordinate_tags_are_discarded(client: TestClient, admin):
    created = admin.post(
        "/api/nodes",
        json=make_node(
            name="coordinate-tags",
            tags={"site": "Madrid", "coordinates": "40.4, -3.7", "latitude": "40.4", "longitude": "-3.7"},
        ),
    )
    assert created.status_code == 201, created.text
    assert created.json()["node"]["tags"] == {"Site": "Madrid"}


def test_legacy_coordinate_tags_are_migrated_and_removed(client: TestClient, admin):
    node_id = _node(admin, "legacy-map")
    orphan_id = _node(admin, "legacy-orphan")
    with SessionLocal() as db:
        node = db.get(Node, node_id)
        assert node is not None
        node.tags = {"Site": "Madrid", "Latitude": "40.4", "Longitude": "-3.7"}
        orphan = db.get(Node, orphan_id)
        assert orphan is not None
        orphan.tags = {"Site": "Madrid", "Latitude": "40.4"}
        db.commit()

    with SessionLocal() as db:
        assert migrate_legacy_coordinate_tags(db) == 2
        assert migrate_site_coordinates(db) == 1
        node = db.get(Node, node_id)
        orphan = db.get(Node, orphan_id)
        assert node is not None and orphan is not None
        assert node.tags == {"Site": "Madrid"}
        assert orphan.tags == {"Site": "Madrid"}
        location = db.scalar(select(SiteLocation).where(SiteLocation.name == "Madrid"))
        assert location is not None
        assert location.latitude == 40.4
        assert location.longitude == -3.7
        assert migrate_site_coordinates(db) == 0

    sites = admin.get("/api/nodes/sites", params={"tag": "Site"}).json()
    madrid = next(site for site in sites["sites"] if site["name"] == "Madrid")
    assert madrid["latitude"] == 40.4
    assert madrid["longitude"] == -3.7


def test_audit_records_before_and_after(client: TestClient, admin):
    node_id = _node(admin, "audit-1")
    updated = admin.patch(f"/api/nodes/{node_id}", json={"model": "iosxe", "tags": {"site": "madrid"}})
    assert updated.status_code == 200, updated.text

    entries = admin.get(
        "/api/audit",
        params={"action": "node.updated", "target_type": "node", "target_id": str(node_id)},
    ).json()["items"]
    assert entries
    params = entries[0]["action_params"]
    assert params["before"]["model"] == "ios"
    assert params["after"]["model"] == "iosxe"
    assert params["after"]["tags"] == {"Site": "Madrid"}


def test_health_history_samples(client: TestClient, admin):
    from app.health_service import process_health

    with SessionLocal() as db:
        process_health(db)
        process_health(db)
    history = admin.get("/api/system/health/history", params={"hours": 24}).json()
    assert len(history["samples"]) >= 2
    assert {"top_nodes", "samples"} <= set(history)
