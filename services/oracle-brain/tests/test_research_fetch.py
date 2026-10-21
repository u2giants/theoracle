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
