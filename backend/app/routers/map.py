from __future__ import annotations

import asyncio
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
MAX_CONCURRENT_FETCHES = 6
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60

_cache: OrderedDict[tuple[int, int, int], tuple[float, bytes]] = OrderedDict()
_cache_lock = Lock()
_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None
_failures = 0
_open_until = 0.0


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


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.0, read=4.0, write=4.0, pool=2.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/*;q=0.8"},
        )
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
    return _semaphore


async def close_client() -> None:
    global _client, _semaphore
    if _client is not None:
        await _client.aclose()
        _client = None
    _semaphore = None


def _record_failure() -> None:
    global _failures, _open_until
    _failures += 1
    if _failures >= FAILURE_THRESHOLD:
        _open_until = time.monotonic() + COOLDOWN_SECONDS


def _record_success() -> None:
    global _failures, _open_until
    _failures = 0
    _open_until = 0.0


async def _fetch_tile(z: int, x: int, y: int) -> bytes:
    url = TILE_URL.format(z=z, x=x, y=y)
    async with _get_semaphore():
        if time.monotonic() < _open_until:
            raise AppError("map.tile_unavailable")
        try:
            response = await _get_client().get(url)
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


async def _tile(z: int, x: int, y: int) -> bytes:
    cached = _cached(z, x, y)
    if cached is not None and time.monotonic() - cached[0] < TILE_TTL:
        return cached[1]
    if time.monotonic() < _open_until:
        if cached is not None:
            return cached[1]
        raise AppError("map.tile_unavailable")
    try:
        payload = await _fetch_tile(z, x, y)
    except AppError:
        _record_failure()
        if cached is not None:
            return cached[1]
        raise
    _record_success()
    _store(z, x, y, payload)
    return payload


@router.get("/tiles/{z}/{x}/{y}.png")
async def tile(
    z: int,
    x: int,
    y: int,
    _context: AuthContext = Depends(get_auth_context),
):
    limit = 1 << z
    if not (0 <= z <= MAX_ZOOM and 0 <= x < limit and 0 <= y < limit):
        raise AppError("app.not_found")
    payload = await _tile(z, x, y)
    return Response(
        content=payload,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
