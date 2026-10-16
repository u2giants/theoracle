"""Pure rights and destination-policy checks for industry sources. No network, no transport."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .registry import Source

ACCESS_PUBLIC = 'public'
ACCESS_LICENSED = 'licensed'
ACCESS_MEMBER = 'member'
PAID_ACCESS = frozenset({ACCESS_LICENSED, ACCESS_MEMBER})


class RightsError(ValueError):
    """A rights or destination policy check failed."""


def require_bool(value: Any, field: str) -> bool:
    """Strict boolean gate: reject truthy non-booleans that could authorize unlicensed use."""
    if type(value) is not bool:
        raise RightsError(f'{field} must be a bool, got {type(value).__name__}')
    return value


def require_public_addresses(addresses: Sequence[str]) -> str:
    """Pure pin-target validation: every candidate address must be public unicast.

    Returns the first address when the whole set is acceptable. Does not resolve
    names or open sockets — callers supply already-resolved addresses.
    """
    if not addresses:
        raise RightsError('no candidate address')
    first: str | None = None
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw.split('%')[0])
        except ValueError as exc:
            raise RightsError(f'not an ip address: {raw!r}') from exc
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if ip.is_private or ip.is_link_local or ip.is_loopback or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise RightsError(f'refused non-public address {raw}')
        if not ip.is_global:
            raise RightsError(f'refused non-global address {raw}')
        if first is None:
            first = raw
    assert first is not None
    return first


@dataclass(frozen=True)
class CoverageGap:
    source_id: str
    access: str
    reason: str


def is_authorized(source: Source) -> bool:
    """Public sources are authorized when enabled; paid/member need confirmed rights."""
    require_bool(source.enabled, 'enabled')
    require_bool(source.rights_confirmed, 'rights_confirmed')
    return source.enabled and (source.access == ACCESS_PUBLIC or source.rights_confirmed)


def coverage_gaps(sources: Iterable[Source]) -> tuple[CoverageGap, ...]:
    """Licensed/member sources without rights are visible gaps, never silently dropped."""
    gaps: list[CoverageGap] = []
    for source in sources:
        require_bool(source.enabled, 'enabled')
        require_bool(source.rights_confirmed, 'rights_confirmed')
        if source.access in PAID_ACCESS and not source.rights_confirmed:
            gaps.append(CoverageGap(source.source_id, source.access, 'paid_access_without_rights'))
        elif not source.enabled:
            gaps.append(CoverageGap(source.source_id, source.access, 'disabled'))
    return tuple(gaps)
