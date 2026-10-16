"""Actual local mTLS/HMAC transport with invented metadata authority only."""
from dataclasses import asdict
import json
import threading

import pytest

from oracle_brain.hosting.gateway import server_tls
from oracle_brain.hosting.processing_profile import processing_gateway
from oracle_brain.operating_model.processing_context import ProcessingProjection
from test_processing_context import processing, metadata_profile
from test_hosting_boundary import certificates, send, KEY


@pytest.fixture
def processing_server(processing,tmp_path,certificates):
    custody,authority,current,opaque=metadata_profile(processing,tmp_path)
    tls=server_tls(certfile=str(certificates/'server.pem'),keyfile=str(certificates/'server.key'),cafile=str(certificates/'ca.pem'))
    server=processing_gateway(('127.0.0.1',0),tls=tls,signing_key=KEY,custody=custody)
    thread=threading.Thread(target=server.serve_forever, kwargs={'poll_interval':0.01},daemon=True);thread.start()
    yield server,custody,authority,opaque
    server.shutdown();server.server_close();thread.join(2)


def test_processing_profile_uses_existing_actual_peer_and_hmac(processing_server,certificates):
    server,custody,authority,opaque=processing_server
    gateway=(server,)
    assert send(gateway,certificates,asdict(opaque),identity='other')[0]==403
    assert send(gateway,certificates,asdict(opaque),signed=False)[0]==403
    injected={**asdict(opaque),'actor_id':'request-cannot-be-authority'}
    assert send(gateway,certificates,injected)[0]==403
    assert not authority.calls
    assert send(gateway,certificates,asdict(opaque))[0]==202
    assert len(authority.calls)==1
    assert send(gateway,certificates,asdict(opaque))[0]==403
    body=b''.join(p.read_bytes() for p in custody.spool.glob('*.pending'))
    assert b'synthetic source' not in body and b'messages' not in body


def test_processing_profile_revocation_rechecked_on_same_live_server(processing_server,certificates):
    server,custody,authority,opaque=processing_server
    authority.active=False
    assert send((server,),certificates,asdict(opaque))[0]==403
    assert not list(custody.spool.glob('*.pending'))


def test_processing_gateway_metadata_cannot_select_weaker_documentary_mode(processing):
    value=json.loads(processing['pp'].read_bytes())
    value['descriptor']['purpose']='documentary-view'
    with pytest.raises(ValueError):ProcessingProjection.model_validate_json(json.dumps(value))
    value=json.loads(processing['pp'].read_bytes());value['processing']=False
    with pytest.raises(ValueError):ProcessingProjection.model_validate_json(json.dumps(value))
