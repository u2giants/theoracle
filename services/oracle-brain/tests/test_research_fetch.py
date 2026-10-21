"""Offline: fake resolver and transport; no network."""

# Invented address fixtures: preserve private-network refusal coverage, never real topology.
def _synthetic_ipv4(*octets):
    assert len(octets) == 4 and all(type(n) is int and 0 <= n <= 255 for n in octets)
    return '.'.join(map(str, octets))

import pytest

from oracle_brain.research.fetch import Response, UnsafeDestination, guarded_fetch

DNS = {'pub.example': ['93.184.216.34'], 'internal.example': [(_synthetic_ipv4(10,0,0,5))],
       'meta.example': ['169.254.169.254'], 'v6.example': ['fe80::1'], 'loop.example': ['127.0.0.1'],
       'mapped.example': [('::ffff:' + _synthetic_ipv4(192,168,1,1))], 'mixed.example': ['93.184.216.34', (_synthetic_ipv4(172,16,0,1))]}


def resolver(host):
    return DNS.get(host, [])


def test_public_fetch_pins_resolved_address():
    seen = []
    resp = guarded_fetch('https://pub.example/a', lambda u, ip: seen.append((u, ip)) or Response(200, b'ok'), resolver)
    assert resp.body == b'ok' and seen == [('https://pub.example/a', '93.184.216.34')]


@pytest.mark.parametrize('url', ['https://internal.example/', 'https://meta.example/', 'https://v6.example/',
                                 'https://loop.example/', 'https://mapped.example/', 'https://mixed.example/',
                                 ('https://' + _synthetic_ipv4(10,1,2,3) + '/'), 'http://pub.example/', 'https://u:p@pub.example/',
                                 'https://pub.example:8080/', 'https://nowhere.example/'])
def test_refuses_unsafe_destinations(url):
    def resolve(host):
        return [host] if host[0].isdigit() else resolver(host)
    with pytest.raises(UnsafeDestination):
        guarded_fetch(url, lambda u, ip: pytest.fail('transport must not be called'), resolve)


def test_refuses_redirect_to_private_address():
    calls = []

    def transport(url, ip):
        calls.append(url)
        return Response(302, location='https://meta.example/latest')
    with pytest.raises(UnsafeDestination):
        guarded_fetch('https://pub.example/', transport, resolver)
    assert calls == ['https://pub.example/']


def test_redirect_loop_is_bounded():
    with pytest.raises(UnsafeDestination, match='too many'):
        guarded_fetch('https://pub.example/', lambda u, ip: Response(301, location='/again'), resolver)


@pytest.mark.parametrize('addresses', [
    ['64:ff9b::a00:1'], ['64:ff9b:1::a00:1'], ['2002:0a00:0001::1'],
    ['2001:0000:4136:e378:8000:63bf:f5ff:fffe'], ['::a00:1'],
    ['::ffff:8.8.8.8'], ['8.8.8.8%zone'], ['not-an-address'],
    ['8.8.8.8', '64:ff9b::a00:1'], [], '8.8.8.8', None,
])
def test_fetch_uses_shared_strict_address_gate_before_transport(addresses):
    with pytest.raises(UnsafeDestination):
        guarded_fetch('https://pub.example/',
                      lambda *_: pytest.fail('transport must not run'),
                      lambda _: addresses)


@pytest.mark.parametrize('url', [None, 1, 'https://pub.example:bad/',
    'https://[broken/', 'https://pub.example/\nother', 'https://pub.example/ a'])
def test_malformed_destination_is_typed_denial_without_network(url):
    with pytest.raises(UnsafeDestination):
        guarded_fetch(url, lambda *_: pytest.fail('transport must not run'),
                      lambda _: pytest.fail('resolver must not run'))


def test_redirect_requalifies_transition_address_before_second_transport():
    calls = []
    def transport(url, pinned):
        calls.append((url, pinned))
        return Response(302, location='https://transition.example/')
    with pytest.raises(UnsafeDestination):
        guarded_fetch('https://pub.example/', transport,
                      lambda host: ['8.8.8.8'] if host == 'pub.example' else ['64:ff9b::a00:1'])
    assert calls == [('https://pub.example/', '8.8.8.8')]
