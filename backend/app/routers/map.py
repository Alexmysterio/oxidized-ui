from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

import httpx
from fastapi import APIRouter, Depends, Response

from .. import __version__
from ..auth_deps import get_auth_context
from ..errors import AppError
from ..security import AuthContext

router = APIRouter(prefix="/map", tags=["map"])

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = f"OxidizedUI/{__version__} (+https://github.com/Alexmysterio/oxidized-ui)"
MAX_ZOOM = 19
TILE_TTL = 24 * 60 * 60
CACHE_SIZE = 1024
MAX_TILE_BYTES = 2 * 1024 * 1024

_cache: OrderedDict[tuple[int, int, int], tuple[float, bytes]] = OrderedDict()
_cache_lock = Lock()


def _cached(z: int, x: int, y: int) -> tuple[float, bytes] | None:
    with _cache_lock:
        entry = _cache.get((z, x, y))
        if entry is not None:
            _cache.move_to_end((z, x, y))
        return entry


def _store(z: int, x: int, y: int, payload: bytes) -> None:
    with _cache_lock:
        _cache[(z, x, y)] = (time.monotonic(), payload)
        _cache.move_to_end((z, x, y))
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def _fetch_tile(z: int, x: int, y: int) -> bytes:
    url = TILE_URL.format(z=z, x=x, y=y)
    try:
        with httpx.Client(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/*;q=0.8"},
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise AppError("map.tile_unavailable") from exc
    content_type = response.headers.get("content-type", "")
    payload = response.content
    if (
        response.status_code != 200
        or not content_type.startswith("image/")
        or not payload
        or len(payload) > MAX_TILE_BYTES
    ):
        raise AppError("map.tile_unavailable")
    return payload


def _tile(z: int, x: int, y: int) -> bytes:
    cached = _cached(z, x, y)
    if cached is not None and time.monotonic() - cached[0] < TILE_TTL:
        return cached[1]
    try:
        payload = _fetch_tile(z, x, y)
    except AppError:
        if cached is not None:
            return cached[1]
        raise
    _store(z, x, y, payload)
    return payload


@router.get("/tiles/{z}/{x}/{y}.png")
def tile(
    z: int,
    x: int,
    y: int,
    _context: AuthContext = Depends(get_auth_context),
):
    limit = 1 << z
    if not (0 <= z <= MAX_ZOOM and 0 <= x < limit and 0 <= y < limit):
        raise AppError("app.not_found")
    payload = _tile(z, x, y)
    return Response(
        content=payload,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
