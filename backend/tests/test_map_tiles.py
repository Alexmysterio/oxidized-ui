from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.routers import map as map_router

PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture(autouse=True)
def _reset_map_state():
    map_router._cache.clear()
    map_router._failures = 0
    map_router._open_until = 0.0
    yield
    map_router._cache.clear()
    map_router._failures = 0
    map_router._open_until = 0.0


def test_tile_requires_authentication(client: TestClient):
    assert client.get("/api/map/tiles/6/30/20.png").status_code == 401


def test_tile_is_fetched_and_cached(admin, monkeypatch):
    calls: list[tuple[int, int, int]] = []

    async def fake(z: int, x: int, y: int) -> bytes:
        calls.append((z, x, y))
        return PNG

    monkeypatch.setattr(map_router, "_fetch_tile", fake)
    first = admin.get("/api/map/tiles/6/30/20.png")
    second = admin.get("/api/map/tiles/6/30/20.png")

    assert first.status_code == 200
    assert first.content == PNG
    assert first.headers["content-type"] == "image/png"
    assert first.headers["cache-control"] == "public, max-age=86400"
    assert second.content == PNG
    assert calls == [(6, 30, 20)]


def test_tile_rejects_out_of_range_coordinates(admin):
    assert admin.get("/api/map/tiles/2/9/0.png").status_code == 404
    assert admin.get("/api/map/tiles/20/0/0.png").status_code == 404


def test_tile_reports_upstream_failure(admin, monkeypatch):
    async def fail(_z: int, _x: int, _y: int) -> bytes:
        raise AppError("map.tile_unavailable")

    monkeypatch.setattr(map_router, "_fetch_tile", fail)
    response = admin.get("/api/map/tiles/6/30/20.png")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "map.tile_unavailable"


def test_tile_circuit_breaker_avoids_repeated_upstream_calls(admin, monkeypatch):
    calls = 0

    async def fail(_z: int, _x: int, _y: int) -> bytes:
        nonlocal calls
        calls += 1
        raise AppError("map.tile_unavailable")

    monkeypatch.setattr(map_router, "_fetch_tile", fail)
    for index in range(map_router.FAILURE_THRESHOLD):
        assert admin.get(f"/api/map/tiles/6/{30 + index}/20.png").status_code == 502
    assert calls == map_router.FAILURE_THRESHOLD

    blocked = admin.get("/api/map/tiles/6/40/20.png")
    assert blocked.status_code == 502
    assert calls == map_router.FAILURE_THRESHOLD
