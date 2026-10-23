from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from .docker_api import LEVEL_ORDER, LogLine, client_for
from .errors import AppError
from .settings import settings
from .timeutil import to_iso

LEVEL_NAMES = {"trace", "debug", "info", "warn", "error", "fatal", "unknown"}


def _matches(line: LogLine, level: str | None, query: str | None) -> bool:
    if level and level in LEVEL_ORDER:
        if LEVEL_ORDER.get(line.level, 6) < LEVEL_ORDER[level]:
            return False
    if query:
        needle = query.casefold()
        if needle not in line.text.casefold():
            return False
    return True


def _line_public(line: LogLine, seq: int) -> dict[str, Any]:
    timestamp = line.timestamp
    if timestamp:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            timestamp = to_iso(parsed)
        except ValueError:
            pass
    return {
        "seq": seq,
        "timestamp": timestamp,
        "stream": line.stream,
        "level": line.level,
        "text": line.text,
    }


def snapshot(
    db: Session,
    *,
    tail: int,
    level: str | None = None,
    query: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    lines = client_for(db).log_snapshot(tail=tail, since=since)
    selected = [line for line in lines if _matches(line, level, query)]
    selected = selected[-max(1, min(tail, settings.max_log_lines)) :]
    return {
        "lines": [_line_public(line, index + 1) for index, line in enumerate(selected)],
        "truncated": len(lines) >= tail,
    }


def download(
    db: Session,
    *,
    since: str | None,
    until: str | None,
    level: str | None,
    query: str | None,
) -> tuple[str, str]:
    lines = client_for(db).log_snapshot(tail=100_000, since=since, until=until)
    selected = [line for line in lines if _matches(line, level, query)]
    if len(selected) > 100_000:
        selected = selected[-100_000:]
        truncated = True
    else:
        truncated = False
    content = "\n".join(line.text for line in selected)
    if content:
        content += "\n"
    if truncated:
        content += "\n[truncated at 100000 lines]\n"
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"oxidized-logs-{stamp}.txt", content


def sse_events(
    client,
    *,
    tail: int,
    level: str | None,
    query: str | None,
    request: Any = None,
) -> Iterator[str]:
    yield _event("ready", {"follow": True})
    seq = 0
    try:
        for line in client.stream_logs(tail=tail, follow=True):
            if request is not None and getattr(request, "is_disconnected", None):
                # Starlette cancels the streaming task on disconnect. For test
                # doubles that expose a boolean we can still stop early.
                disconnected = request.is_disconnected
                if isinstance(disconnected, bool) and disconnected:
                    break
            if not _matches(line, level, query):
                continue
            seq += 1
            yield _event("log", {"seq": seq, **_strip_seq(_line_public(line, seq))})
    except AppError as exc:
        yield _event("error", {"code": exc.code, "params": exc.params})
    except Exception:  # noqa: BLE001 - never leak internals to the browser
        yield _event("error", {"code": "logs.stream_failed", "params": {}})


def _strip_seq(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("seq", None)
    return result


def _event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"
