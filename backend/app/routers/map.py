from __future__ import annotations

import asyncio
import socket
import sys
import time
from collections import OrderedDict
from threading import Lock

import aiohttp
from aiohttp.resolver import AsyncResolver
from fastapi import APIRouter, Depends, Response

from .. import __version__
from ..auth_deps import validate_session
from ..errors import AppError

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
TILE_FETCH_TIMEOUT = 6.0

_cache: OrderedDict[tuple[int, int, int], tuple[float, bytes]] = OrderedDict()
_cache_lock = Lock()
_session: aiohttp.ClientSession | None = None
_resolver: AsyncResolver | None = None
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


def _get_session() -> aiohttp.ClientSession:
    global _session, _resolver
    if _session is None:
        # aiodns resolves without blocking the shared anyio thread pool. That
        # matters when DNS is black-holed: a threaded getaddrinfo can stay stuck
        # for ~30s and accumulate until every API request stalls.
        resolver: AsyncResolver | None = None
        if sys.platform.startswith("linux"):
            try:
                resolver = AsyncResolver(timeout=2)
            except Exception:  # noqa: BLE001 - fall back to the default resolver
                resolver = None
        _resolver = resolver
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            ttl_dns_cache=300,
            family=socket.AF_INET,
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=5, connect=3, sock_read=3),
            headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/*;q=0.8"},
            trust_env=True,
        )
    return _session


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
    return _semaphore


async def close_client() -> None:
    global _session, _resolver, _semaphore
    if _session is not None:
        await _session.close()
        _session = None
    if _resolver is not None:
        await _resolver.close()
        _resolver = None
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
            async with _get_session().get(url) as response:
                content_type = response.headers.get("Content-Type", "")
                payload = await response.read()
                status = response.status
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise AppError("map.tile_unavailable") from exc
    if (
        status != 200
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
        payload = await asyncio.wait_for(_fetch_tile(z, x, y), timeout=TILE_FETCH_TIMEOUT)
    except (AppError, TimeoutError):
        _record_failure()
        if cached is not None:
            return cached[1]
        raise AppError("map.tile_unavailable") from None
    _record_success()
    _store(z, x, y, payload)
    return payload


@router.get("/tiles/{z}/{x}/{y}.png")
async def tile(
    z: int,
    x: int,
    y: int,
    _context: None = Depends(validate_session),
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
