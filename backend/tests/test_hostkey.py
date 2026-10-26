from __future__ import annotations

import base64
import hashlib
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import hostkey_service
from tests.conftest import make_node

KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIKgEw4s0w6s4m8P7Y3eE2V5rJH0n3i9g1j6z4b8x2c0d"


def test_scan_filters_host_and_comments(monkeypatch) -> None:
    output = (
        "# 10.0.0.1:22 SSH-2.0-OpenSSH_9\n"
        f"10.0.0.1 ssh-ed25519 {KEY}\n"
        "10.0.0.2 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBad\n"
    )
    monkeypatch.setattr(
        hostkey_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=output, returncode=0),
    )
    lines = hostkey_service._scan("10.0.0.1", 22)
    assert lines == [f"10.0.0.1 ssh-ed25519 {KEY}"]
    expected = "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(KEY)).digest()).decode().rstrip("=")
    assert hostkey_service._fingerprints(lines) == [expected]


def test_write_known_hosts_replaces_only_target_host(tmp_path, monkeypatch) -> None:
    target = tmp_path / ".ssh" / "known_hosts"
    target.parent.mkdir()
    target.write_text(
        f"10.0.0.1 ssh-ed25519 {KEY}\n"
        f"10.0.0.2 ssh-ed25519 {KEY}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hostkey_service, "known_hosts_path", lambda: target)
    new_key = KEY[:-1] + "e"
    hostkey_service._write_known_hosts("10.0.0.1", [f"10.0.0.1 ssh-ed25519 {new_key}"])
    content = target.read_text(encoding="utf-8")
    assert "10.0.0.2" in content
    assert new_key in content
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_bulk_trust_host_keys(client: TestClient, admin, monkeypatch, tmp_path) -> None:
    target = tmp_path / "known_hosts"
    monkeypatch.setattr(hostkey_service, "known_hosts_path", lambda: target)
    monkeypatch.setattr(
        hostkey_service,
        "_scan",
        lambda address, port: [f"{address} ssh-ed25519 {KEY}"],
    )
    first = admin.post(
        "/api/nodes",
        json=make_node(name="trust-1", address="10.0.0.1"),
    )
    second = admin.post(
        "/api/nodes",
        json=make_node(name="trust-2", address="10.0.0.2"),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    ids = [first.json()["node"]["id"], second.json()["node"]["id"]]

    response = admin.post("/api/nodes/bulk", json={"action": "trust_host_key", "ids": ids})

    assert response.status_code == 200, response.text
    assert response.json()["trusted"] == 2
    assert response.json()["failed"] == []
    content = target.read_text(encoding="utf-8")
    assert "10.0.0.1" in content
    assert "10.0.0.2" in content
