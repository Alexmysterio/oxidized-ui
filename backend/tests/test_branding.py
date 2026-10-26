from __future__ import annotations

import base64

from fastapi.testclient import TestClient

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def test_site_name_and_logo_are_public_in_meta(client: TestClient, admin):
    patched = admin.patch("/api/system/settings", json={"site_name": "Acme NOC"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["site_name"] == "Acme NOC"

    meta = client.get("/api/meta").json()
    assert meta["site_name"] == "Acme NOC"
    assert meta["logo_url"] is None

    uploaded = admin.post(
        "/api/system/branding/logo",
        files={"file": ("logo.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_logo"] is True

    meta = client.get("/api/meta").json()
    assert meta["logo_url"] and meta["logo_url"].startswith("/api/branding/logo?v=")
    logo = client.get(meta["logo_url"])
    assert logo.status_code == 200
    assert logo.headers["content-type"].startswith("image/png")
    assert logo.content == PNG

    removed = admin.delete("/api/system/branding/logo")
    assert removed.status_code == 204
    assert client.get("/api/meta").json()["logo_url"] is None


def test_logo_rejects_non_image_files(client: TestClient, admin):
    response = admin.post(
        "/api/system/branding/logo",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 422
