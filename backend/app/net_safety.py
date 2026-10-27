from __future__ import annotations

import ipaddress
import socket

from .errors import AppError

FORBIDDEN_MESSAGE = "forbidden_target"


def _is_forbidden(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or (isinstance(address, ipaddress.IPv4Address) and address in ipaddress.ip_network("169.254.0.0/16"))
    )


def ensure_safe_target(host: str, port: int | None = None, *, raise_on_dns_failure: bool = True) -> None:
    value = (host or "").strip().strip("[]")
    if not value:
        raise AppError("node.forbidden_target", params={"address": host or ""})
    try:
        addresses = [ipaddress.ip_address(value)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(value, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            if not raise_on_dns_failure:
                return
            raise AppError("node.forbidden_target", params={"address": value}) from exc
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
        if not addresses:
            raise AppError("node.forbidden_target", params={"address": value}) from None
    if any(_is_forbidden(address) for address in addresses):
        raise AppError("node.forbidden_target", params={"address": value})
