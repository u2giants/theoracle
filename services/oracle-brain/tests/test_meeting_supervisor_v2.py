"""Invented independent keys and profiles; no installed process acceptance."""
import base64,hashlib,json
from datetime import timedelta
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.parent_observer_v2 import (MeetingSupervisorAdmissionV2,MeetingSupervisorWitnessV2,
 MEETING_SUPERVISOR_DOMAIN_V2,MEETING_SUPERVISOR_DOMAIN,verify_meeting_supervisor_v1,verify_meeting_supervisor_v2)
from test_meeting_supervisor_observer import packet

def packet_v2():
    _,args,old=packet();key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    value=args['admission'].model_dump(mode='python');value.update(schema_version=2,purpose='meeting-supervisor-currentness-v2',scheduler_process_sha256='7'*64,stop_process_sha256='8'*64,max_age_seconds=2,signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest())
    admission=MeetingSupervisorAdmissionV2.model_validate(value);sha=digest(admission.model_dump(mode='json'))
    value=old.model_dump(mode='python');value.update(schema_version=2,purpose=admission.purpose,admission_hash=sha,scheduler_process_sha256=admission.scheduler_process_sha256,stop_process_sha256=admission.stop_process_sha256,expires_at=old.checked_at+timedelta(seconds=2))
    witness=MeetingSupervisorWitnessV2.model_validate(value)
    def sign(w=witness,domain=MEETING_SUPERVISOR_DOMAIN_V2,signer=key):
        value=w.model_dump(mode='json');return canonical_bytes(dict(witness=value,signature=base64.b64encode(signer.sign(domain+canonical_bytes(value))).decode()))
    args.update(admission=admission,trusted_admission_hash=sha)
    return sign,args,witness

def test_v2_exact_installed_process_commitments_and_independent_signature():
    sign,args,w=packet_v2();assert verify_meeting_supervisor_v2(sign(),**args)==w

@pytest.mark.parametrize('field',['scheduler_process_sha256','stop_process_sha256'])
def test_signed_other_installed_profile_cannot_match_admission(field):
    sign,args,w=packet_v2()
    with pytest.raises(PermissionError):verify_meeting_supervisor_v2(sign(w.model_copy(update={field:'0'*64})),**args)

@pytest.mark.parametrize('change',[dict(previous_sequence=1),dict(challenge='0'*64),dict(elapsed_seconds=2.01),dict(elapsed_seconds=True)])
def test_v2_replay_deadline_and_nonce_refusal(change):
    sign,args,_=packet_v2();args.update(change)
    with pytest.raises((PermissionError,ValueError)):verify_meeting_supervisor_v2(sign(),**args)

def test_v1_admission_or_domain_never_satisfies_v2():
    oldsign,oldargs,_=packet()
    with pytest.raises(PermissionError):verify_meeting_supervisor_v2(oldsign(),**oldargs)
    sign,args,_=packet_v2()
    with pytest.raises(PermissionError):verify_meeting_supervisor_v1(sign(),**args)
    with pytest.raises(InvalidSignature):verify_meeting_supervisor_v2(sign(domain=MEETING_SUPERVISOR_DOMAIN),**args)
    with pytest.raises(InvalidSignature):verify_meeting_supervisor_v2(sign(signer=Ed25519PrivateKey.generate()),**args)

@pytest.mark.parametrize('field,value',[('schema_version',True),('schema_version',1),('max_age_seconds',True),('max_age_seconds',3)])
def test_v2_schema_and_freshness_are_exact(field,value):
    _,args,_=packet_v2();d=args['admission'].model_dump(mode='python');d[field]=value
    with pytest.raises(ValueError):MeetingSupervisorAdmissionV2.model_validate(d)

@pytest.mark.parametrize('field,value',[('principal_id',__import__('uuid').uuid4()),('observer_uri','spiffe://oracle/other/observer'),('client_uri','spiffe://oracle/other/client')])
def test_v2_signed_wrong_independent_identity_refused(field,value):
    sign,args,w=packet_v2()
    with pytest.raises(PermissionError):verify_meeting_supervisor_v2(sign(w.model_copy(update={field:value})),**args)

def test_v2_witness_stale_or_expired_never_opens_currentness():
    sign,args,w=packet_v2();args['now']=w.checked_at+timedelta(seconds=2)
    with pytest.raises(PermissionError):verify_meeting_supervisor_v2(sign(),**args)

def test_v2_observer_protocol_has_no_v1_request_fallback_or_unknown_fields():
    from oracle_brain.hosting.meeting_supervisor_observer_v1 import parse_supervisor_request_v1,parse_supervisor_request_v2
    _,args,_=packet_v2();q=dict(schema_version=2,purpose='meeting-supervisor-currentness-v2',challenge='f'*64,caller_deadline=args['started_at'].isoformat().replace('+00:00','Z'))
    assert parse_supervisor_request_v2(canonical_bytes(q)).schema_version==2
    with pytest.raises(ValueError):parse_supervisor_request_v1(canonical_bytes(q))
    q['schema_version']=1;q['purpose']='meeting-supervisor-currentness-v1'
    with pytest.raises(ValueError):parse_supervisor_request_v2(canonical_bytes(q))
    q.update(schema_version=2,purpose='meeting-supervisor-currentness-v2',active=True)
    with pytest.raises(ValueError):parse_supervisor_request_v2(canonical_bytes(q))
