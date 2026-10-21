"""Pure source-rights and resolved-address validation; no network or transport."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Iterable, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import Source


class RightsError(ValueError):
    """Source rights or a supplied destination fails qualification."""


def require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise RightsError(f'{field} must be a bool')
    return value


def require_public_addresses(addresses: Sequence[str]) -> str:
    """Return the first supplied address only if every candidate is global unicast.

    Transition and translation mechanisms are refused without assuming gateway
    policy. The caller remains responsible for actually connecting to this pin.
    """
    if type(addresses) not in (list, tuple):
        raise RightsError('candidate addresses must be a sequence of addresses')
    if not addresses:
        raise RightsError('no candidate address')
    for raw in addresses:
        if type(raw) is not str or '%' in raw:
            raise RightsError('not an ip address')
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as error:
            raise RightsError('not an ip address') from error
        if isinstance(ip, ipaddress.IPv6Address):
            blocked = ('64:ff9b::/96', '64:ff9b:1::/48', '::/96', 'fec0::/10')
            if (ip.ipv4_mapped is not None or ip.sixtofour is not None or
                    ip.teredo is not None or
                    any(ip in ipaddress.IPv6Network(prefix) for prefix in blocked)):
                raise RightsError('refused transition or translated address')
        if (not ip.is_global or ip.is_multicast or ip.is_reserved or
                ip.is_unspecified or ip.is_loopback or ip.is_link_local):
            raise RightsError('refused non-public address')
    return addresses[0]


@dataclass(frozen=True)
class CoverageGap:
    source_id: str
    access: str
    reason: str


def is_authorized(source: Source) -> bool:
    require_bool(source.enabled, 'enabled')
    require_bool(source.rights_confirmed, 'rights_confirmed')
    if source.access not in ('public', 'licensed', 'member'):
        raise RightsError('unknown access')
    return source.enabled and (source.access == 'public' or source.rights_confirmed)


def coverage_gaps(sources: Iterable[Source]) -> tuple[CoverageGap, ...]:
    gaps = []
    for source in sources:
        is_authorized(source)
        if source.access in ('licensed', 'member') and not source.rights_confirmed:
            gaps.append(CoverageGap(source.source_id, source.access, 'paid_access_without_rights'))
        elif not source.enabled:
            gaps.append(CoverageGap(source.source_id, source.access, 'disabled'))
    return tuple(gaps)
