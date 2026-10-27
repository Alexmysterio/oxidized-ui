from __future__ import annotations

import time
import xmlrpc.client
from collections.abc import Iterator
from pathlib import Path

from defusedxml import xmlrpc as safe_xmlrpc

from .docker_api import LogLine, parse_level, split_timestamp
from .errors import AppError
from .settings import settings

safe_xmlrpc.monkey_patch()


class ProcessClient:
    """Small DockerClient-compatible adapter backed by supervisord."""

    def __init__(self, url: str | None = None, program: str | None = None, logfile: str | None = None) -> None:
        self.url = url or settings.supervisor_url
        self.program = program or settings.supervisor_program
        self.logfile = Path(logfile or settings.supervisor_logfile)

    def _server(self) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(self.url, allow_none=True)

    def restart(self) -> None:
        try:
            server = self._server()
            info = server.supervisor.getProcessInfo(self.program)
            if info.get("statename") == "RUNNING":
                server.supervisor.stopProcess(self.program, True)
            server.supervisor.startProcess(self.program, True)
        except Exception as exc:  # noqa: BLE001
            raise AppError("oxidized.restart_failed", params={"reason": "supervisor"}) from exc

    def container_state(self) -> dict[str, object]:
        try:
            info = self._server().supervisor.getProcessInfo(self.program)
            running = info.get("statename") == "RUNNING"
            return {
                "status": "running" if running else "stopped",
                "running": running,
                "restarting": False,
                "health": "healthy" if running else "unhealthy",
            }
        except Exception:  # noqa: BLE001
            raise AppError("oxidized.unavailable") from None

    def inspect(self) -> dict[str, object]:
        state = self.container_state()
        return {"State": {"Status": state["status"], "Running": state["running"]}}

    def log_snapshot(self, *, tail: int = 500, since: str | None = None, until: str | None = None) -> list[LogLine]:
        try:
            lines = self.logfile.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return []
        selected = lines[-max(1, min(tail, 100_000)) :]
        result: list[LogLine] = []
        for raw in selected:
            timestamp, text = split_timestamp(raw)
            result.append(LogLine(timestamp, "stdout", parse_level(text, "stdout"), text))
        return result

    def stream_logs(
        self,
        *,
        tail: int = 500,
        follow: bool = True,
        since: str | None = None,
        until: str | None = None,
    ) -> Iterator[LogLine]:
        position = 0
        try:
            position = max(0, self.logfile.stat().st_size)
        except OSError:
            position = 0
        yield from self.log_snapshot(tail=tail)
        if not follow:
            return
        while True:
            try:
                size = self.logfile.stat().st_size
                if size < position:
                    position = 0
                if size > position:
                    with self.logfile.open("r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(position)
                        data = handle.read()
                        position = handle.tell()
                    for raw in data.splitlines():
                        timestamp, text = split_timestamp(raw)
                        yield LogLine(timestamp, "stdout", parse_level(text, "stdout"), text)
            except OSError:
                pass
            time.sleep(1)

    def test(self) -> dict[str, object]:
        state = self.container_state()
        return {"ok": bool(state["running"]), "status": state["status"]}
