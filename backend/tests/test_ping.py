from __future__ import annotations

import socket
import struct

from app import ping_service


class FakeSocket:
    def __init__(self, replies: list[bytes] | None = None, *, timeout: bool = False) -> None:
        self.replies = list(replies or [])
        self.timeout = timeout
        self.sent: list[tuple[bytes, tuple[object, ...]]] = []
        self.closed = False

    def sendto(self, data: bytes, sockaddr: tuple[object, ...]) -> None:
        self.sent.append((data, sockaddr))

    def settimeout(self, _value: float) -> None:
        return None

    def recvfrom(self, _size: int) -> tuple[bytes, tuple[str, int]]:
        if self.timeout:
            raise TimeoutError
        if not self.replies:
            raise TimeoutError
        return self.replies.pop(0), ("192.0.2.1", 0)

    def close(self) -> None:
        self.closed = True


def _reply() -> bytes:
    return struct.pack("!BBHHH", 0, 0, 0, 0, 1)


def _resolved(monkeypatch, *, family: int = socket.AF_INET) -> None:
    monkeypatch.setattr(
        ping_service.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, socket.SOCK_DGRAM, socket.IPPROTO_ICMP, "", ("192.0.2.1", 0))],
    )


def test_ping_host_reports_successful_round_trips(monkeypatch):
    _resolved(monkeypatch)
    fake = FakeSocket([_reply(), _reply(), _reply()])
    monkeypatch.setattr(ping_service.socket, "socket", lambda *_args, **_kwargs: fake)

    result = ping_service.ping_host("192.0.2.1")

    assert result["reachable"] is True
    assert result["sent"] == 3
    assert result["received"] == 3
    assert result["rtt_ms"] is not None
    assert result["message"] == "ok"
    assert fake.closed is True
    assert len(fake.sent) == 3


def test_ping_host_reports_timeout(monkeypatch):
    _resolved(monkeypatch)
    fake = FakeSocket(timeout=True)
    monkeypatch.setattr(ping_service.socket, "socket", lambda *_args, **_kwargs: fake)

    result = ping_service.ping_host("192.0.2.1", count=1, timeout=0.01)

    assert result["reachable"] is False
    assert result["sent"] == 1
    assert result["received"] == 0
    assert result["message"] == "timeout"


def test_ping_host_reports_unknown_host(monkeypatch):
    def fail(*_args, **_kwargs):
        raise socket.gaierror("name not known")

    monkeypatch.setattr(ping_service.socket, "getaddrinfo", fail)

    result = ping_service.ping_host("missing.invalid")

    assert result["reachable"] is False
    assert result["message"] == "unknown_host"


def test_ping_host_reports_unavailable_without_icmp_permissions(monkeypatch):
    _resolved(monkeypatch)

    def deny(*_args, **_kwargs):
        raise PermissionError

    monkeypatch.setattr(ping_service.socket, "socket", deny)
    monkeypatch.setattr(ping_service.shutil, "which", lambda _name: None)

    result = ping_service.ping_host("192.0.2.1", count=1)

    assert result["reachable"] is False
    assert result["message"] == "unavailable"


def test_ping_host_falls_back_to_the_ping_command(monkeypatch):
    _resolved(monkeypatch)

    def deny(*_args, **_kwargs):
        raise PermissionError

    monkeypatch.setattr(ping_service.socket, "socket", deny)
    monkeypatch.setattr(ping_service.shutil, "which", lambda _name: "ping")
    monkeypatch.setattr(
        ping_service.subprocess,
        "run",
        lambda *_args, **_kwargs: ping_service.subprocess.CompletedProcess(
            args=[], returncode=0, stdout="64 bytes: time=1.25 ms", stderr=""
        ),
    )

    result = ping_service.ping_host("192.0.2.1")

    assert result["reachable"] is True
    assert result["received"] == 3
    assert result["rtt_ms"] == 1.25
    assert result["message"] == "ok"
