"""Protected executor metadata refusals; native positive uses the sole coherent fixture."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.hosting.paid_executor_v3 import PaidExecutorConfigV3,load_paid_executor_settings_v3,build_paid_executor_projection_v3
from oracle_brain.operating_model.source_receipts import SourceRef

def executor_config():
    workspace,artifact,generation=uuid4(),uuid4(),uuid4();now=datetime.now(timezone.utc)
    actors=[uuid4() for _ in range(6)]
    ref=SourceRef(workspace_id=workspace,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256='b'*64,parser_id='fixture')
    c=dict(workspace_id=workspace,actor_id=actors[0],expected_owner_role='fixture_owner',expected_session_role='fixture_executor',
        runtime_hash='a'*64,source_registry_hash='b'*64,source_refs=(ref,),original_root_hash='c'*64,
        semantic_admission_hash='7'*64,semantic_context_hash='8'*64,original_horizon=now+timedelta(seconds=90),source_expires_at=now+timedelta(seconds=90),database_hostname='fixture.invalid',
        database_port=5432,database_name='fixture',artifact_id=artifact,artifact_version=1,content_hash='d'*64,
        projection_digest='e'*64,receipt_body_hash='f'*64,receipt_signature='1'*64,source_digest='2'*64,permission_digest='3'*64,
        generation=generation,graph_name=f'oracle_processing_v1_{workspace.hex}_{artifact.hex}_1_{generation.hex}',blob_root='/fixture/qualified',
        graph_hostname='fixture.invalid',graph_port=6379,graph_username='fixture_reader',tls_client_uri='spiffe://fixture/executor',
        tls_server_uri='spiffe://fixture/graph',compiler_actor=actors[1],compiler_login='fixture_compiler',compiler_runtime_hash='4'*64,
        compiler_permission_hash='5'*64,semantic_issuer_actor=actors[2],semantic_reviewer_actor=actors[3],
        semantic_valid_from=now,semantic_expires_at=now+timedelta(seconds=90),issuer_actor=actors[4],reviewer_actor=actors[5],
        valid_from=now,expires_at=now+timedelta(seconds=60))
    for name in ('database_url','database_ca','graph_url','tls_ca','tls_certificate','tls_key','semantic_registry'):
        c[name+'_file']='/fixture/'+name;c[name+'_sha256']='6'*64
    return c

def test_executor_exact_metadata_never_accepts_compiler_or_writer_credentials():
    c=executor_config();assert PaidExecutorConfigV3.model_validate(c).actor_id==c['actor_id']
    for update in ({'actor_id':c['compiler_actor']},{'expected_session_role':c['compiler_login']},
        {'source_refs':()},{'source_refs':c['source_refs']*2},{'graph_name':'other'},
        {'expires_at':c['original_horizon']+timedelta(seconds=1)},{'database_port':True},
        {'tls_client_uri':c['tls_server_uri']},{'blob_root':'relative'},
        {'receipt_key_file':'/fixture/forbidden'},{'paid_wire_file':'/fixture/forbidden'}):
        with pytest.raises(Exception):PaidExecutorConfigV3.model_validate({**c,**update})

def test_executor_foreign_pins_and_settings_deny_before_any_file_or_network():
    for h in (None,'','placeholder',True):
        with pytest.raises(PermissionError,match='external protected executor pins required'):
            load_paid_executor_settings_v3('/absent',h,appointment_path='/absent',expected_appointment_sha256='a'*64,
                issuer_actor=uuid4(),reviewer_actor=uuid4())
    for supplied in (None,True,{},object()):
        with pytest.raises(PermissionError,match='actual protected executor settings required'):
            build_paid_executor_projection_v3(supplied)


def test_external_appointment_root_and_admission_cross_substitution_denies():
    from oracle_brain.hosting.paid_executor_v3 import PaidExecutorAppointmentV3,_appointment
    c=PaidExecutorConfigV3.model_validate(executor_config())
    fields=PaidExecutorAppointmentV3.model_fields
    values={k:getattr(c,k) for k in fields if hasattr(c,k)}
    values['config_sha256']='a'*64
    a=PaidExecutorAppointmentV3.model_validate(values)
    _appointment(c,a,'a'*64,c.issuer_actor,c.reviewer_actor,datetime.now(timezone.utc))
    for name,value in [('original_root_hash','0'*64),('semantic_admission_hash','0'*64),
                       ('semantic_context_hash','0'*64),('content_hash','0'*64),('receipt_body_hash','0'*64)]:
        changed=a.model_copy(update={name:value})
        with pytest.raises(PermissionError,match='appointment/config differs'):
            _appointment(c,changed,'a'*64,c.issuer_actor,c.reviewer_actor,datetime.now(timezone.utc))
