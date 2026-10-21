"""Pure rights and destination checks. Invented/synthetic only; no I/O."""
from __future__ import annotations

# Invented address fixtures: preserve private-network refusal coverage, never real topology.
def _synthetic_ipv4(*octets):
    assert len(octets) == 4 and all(type(n) is int and 0 <= n <= 255 for n in octets)
    return '.'.join(map(str, octets))


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
        [(_synthetic_ipv4(10,0,0,1))],
        [(_synthetic_ipv4(192,168,1,1))],
        ['127.0.0.1'],
        ['169.254.1.1'],
        ['224.0.0.1'],
        [(_synthetic_ipv4(0,0,0,0))],
        ['::1'],
        ['fe80::1'],
        ['fc00::1'],
        [('::ffff:' + _synthetic_ipv4(10,0,0,1))],
    ):
        with pytest.raises(RightsError):
            require_public_addresses(bad)


def test_require_public_addresses_refuses_empty_and_mixed_sets():
    with pytest.raises(RightsError, match='no candidate address'):
        require_public_addresses([])
    with pytest.raises(RightsError):
        require_public_addresses(['8.8.8.8', (_synthetic_ipv4(10,0,0,1))])
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


@pytest.mark.parametrize('field', ['source_id', 'publisher', 'url', 'jurisdiction', 'scope', 'access', 'cadence'])
@pytest.mark.parametrize('bad', ['', '  ', None, 1, False, []])
def test_source_requires_typed_nonempty_fields(field, bad):
    row = dict(source_id='s', publisher='P', url='https://p.example/x', jurisdiction='US',
               scope='retail', access='public', cadence='weekly')
    row[field] = bad
    with pytest.raises(ValueError, match=f'{field} must be a nonempty string'):
        Source(**row)


@pytest.mark.parametrize('field', ['enabled', 'rights_confirmed'])
@pytest.mark.parametrize('bad', [1, 0, 'true', 'false', None, [], {}])
def test_source_flags_cannot_be_truthy_or_falsey_substitutes(field, bad):
    with pytest.raises(ValueError, match=f'{field} must be a bool'):
        Source('s', 'P', 'https://p.example/x', 'US', 'retail', 'licensed', 'weekly', **{field: bad})


@pytest.mark.parametrize('url', [
    'http://p.example/', 'https://', 'https://u:p@p.example/', 'https://p.example:8443/',
    'https://p.example:bad/', 'https://[broken/', 'https://p.example/\nprivate',
    'https://p.example/\tprivate', ' https://p.example/', 'https://p.example/\x7f',
])
def test_source_rejects_malformed_or_credentialed_destination(url):
    with pytest.raises(ValueError, match='uncredentialed https destination'):
        Source('s', 'P', url, 'US', 'retail', 'public', 'weekly')


@pytest.mark.parametrize('raw', ['null', '[]', '{}', '{"sources": null}',
    '{"sources": {}}', '{"sources": [null]}', '{"sources": [1]}',
    '{"sources": [[]]}', '{"sources": [{}]}', '{"sources": [], "unknown": 1}'])
def test_register_refuses_malformed_shapes(raw):
    from oracle_brain.research.registry import parse_register
    with pytest.raises(ValueError):
        parse_register(raw)


@pytest.mark.parametrize('raw', [
    '64:ff9b::a00:1', '64:ff9b:1::a00:1', '2002:0a00:0001::1',
    '2001:0000:4136:e378:8000:63bf:f5ff:fffe', '::a00:1',
    '::ffff:' + _synthetic_ipv4(10, 0, 0, 1), 'fec0::1', 'ff0e::1',
    _synthetic_ipv4(100, 64, 0, 1),
    '2001:db8::1', '8.8.8.8%zone', None, 134744072,
])
def test_public_address_gate_refuses_transition_and_non_unicast_candidates(raw):
    with pytest.raises(RightsError):
        require_public_addresses(['8.8.8.8', raw])


def test_approved_rights_never_turn_on_a_disabled_source():
    source = Source('s', 'P', 'https://p.example/', 'US', 'retail', 'licensed', 'weekly',
                    enabled=False, rights_confirmed=True)
    assert source.authorized is False
    assert coverage_gaps([source]) == (CoverageGap('s', 'licensed', 'disabled'),)


@pytest.mark.parametrize('addresses', [iter(['8.8.8.8']), iter([]), {'8.8.8.8'}, None])
def test_address_gate_requires_an_indexable_explicit_candidate_population(addresses):
    with pytest.raises(RightsError, match='sequence'):
        require_public_addresses(addresses)
