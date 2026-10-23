from __future__ import annotations

import json
import re
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .errors import AppError
from .models import SystemSettings
from .settings import settings

LEVEL_ORDER = {"trace": 0, "debug": 1, "info": 2, "warn": 3, "error": 4, "fatal": 5, "unknown": 6}
LEVEL_LETTER = {
    "T": "trace",
    "D": "debug",
    "I": "info",
    "W": "warn",
    "E": "error",
    "F": "fatal",
}
LEVEL_WORD_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\b", re.IGNORECASE)
LEVEL_LETTER_RE = re.compile(r"\b([TDIWEF])\b")


@dataclass(slots=True)
class LogLine:
    timestamp: str | None
    stream: str
    level: str
    text: str


def effective_docker_url(db: Session | None = None) -> str:
    if db is not None:
        row = db.get(SystemSettings, 1)
        if row and row.docker_proxy_url:
            return row.docker_proxy_url
    return settings.docker_proxy_url


def effective_container_name(db: Session | None = None) -> str:
    if db is not None:
        row = db.get(SystemSettings, 1)
        if row and row.oxidized_container_name:
            return row.oxidized_container_name
    return settings.oxidized_container_name


def parse_level(line: str, stream: str = "stdout") -> str:
    stripped = line.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
            raw = str(obj.get("level") or obj.get("severity") or "").casefold()
            if raw in {"warning", "warn"}:
                return "warn"
            if raw in {"err", "error"}:
                return "error"
            if raw in {"fatal", "critical"}:
                return "fatal"
            if raw in {"trace", "debug", "info"}:
                return raw
        except (ValueError, TypeError):
            pass
    match = LEVEL_WORD_RE.search(stripped[:120])
    if match:
        value = match.group(1).casefold()
        return "warn" if value in {"warn", "warning"} else value
    # SemanticLogger's short prefix: "2026-... W [pid:tid]".
    short = re.search(r"^\S+\s+\S+\s+([TDIWEF])\s+", stripped)
    if short:
        return LEVEL_LETTER.get(short.group(1), "unknown")
    match = LEVEL_LETTER_RE.search(stripped[:120])
    if match:
        return LEVEL_LETTER.get(match.group(1), "unknown")
    if stream == "stderr":
        return "error"
    return "unknown"


def split_timestamp(line: str) -> tuple[str | None, str]:
    # Docker timestamps=1 prefixes RFC3339Nano and one space. Python's parser
    # accepts the fraction, but Docker can emit nanosecond precision and we do
    # not need a datetime object here, only a stable timestamp string.
    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})) (.*)$",
        line,
    )
    if match:
        return match.group(1).replace("Z", "+00:00"), match.group(2)
    return None, line


class DockerClient:
    def __init__(self, base_url: str | None = None, container: str | None = None) -> None:
        self.base_url = (base_url or settings.docker_proxy_url).rstrip("/")
        self.container = container or settings.oxidized_container_name
        self.timeout = httpx.Timeout(settings.docker_read_timeout, connect=settings.docker_connect_timeout)

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout, follow_redirects=False)

    def _container_path(self, suffix: str) -> str:
        return f"/containers/{self.container}/{suffix}"

    def inspect(self) -> dict[str, Any]:
        try:
            with self._client() as client:
                response = client.get(self._container_path("json"))
        except httpx.TimeoutException as exc:
            raise AppError("docker.unavailable") from exc
        except httpx.RequestError as exc:
            raise AppError("docker.unavailable") from exc
        if response.status_code == 404:
            raise AppError("docker.container_not_found", params={"container": self.container})
        if response.status_code >= 400:
            raise AppError("docker.unavailable", params={"status": response.status_code})
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError("docker.unavailable", params={"reason": "invalid_json"}) from exc
        return payload if isinstance(payload, dict) else {}

    def restart(self) -> None:
        try:
            with self._client() as client:
                response = client.post(self._container_path("restart"), params={"t": 10})
        except httpx.TimeoutException as exc:
            raise AppError("oxidized.restart_failed", params={"reason": "timeout"}) from exc
        except httpx.RequestError as exc:
            raise AppError("oxidized.restart_failed", params={"reason": "unavailable"}) from exc
        if response.status_code == 404:
            raise AppError("docker.container_not_found", params={"container": self.container})
        if response.status_code >= 400:
            raise AppError("oxidized.restart_failed", params={"status": response.status_code})

    def container_state(self) -> dict[str, Any]:
        payload = self.inspect()
        state = payload.get("State") if isinstance(payload.get("State"), dict) else {}
        return {
            "status": state.get("Status"),
            "running": bool(state.get("Running")),
            "restarting": bool(state.get("Restarting")),
            "started_at": state.get("StartedAt"),
            "health": (state.get("Health") or {}).get("Status") if isinstance(state.get("Health"), dict) else None,
        }

    def _logs_params(
        self,
        *,
        tail: int = 500,
        follow: bool = False,
        since: str | None = None,
        until: str | None = None,
        timestamps: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "stdout": 1,
            "stderr": 1,
            "follow": 1 if follow else 0,
            "timestamps": 1 if timestamps else 0,
            "tail": str(max(1, min(tail, 100_000))),
        }
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        return params

    def _logs_response(self, client: httpx.Client, params: dict[str, Any]) -> Any:
        request = client.build_request("GET", self._container_path("logs"), params=params)
        try:
            return client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise AppError("docker.logs_unavailable", params={"reason": "timeout"}) from exc
        except httpx.RequestError as exc:
            raise AppError("docker.logs_unavailable", params={"reason": "unavailable"}) from exc

    def stream_logs(
        self,
        *,
        tail: int = 500,
        follow: bool = True,
        since: str | None = None,
        until: str | None = None,
    ) -> Iterator[LogLine]:
        params = self._logs_params(tail=tail, follow=follow, since=since, until=until)
        buffers: dict[str, str] = {"stdout": "", "stderr": ""}
        timeout = httpx.Timeout(None, connect=settings.docker_connect_timeout) if follow else self.timeout
        with httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=False) as client:
            response = self._logs_response(client, params)
            try:
                if response.status_code == 404:
                    raise AppError("docker.container_not_found", params={"container": self.container})
                if response.status_code >= 400:
                    raise AppError("docker.logs_unavailable", params={"status": response.status_code})
                demux = _Demuxer()
                for chunk in response.iter_raw():
                    for stream, payload in demux.feed(chunk):
                        buffers[stream] += payload.decode("utf-8", errors="replace")
                        yield from self._drain_lines(stream, buffers)
                for stream, payload in demux.flush():
                    buffers[stream] += payload.decode("utf-8", errors="replace")
                    yield from self._drain_lines(stream, buffers)
                for stream, text in list(buffers.items()):
                    if text:
                        timestamp, line = split_timestamp(text.rstrip("\r"))
                        yield LogLine(timestamp, stream, parse_level(line, stream), line)
                        buffers[stream] = ""
            finally:
                response.close()

    @staticmethod
    def _drain_lines(stream: str, buffers: dict[str, str]) -> Iterator[LogLine]:
        while "\n" in buffers[stream]:
            raw, _, rest = buffers[stream].partition("\n")
            buffers[stream] = rest
            raw = raw.rstrip("\r")
            if not raw:
                continue
            timestamp, text = split_timestamp(raw)
            yield LogLine(timestamp, stream, parse_level(text, stream), text)

    def log_snapshot(
        self,
        *,
        tail: int = 500,
        since: str | None = None,
        until: str | None = None,
    ) -> list[LogLine]:
        return list(self.stream_logs(tail=tail, follow=False, since=since, until=until))

    def test(self) -> dict[str, Any]:
        payload = self.inspect()
        state = payload.get("State") if isinstance(payload.get("State"), dict) else {}
        return {"ok": True, "status": state.get("Status")}


class _Demuxer:
    """Demultiplex Docker's 8-byte frame format; fall back to raw text."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.multiplexed = True
        self._checked = False

    def _framed(self) -> bool:
        if len(self.buffer) < 8:
            return True
        if self._checked:
            return self.multiplexed
        first = self.buffer[0]
        header_ok = first in (0, 1, 2) and self.buffer[1:4] == b"\x00\x00\x00"
        self.multiplexed = header_ok
        self._checked = True
        return self.multiplexed

    def feed(self, chunk: bytes) -> list[tuple[str, bytes]]:
        self.buffer.extend(chunk)
        if not self._framed():
            data = bytes(self.buffer)
            self.buffer.clear()
            return [("stdout", data)]
        output: list[tuple[str, bytes]] = []
        while len(self.buffer) >= 8:
            stream_type = self.buffer[0]
            frame_size = struct.unpack(">I", self.buffer[4:8])[0]
            if frame_size > 16 * 1024 * 1024:
                self.multiplexed = False
                data = bytes(self.buffer)
                self.buffer.clear()
                return output + ([("stdout", data)] if data else [])
            if len(self.buffer) < 8 + frame_size:
                break
            frame = bytes(self.buffer[8 : 8 + frame_size])
            del self.buffer[: 8 + frame_size]
            stream = "stderr" if stream_type == 2 else "stdout"
            output.append((stream, frame))
        return output

    def flush(self) -> list[tuple[str, bytes]]:
        if not self.buffer:
            return []
        data = bytes(self.buffer)
        self.buffer.clear()
        return [("stdout", data)]


def client_for(db: Session | None = None):
    if settings.supervisor_url:
        from .process_supervisor import ProcessClient

        return ProcessClient()
    return DockerClient(effective_docker_url(db), effective_container_name(db))


def service_state(db: Session | None = None) -> dict[str, Any]:
    try:
        return client_for(db).container_state()
    except AppError as exc:
        return {"status": "unavailable", "running": False, "error": exc.code}


def test_connection(db: Session | None = None) -> dict[str, Any]:
    return client_for(db).test()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
