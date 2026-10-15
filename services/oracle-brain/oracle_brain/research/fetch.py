"""Guarded fetch: rejects private/link-local destinations and unsafe redirects. Transport is injected."""
from dataclasses import dataclass
import ipaddress
import socket
from typing import Callable
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 5


class UnsafeDestination(ValueError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = b''
    location: str | None = None


Resolver = Callable[[str], list[str]]
Transport = Callable[[str, str], Response]  # (url, pinned_ip) -> Response


def system_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def _unsafe_ip(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split('%')[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def check_destination(url: str, resolver: Resolver) -> str:
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise UnsafeDestination(f'refused url {url!r}')
    if parts.port not in (None, 443):
        raise UnsafeDestination(f'refused port {parts.port}')
    addresses = resolver(parts.hostname)
    if not addresses:
        raise UnsafeDestination(f'no address for {parts.hostname}')
    for address in addresses:
        if _unsafe_ip(address):
            raise UnsafeDestination(f'refused non-public address {address} for {parts.hostname}')
    return addresses[0]


def guarded_fetch(url: str, transport: Transport, resolver: Resolver = system_resolver) -> Response:
    """Every hop is re-validated; the transport must connect to the pinned address (no re-resolution)."""
    for _ in range(MAX_REDIRECTS + 1):
        pinned = check_destination(url, resolver)
        response = transport(url, pinned)
        if response.status in (301, 302, 303, 307, 308):
            if not response.location:
                raise UnsafeDestination('redirect without location')
            url = urljoin(url, response.location)
            continue
        return response
    raise UnsafeDestination('too many redirects')
