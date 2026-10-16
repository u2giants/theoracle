"""Exact projector metadata refusals; no authority, key generation or graph calls."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.hosting.paid_projector_v3 import PaidProjectorConfigV3,load_paid_projector_settings_v3


def config():
    workspace,artifact,generation=uuid4(),uuid4(),uuid4();now=datetime.now(timezone.utc)
    name=f'oracle_processing_v1_{workspace.hex}_{artifact.hex}_1_{generation.hex}'
    return dict(worker_config_sha256='a'*64,job_hash='b'*64,workspace_id=workspace,compiler_actor=uuid4(),compiler_login='compiler',runtime_hash='c'*64,
        artifact_id=artifact,artifact_version=1,content_hash='d'*64,projection_digest='e'*64,embedding_dispatch_id=uuid4(),generation=generation,
        graph_name=name,ontology_name=name+'__ontology',graph_hostname='owned-fixture.invalid',graph_port=6379,graph_username='oracle_projector',
        graph_url_file='/fixture/graph-url',graph_url_sha256='1'*64,tls_ca_file='/fixture/ca',tls_ca_sha256='2'*64,
        tls_certificate_file='/fixture/cert',tls_certificate_sha256='3'*64,tls_key_file='/fixture/key',tls_key_sha256='4'*64,
        projector_id=uuid4(),receipt_key_file='/fixture/receipt-key',receipt_key_sha256='5'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),
        valid_from=now,expires_at=now+timedelta(seconds=60))


def test_exact_projector_namespace_and_private_path_schema():
    value=config();assert PaidProjectorConfigV3.model_validate(value).graph_name==value['graph_name']
    for update in ({'graph_name':'other'}, {'ontology_name':value['graph_name']}, {'graph_port':True},
                   {'generation':uuid4()}, {'tls_key_file':value['receipt_key_file']},
                   {'tls_ca_file':'relative'}, {'worker_config_sha256':'placeholder'},
                   {'expires_at':value['valid_from']}, {'issuer_actor':value['compiler_actor']}):
        with pytest.raises(Exception):PaidProjectorConfigV3.model_validate({**value,**update})


def test_projector_startup_never_accepts_foreign_worker_or_caller_json():
    for worker in (None,True,{},object()):
        with pytest.raises(Exception,match='actual compiler worker'):
            load_paid_projector_settings_v3('/absent','a'*64,appointment_path='/absent',
                expected_appointment_sha256='b'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),worker=worker,job={})


def test_projector_authority_refuses_caller_objects_and_deserialized_metadata():
    from oracle_brain.hosting.paid_projector_v3 import PaidProjectorAuthorityV3
    for supplied in (None,True,{},object()):
        with pytest.raises(Exception,match='exact protected projector authority'):
            PaidProjectorAuthorityV3(supplied)


def test_projector_startup_rejects_missing_or_placeholder_external_hashes_before_files():
    for config_hash,appointment_hash in ((None,'b'*64),('a'*64,None),('placeholder','b'*64),('a'*64,'')):
        with pytest.raises(Exception,match='explicit external projector'):
            load_paid_projector_settings_v3('/absent',config_hash,appointment_path='/absent',
                expected_appointment_sha256=appointment_hash,issuer_actor=uuid4(),reviewer_actor=uuid4(),worker=None,job=None)
