from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import notifications


def _channel(client: TestClient, **overrides):
    payload = {
        "name": "Ops",
        "kind": "webhook",
        "enabled": True,
        "events": ["job.failed"],
        "config": {"url": "https://hooks.example.test/ops"},
    }
    payload.update(overrides)
    return client.post("/api/system/notifications", json=payload)


def test_notification_channels_crud(client: TestClient, admin):
    created = _channel(admin)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Ops"
    assert body["kind"] == "webhook"
    assert body["config"]["url"] == "https://hooks.example.test/ops"

    listed = admin.get("/api/system/notifications")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    updated = admin.patch(
        f"/api/system/notifications/{body['id']}",
        json={"name": "Ops 2", "enabled": False, "events": ["job.failed", "backup.stale"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Ops 2"
    assert updated.json()["enabled"] is False
    assert updated.json()["events"] == ["job.failed", "backup.stale"]

    deleted = admin.delete(f"/api/system/notifications/{body['id']}")
    assert deleted.status_code == 204
    assert admin.get("/api/system/notifications").json()["items"] == []


def test_notification_channel_validation(client: TestClient, admin):
    invalid = _channel(admin, config={"url": "not-a-url"})
    assert invalid.status_code == 422
    invalid_events = _channel(admin, events=["unknown.event"])
    assert invalid_events.status_code == 422
    telegram = _channel(
        admin,
        kind="telegram",
        config={"bot_token": "123:abc", "chat_id": "-1001"},
    )
    assert telegram.status_code == 201
    assert admin.get("/api/system/notifications").json()["items"][0]["kind"] == "telegram"


def test_notification_delivery_formats(monkeypatch, client: TestClient, admin):
    calls: list[tuple[str, dict]] = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs.get("json", {})))
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    for kind, config in (
        ("webhook", {"url": "https://example.test/hook"}),
        ("slack", {"webhook_url": "https://hooks.slack.test/x"}),
        ("discord", {"webhook_url": "https://discord.test/x"}),
        ("telegram", {"bot_token": "123:abc", "chat_id": "-1"}),
    ):
        created = _channel(admin, name=kind, kind=kind, config=config)
        assert created.status_code == 201, created.text
        tested = admin.post(f"/api/system/notifications/{created.json()['id']}/test")
        assert tested.status_code == 200
        assert tested.json()["ok"] is True

    assert calls[0][1]["event"] == "test"
    assert calls[1][1] == {"text": calls[1][1]["text"]}
    assert "content" in calls[2][1]
    assert calls[3][0].startswith("https://api.telegram.org/bot123:abc/sendMessage")
    assert calls[3][1]["chat_id"] == "-1"


def test_legacy_webhook_is_migrated_to_a_channel(client: TestClient, admin):
    patched = admin.patch(
        "/api/system/settings",
        json={"notify_webhook_url": "https://legacy.example.test/hook"},
    )
    assert patched.status_code == 200

    channels = admin.get("/api/system/notifications").json()["items"]
    assert len(channels) == 1
    assert channels[0]["name"] == "Legacy webhook"
    assert channels[0]["config"]["url"] == "https://legacy.example.test/hook"
