from __future__ import annotations

import os
import re
import shutil
import socket
import struct
import subprocess
import time
from typing import Any

PING_COUNT = 3
PING_TIMEOUT = 1.0
MAX_REPLY_BYTES = 2048
PAYLOAD = b"oxidized-ui"

ICMP_ECHO_REQUEST = {socket.AF_INET: 8, socket.AF_INET6: 128}
ICMP_ECHO_REPLY = {socket.AF_INET: 0, socket.AF_INET6: 129}
ICMP_PROTOCOL = {
    socket.AF_INET: socket.IPPROTO_ICMP,
    socket.AF_INET6: getattr(socket, "IPPROTO_ICMPV6", 58),
}
RTT_PATTERN = re.compile(r"(?:time|tiempo)[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


def _build_request(family: int, identifier: int, sequence: int) -> bytes:
    kind = ICMP_ECHO_REQUEST[family]
    header = struct.pack("!BBHHH", kind, 0, 0, identifier, sequence)
    payload = PAYLOAD + struct.pack("!d", time.perf_counter())
    # ICMPv6 checksums need the IPv6 pseudo-header, but the kernel always
    # computes them for raw and datagram ICMPv6 sockets.
    checksum = 0 if family == socket.AF_INET6 else _checksum(header + payload)
    return struct.pack("!BBHHH", kind, 0, checksum, identifier, sequence) + payload


def _resolve(address: str) -> tuple[int, tuple[Any, ...]] | None:
    try:
        infos = socket.getaddrinfo(address, None, type=socket.SOCK_DGRAM)
    except (OSError, UnicodeError):
        return None
    for family, _type, _proto, _canonical, sockaddr in infos:
        if family in ICMP_ECHO_REQUEST:
            return family, sockaddr
    return None


def _round_trip(
    sock: socket.socket,
    family: int,
    sockaddr: tuple[Any, ...],
    sequence: int,
    timeout: float,
    identifier: int,
    sock_type: int,
) -> float | None:
    packet = _build_request(family, identifier, sequence)
    started = time.perf_counter()
    sock.sendto(packet, sockaddr)
    deadline = started + timeout
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return None
        sock.settimeout(remaining)
        try:
            data, _peer = sock.recvfrom(MAX_REPLY_BYTES)
        except TimeoutError:
            return None
        # Raw sockets include the IP header; datagram ping sockets do not.
        if family == socket.AF_INET and len(data) >= 20 and data[0] >> 4 == 4:
            data = data[(data[0] & 0x0F) * 4 :]
        if not data or data[0] != ICMP_ECHO_REPLY[family]:
            continue
        if len(data) >= 8 and sock_type == socket.SOCK_RAW:
            reply_identifier = struct.unpack("!H", data[4:6])[0]
            if reply_identifier != identifier:
                continue
        return round((time.perf_counter() - started) * 1000, 2)


def _parse_rtt(stdout: str) -> float | None:
    match = RTT_PATTERN.search(stdout)
    return float(match.group(1)) if match else None


def _ping_command(
    result: dict[str, Any],
    address: str,
    count: int,
    timeout: float,
) -> dict[str, Any]:
    """Fallback for platforms where unprivileged ICMP sockets are unavailable."""
    binary = shutil.which("ping")
    if not binary:
        result.update(sent=0, received=0, reachable=False, message="unavailable")
        return result
    if os.name == "nt":
        command = [binary, "-n", str(count), "-w", str(max(1, int(timeout * 1000))), address]
    else:
        command = [binary, "-c", str(count), "-W", str(max(1, int(round(timeout)))), address]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=count * (timeout + 1) + 3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        result.update(sent=0, received=0, reachable=False, message="error")
        return result

    stderr = (completed.stderr or "").lower()
    result["sent"] = count
    if completed.returncode == 0:
        result.update(reachable=True, received=count, message="ok", rtt_ms=_parse_rtt(completed.stdout or ""))
    elif "not permitted" in stderr or "permission denied" in stderr:
        result.update(sent=0, received=0, reachable=False, message="unavailable")
    elif any(
        fragment in stderr
        for fragment in ("unknown host", "name or service not known", "cannot resolve", "could not find host")
    ):
        result.update(received=0, reachable=False, message="unknown_host")
    else:
        result.update(received=0, reachable=False, message="timeout")
    return result


def ping_host(address: str, *, count: int = PING_COUNT, timeout: float = PING_TIMEOUT) -> dict[str, Any]:
    """Send ICMP echo requests to a node address.

    Loopback, link-local, multicast and metadata targets are rejected: they are
    not managed devices and would turn this endpoint into an SSRF primitive.

    Uses unprivileged ICMP datagram sockets first (they only need
    ``net.ipv4.ping_group_range`` inside the container), then raw sockets, and
    finally the system ``ping`` command. ICMP may be filtered by the network, so
    callers must treat the result as informational.
    """
    from .net_safety import ensure_safe_target

    ensure_safe_target(address, raise_on_dns_failure=False)
    result: dict[str, Any] = {
        "reachable": False,
        "address": None,
        "sent": 0,
        "received": 0,
        "rtt_ms": None,
        "message": "unknown_host",
    }
    target_address = (address or "").strip()
    if not target_address:
        return result
    target = _resolve(target_address)
    if target is None:
        return result
    family, sockaddr = target
    result["address"] = str(sockaddr[0])

    identifier = os.getpid() & 0xFFFF
    sock: socket.socket | None = None
    sock_type = socket.SOCK_DGRAM
    for candidate in (socket.SOCK_DGRAM, socket.SOCK_RAW):
        try:
            sock = socket.socket(family, candidate, ICMP_PROTOCOL[family])
            sock_type = candidate
            break
        except OSError:
            sock = None
    if sock is None:
        return _ping_command(result, target_address, count, timeout)

    rtts: list[float] = []
    try:
        for sequence in range(1, count + 1):
            result["sent"] += 1
            try:
                rtt = _round_trip(sock, family, sockaddr, sequence, timeout, identifier, sock_type)
            except PermissionError:
                return _ping_command(result, target_address, count, timeout)
            except OSError:
                rtt = None
            if rtt is not None:
                rtts.append(rtt)
    finally:
        sock.close()

    result["received"] = len(rtts)
    if rtts:
        result["reachable"] = True
        result["rtt_ms"] = round(sum(rtts) / len(rtts), 2)
        result["message"] = "ok"
    elif result["sent"]:
        result["message"] = "timeout"
    else:
        result["message"] = "error"
    return result
