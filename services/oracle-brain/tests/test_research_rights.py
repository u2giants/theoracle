"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.research.rights is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.research.rights'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        'S10 research rights implementation absent on main (held PR #140 / branch s10-industry-expertise). Named offline gate test retained with the branch assertions; activates when research.rights lands.',
        allow_module_level=True,
    )

"""Pure rights and destination-policy checks. No network, no transport, no credentials."""


import pytest

from oracle_brain.research.registry import Source
from oracle_brain.research.rights import (
    CoverageGap,
    RightsError,
    coverage_gaps,
    is_authorized,
    require_bool,
    require_public_addresses,
)

PUB = Source('pub', 'Pub', 'https://pub.example/a', 'US', 'retail', 'public', 'weekly')
LIC_UNCONFIRMED = Source('lic', 'Pub', 'https://pub.example/b', 'US', 'toys', 'licensed', 'quarterly')
LIC_CONFIRMED = Source('lic-ok', 'Pub', 'https://pub.example/c', 'US', 'toys', 'licensed', 'quarterly', rights_confirmed=True)
MEMBER_NO_RIGHTS = Source('mem', 'Pub', 'https://pub.example/d', 'US', 'x', 'member', 'weekly')
DISABLED = Source('off', 'Pub', 'https://pub.example/e', 'US', 'x', 'public', 'weekly', enabled=False)


def test_require_bool_accepts_only_real_booleans():
    assert require_bool(True, 'enabled') is True
    assert require_bool(False, 'enabled') is False
    for bad in (1, 0, 'yes', 'true', None, [], object()):
        with pytest.raises(RightsError):
            require_bool(bad, 'enabled')


def test_registry_rejects_truthy_non_boolean_flags():
    with pytest.raises(ValueError, match='enabled must be a bool'):
        Source('x', 'P', 'https://p.example/x', 'US', 's', 'public', 'weekly', enabled=1)
    with pytest.raises(ValueError, match='rights_confirmed must be a bool'):
        Source('x', 'P', 'https://p.example/x', 'US', 's', 'public', 'weekly', rights_confirmed='yes')


def test_authorized_public_enabled_and_paid_need_rights():
    assert is_authorized(PUB) is True
    assert is_authorized(LIC_UNCONFIRMED) is False
    assert is_authorized(LIC_CONFIRMED) is True
    assert is_authorized(MEMBER_NO_RIGHTS) is False
    assert is_authorized(DISABLED) is False


def test_coverage_gaps_surface_paid_without_rights_and_disabled():
    gaps = coverage_gaps([PUB, LIC_UNCONFIRMED, LIC_CONFIRMED, MEMBER_NO_RIGHTS, DISABLED])
    assert gaps == (
        CoverageGap('lic', 'licensed', 'paid_access_without_rights'),
        CoverageGap('mem', 'member', 'paid_access_without_rights'),
        CoverageGap('off', 'public', 'disabled'),
    )


def test_coverage_gaps_empty_when_fully_authorized():
    assert coverage_gaps([PUB, LIC_CONFIRMED]) == ()


def test_require_public_addresses_accepts_global_unicast():
    assert require_public_addresses(['8.8.8.8']) == '8.8.8.8'
    assert require_public_addresses(['2001:4860:4860::8888', '8.8.8.8']) == '2001:4860:4860::8888'


def test_require_public_addresses_refuses_private_and_special_use():
    for bad in (
        ['10.0.0.1'],
        ['192.168.1.1'],
        ['127.0.0.1'],
        ['169.254.1.1'],
        ['224.0.0.1'],
        ['0.0.0.0'],
        ['::1'],
        ['fe80::1'],
        ['fc00::1'],
        ['::ffff:10.0.0.1'],
    ):
        with pytest.raises(RightsError):
            require_public_addresses(bad)


def test_require_public_addresses_refuses_empty_and_mixed_sets():
    with pytest.raises(RightsError, match='no candidate address'):
        require_public_addresses([])
    with pytest.raises(RightsError):
        require_public_addresses(['8.8.8.8', '10.0.0.1'])
    with pytest.raises(RightsError, match='not an ip address'):
        require_public_addresses(['example.com'])


def test_register_load_marks_licensed_unconfirmed_as_visible_gap():
    from pathlib import Path

    from oracle_brain.research.registry import load_register

    path = Path(__file__).resolve().parents[3] / 'config' / 'oracle2' / 'industry-sources.yaml'
    sources = load_register(path)
    ids = {s.source_id for s in sources}
    assert {'cpsc-recalls', 'astm-f963', 'ftc-guides'} <= ids
    gaps = coverage_gaps(sources)
    assert gaps == (CoverageGap('astm-f963', 'licensed', 'paid_access_without_rights'),)
    authorized_ids = {s.source_id for s in sources if is_authorized(s)}
    assert 'astm-f963' not in authorized_ids
    assert 'cpsc-recalls' in authorized_ids


def test_parse_register_rejects_duplicate_ids_and_bad_flags():
    from oracle_brain.research.registry import parse_register

    dup = '{"sources": [{"source_id": "a", "publisher": "P", "url": "https://p.example/a", "jurisdiction": "US", "scope": "s", "access": "public", "cadence": "weekly"}, {"source_id": "a", "publisher": "P", "url": "https://p.example/b", "jurisdiction": "US", "scope": "s", "access": "public", "cadence": "weekly"}]}'
    with pytest.raises(ValueError, match='duplicate source_id'):
        parse_register(dup)
    truthy = '{"sources": [{"source_id": "a", "publisher": "P", "url": "https://p.example/a", "jurisdiction": "US", "scope": "s", "access": "public", "cadence": "weekly", "rights_confirmed": 1}]}'
    with pytest.raises(ValueError, match='rights_confirmed must be a bool'):
        parse_register(truthy)
