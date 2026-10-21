"""Guarded fetch: rejects private/link-local destinations and unsafe redirects. Transport is injected."""
from dataclasses import dataclass
import socket
from typing import Callable
from urllib.parse import urljoin, urlsplit
from .rights import RightsError, require_public_addresses

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


def check_destination(url: str, resolver: Resolver) -> str:
    try:
        if type(url) is not str or any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ValueError('invalid destination')
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username
                or parts.password or parts.port not in (None, 443)):
            raise ValueError('invalid destination')
    except ValueError:
        raise UnsafeDestination('refused HTTPS destination') from None
    try:
        return require_public_addresses(resolver(parts.hostname))
    except RightsError as error:
        raise UnsafeDestination(str(error)) from None


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
