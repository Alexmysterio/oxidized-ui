from __future__ import annotations

import base64

from fastapi.testclient import TestClient

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def test_profile_full_name_email_and_avatar(client: TestClient, admin):
    updated = admin.patch(
        "/api/me",
        json={"full_name": "  Alex  Example ", "email": "ALEX@Example.com"},
    )
    assert updated.status_code == 200, updated.text
    user = updated.json()["user"]
    assert user["full_name"] == "Alex Example"
    assert user["email"] == "alex@example.com"
    assert user["avatar_url"] is None

    uploaded = admin.post(
        "/api/me/avatar",
        files={"file": ("me.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    avatar_url = uploaded.json()["user"]["avatar_url"]
    assert avatar_url and avatar_url.startswith("/api/avatars/")
    avatar = admin.get(avatar_url)
    assert avatar.status_code == 200
    assert avatar.headers["content-type"].startswith("image/png")
    assert avatar.content == PNG

    removed = admin.delete("/api/me/avatar")
    assert removed.status_code == 204
    session = admin.get("/api/auth/session").json()
    assert session["user"]["avatar_url"] is None


def test_profile_rejects_invalid_email(client: TestClient, admin):
    response = admin.patch("/api/me", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_admin_can_store_user_profile_fields(client: TestClient, admin):
    created = admin.post(
        "/api/users",
        json={
            "username": "jdoe",
            "password": "CorrectHorseBattery9!",
            "role": "viewer",
            "language": "es",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["full_name"] == "Jane Doe"
    assert created.json()["email"] == "jane@example.com"

    updated = admin.patch(
        f"/api/users/{created.json()['id']}",
        json={"full_name": "Jane A. Doe", "email": "jane.doe@example.com"},
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Jane A. Doe"
    assert updated.json()["email"] == "jane.doe@example.com"

    listed = admin.get("/api/users", params={"search": "jane.doe@example.com"})
    assert listed.json()["total"] == 1
