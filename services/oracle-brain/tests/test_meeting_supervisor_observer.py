"""Invented independent signer; no installed supervisor or provider authority."""
import base64,hashlib,json
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.parent_observer_v2 import MeetingSupervisorScopeV1,MeetingSupervisorAdmissionV1,MeetingSupervisorWitnessV1,MEETING_SUPERVISOR_DOMAIN,verify_meeting_supervisor_v1

def packet():
    now=datetime.now(timezone.utc);key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    scope=MeetingSupervisorScopeV1(workspace_id=uuid4(),meeting_id=uuid4(),provider_account='installed-account',create_operation_id=uuid4(),create_request_sha256='a'*64,scheduler_id=uuid4(),scheduler_runtime_sha256='b'*64,scheduler_config_sha256='c'*64,stop_owner_id=uuid4(),stop_runtime_sha256='d'*64,stop_config_sha256='e'*64,capture_until=now+timedelta(seconds=20),stop_valid_from=now-timedelta(seconds=60),stop_until=now+timedelta(seconds=50),original_horizon=now+timedelta(seconds=60),scheduler_poll_seconds=1,stop_request_seconds=3,safety_allowance_seconds=1,stop_margin_seconds=5)
    admission=MeetingSupervisorAdmissionV1(purpose='meeting-supervisor-currentness-v1',scope=scope,principal_id=uuid4(),observer_uri='spiffe://oracle/observer/supervisor',client_uri='spiffe://oracle/meeting/creator',signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest(),issuer_actor=uuid4(),reviewer_actor=uuid4(),minimum_sequence=0,max_age_seconds=5,expires_at=scope.capture_until)
    sha=digest(admission.model_dump(mode='json'));nonce='f'*64
    witness=MeetingSupervisorWitnessV1(purpose='meeting-supervisor-currentness-v1',admission_hash=sha,scope=scope,principal_id=admission.principal_id,observer_uri=admission.observer_uri,client_uri=admission.client_uri,challenge=nonce,sequence=1,scheduler_observation_sha256='1'*64,checked_at=now,expires_at=now+timedelta(seconds=4))
    def sign(witness=witness,domain=MEETING_SUPERVISOR_DOMAIN):
        value=witness.model_dump(mode='json');return canonical_bytes(dict(witness=value,signature=base64.b64encode(key.sign(domain+canonical_bytes(value))).decode()))
    args=dict(admission=admission,trusted_admission_hash=sha,expected_scope=scope,challenge=nonce,previous_sequence=0,started_at=now,now=now+timedelta(seconds=1),elapsed_seconds=1.)
    return sign,args,witness

def test_exact_new_supervisor_domain_and_finite_lease():
    sign,args,w=packet();assert verify_meeting_supervisor_v1(sign(),**args)==w

@pytest.mark.parametrize('changes',[dict(previous_sequence=1),dict(challenge='0'*64),dict(elapsed_seconds=True),dict(elapsed_seconds=float('nan')),dict(elapsed_seconds=6),dict(now=datetime(2040,1,1,tzinfo=timezone.utc))])
def test_replay_nonce_time_and_strict_elapsed_refuse(changes):
    sign,args,_=packet();args.update(changes)
    with pytest.raises((ValueError,PermissionError)):verify_meeting_supervisor_v1(sign(),**args)

@pytest.mark.parametrize('field,value',[('meeting_id',uuid4()),('provider_account','foreign'),('scheduler_config_sha256','0'*64),('stop_owner_id',uuid4()),('create_operation_id',uuid4())])
def test_each_bound_operational_owner_scope_refuses(field,value):
    sign,args,_=packet();args['expected_scope']=args['expected_scope'].model_copy(update={field:value})
    with pytest.raises(PermissionError):verify_meeting_supervisor_v1(sign(),**args)

def test_old_parent_domain_cannot_be_reinterpreted_and_unknown_envelope_refuses():
    sign,args,_=packet()
    from cryptography.exceptions import InvalidSignature
    with pytest.raises(InvalidSignature):verify_meeting_supervisor_v1(sign(domain=b'oracle.complete-parent-currentness-v2\x00'),**args)
    value=json.loads(sign());value['active']=True
    with pytest.raises(PermissionError):verify_meeting_supervisor_v1(canonical_bytes(value),**args)

def test_witness_cannot_extend_capture_or_swap_observed_queue():
    sign,args,w=packet();bad=w.model_copy(update=dict(expires_at=w.scope.capture_until+timedelta(seconds=1)))
    with pytest.raises(PermissionError):verify_meeting_supervisor_v1(sign(bad),**args)
    # Altering concrete scheduler-observation seal without signer is refused.
    value=json.loads(sign());value['witness']['scheduler_observation_sha256']='0'*64
    from cryptography.exceptions import InvalidSignature
    with pytest.raises(InvalidSignature):verify_meeting_supervisor_v1(canonical_bytes(value),**args)

@pytest.mark.parametrize('changes',[
 dict(stop_margin_seconds=4),dict(stop_request_seconds=True),dict(safety_allowance_seconds=0),
 dict(stop_until=datetime(2020,1,1,tzinfo=timezone.utc)),dict(stop_valid_from=datetime(2040,1,1,tzinfo=timezone.utc)),
 dict(stop_margin_seconds=120),
])
def test_stop_window_cannot_be_shortened_below_full_margin_or_renewed(changes):
    _sign,args,_w=packet();scope=args['expected_scope'].model_dump(mode='python');scope.update(changes)
    with pytest.raises(ValueError):MeetingSupervisorScopeV1.model_validate(scope)

def test_stop_only_process_window_can_survive_capture_end_without_witness_extension():
    _sign,args,_w=packet();scope=args['expected_scope']
    assert scope.capture_until<scope.stop_until<=scope.original_horizon
    admission=args['admission'].model_dump(mode='python');admission['expires_at']=scope.stop_until
    with pytest.raises(ValueError):MeetingSupervisorAdmissionV1.model_validate(admission)
