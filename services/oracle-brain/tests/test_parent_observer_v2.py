"""Synthetic independent fixture key only; no observer/admission is deployed."""
import base64
import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.parent_observer_v2 import (
    DOMAIN,ParentObserverAdmissionV2,ParentCurrentnessWitnessV2,verify_parent_currentness_v2)
from test_purpose_context_v2 import qualification


def fixture():
    _,population,_,now,_=qualification('census')
    key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    admission=ParentObserverAdmissionV2(purpose='complete-parent-currentness-v2',population=population,
        principal_id=uuid4(),observer_uri='spiffe://oracle/complete-parent-observer',
        client_uri='spiffe://oracle/census-provider',signing_public_key=public.hex(),
        signing_key_fingerprint=hashlib.sha256(public).hexdigest(),issuer_actor=uuid4(),
        reviewer_actor=uuid4(),minimum_sequence=12,max_age_seconds=5,expires_at=population.expires_at)
    witness=ParentCurrentnessWitnessV2(purpose='complete-parent-currentness-v2',
        admission_hash=digest(admission.model_dump(mode='json')),challenge='a'*64,sequence=13,
        population=population,principal_id=admission.principal_id,observer_uri=admission.observer_uri,
        client_uri=admission.client_uri,checked_at=now,expires_at=now+timedelta(seconds=5),revoked=False)
    return key,admission,witness,now


def signed(key,witness):
    payload=witness.model_dump(mode='json')
    return canonical_bytes({'witness':payload,'signature':base64.b64encode(
        key.sign(DOMAIN+canonical_bytes(payload))).decode()})


def verify(key,admission,witness,baseline_now,**changes):
    args=dict(admission=admission,trusted_admission_hash=digest(admission.model_dump(mode='json')),
        expected_population=admission.population,challenge='a'*64,previous_sequence=12,
        started_at=baseline_now,now=baseline_now+timedelta(milliseconds=10),elapsed_seconds=.01)
    args.update(changes)
    return verify_parent_currentness_v2(signed(key,witness),**args)


def test_fresh_domain_separated_challenge_authenticates_all_three_source_metadata():
    key,a,w,now=fixture()
    assert len(verify(key,a,w,now).population.source_refs)==3
    assert '"reading":' not in signed(key,w).decode()


@pytest.mark.parametrize('damage',('key','purpose','challenge','replay','stale','future','parent',
    'revoked','omitted-third','reordered','principal','uri','overlong','roundtrip','admission',
    'initial-counter-rollback'))
def test_currentness_never_accepts_old_file_or_borrowed_coverage_signer(damage):
    key,a,w,now=fixture();args={}
    if damage=='key':key=Ed25519PrivateKey.generate()
    elif damage=='purpose':w=w.model_copy(update={'purpose':'key-coverage'})
    elif damage=='challenge':args['challenge']='b'*64
    elif damage=='replay':args['previous_sequence']=13
    elif damage=='stale':args.update(now=now+timedelta(seconds=6),elapsed_seconds=6)
    elif damage=='future':w=w.model_copy(update={'checked_at':now+timedelta(seconds=1)})
    elif damage=='parent':w=w.model_copy(update={'population':w.population.model_copy(update={'parent_registry_sha256':'f'*64})})
    elif damage=='revoked':w=w.model_copy(update={'revoked':True})
    elif damage=='omitted-third':w=w.model_copy(update={'population':w.population.model_copy(update={'source_refs':w.population.source_refs[:-1]})})
    elif damage=='reordered':w=w.model_copy(update={'population':w.population.model_copy(update={'source_refs':tuple(reversed(w.population.source_refs))})})
    elif damage=='principal':w=w.model_copy(update={'principal_id':uuid4()})
    elif damage=='uri':w=w.model_copy(update={'client_uri':'spiffe://oracle/other'})
    elif damage=='overlong':w=w.model_copy(update={'expires_at':now+timedelta(seconds=6)})
    elif damage=='roundtrip':args['elapsed_seconds']=5.001
    elif damage=='admission':args['trusted_admission_hash']='0'*64
    elif damage=='initial-counter-rollback':args['previous_sequence']=11
    with pytest.raises((PermissionError,ValueError,InvalidSignature)):verify(key,a,w,now,**args)


def provision(tmp_path,admission,*,namespace='parent-v2'):
    """Explicit invented external provisioning, never runtime automatic init."""
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    tmp_path.chmod(0o700)
    initial={'schema_version':2,'namespace':namespace,'appointment_hash':digest(admission.model_dump(mode='json')),
             'minimum_sequence':admission.minimum_sequence}
    for name,payload in [(namespace+'-init.json',canonical_bytes(initial)),
        (namespace+'-state.json',canonical_bytes({**initial,'sequence':admission.minimum_sequence})),
        (namespace+'-lock',b'')]:
        path=tmp_path/name;path.write_bytes(payload);path.chmod(0o600)
    kwargs=dict(namespace=namespace,appointment_hash=initial['appointment_hash'],
        minimum_sequence=admission.minimum_sequence,
        initialization_receipt_hash=hashlib.sha256(canonical_bytes(initial)).hexdigest())
    return DurableNonceSequenceV2(tmp_path,**kwargs),kwargs


def test_durable_observer_challenge_and_highwater_survive_restart(tmp_path):
    from oracle_brain.hosting.parent_observer_v2 import ParentObserverTransportV2,ParentCurrentnessConsumerV2
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    key,a,w,now=fixture();replay,kwargs=provision(tmp_path,a)
    class Transport(ParentObserverTransportV2):
        def fetch_current(self,challenge):
            return signed(key,w.model_copy(update={'challenge':challenge}))
    consumer=ParentCurrentnessConsumerV2(admission=a,trusted_admission_hash=kwargs['appointment_hash'],
        transport=Transport(),replay=replay,clock=lambda:now,monotonic=lambda:0.)
    assert consumer.current(a.population).sequence==13
    restarted=DurableNonceSequenceV2(tmp_path,**kwargs)
    assert restarted._read()['sequence']==13
    # Same signed sequence with a fresh challenge remains a replay after restart.
    consumer.replay=restarted
    with pytest.raises(PermissionError,match='sequence'):consumer.current(a.population)
    assert len(list(tmp_path.glob('parent-v2-nonce-*')))==2


@pytest.mark.parametrize('damage',('missing-state','missing-lock','symlink-state','corrupt-state',
    'rollback','partial-journal','foreign-appointment','permissive-state','deleted-journal'))
def test_replay_store_never_reinitializes_missing_corrupt_or_rolled_back_epoch(tmp_path,damage):
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    key,a,w,now=fixture();store,kwargs=provision(tmp_path,a)
    store.claim('a'*64);store.advance('a'*64,13,verify=lambda previous:None)
    state=tmp_path/'parent-v2-state.json'
    if damage=='missing-state':state.unlink()
    elif damage=='missing-lock':(tmp_path/'parent-v2-lock').unlink()
    elif damage=='symlink-state':state.rename(tmp_path/'other');state.symlink_to(tmp_path/'other')
    elif damage=='corrupt-state':state.write_bytes(b'{')
    elif damage=='rollback':
        value=__import__('json').loads(state.read_bytes());value['sequence']=12;state.write_bytes(canonical_bytes(value))
    elif damage=='partial-journal':
        journal=tmp_path/'parent-v2-sequence-14.json'
        value=__import__('json').loads((tmp_path/'parent-v2-sequence-13.json').read_bytes())
        value['sequence']=14;journal.write_bytes(canonical_bytes(value));journal.chmod(0o600)
    elif damage=='foreign-appointment':kwargs['appointment_hash']='f'*64
    elif damage=='permissive-state':state.chmod(0o644)
    elif damage=='deleted-journal':(tmp_path/'parent-v2-sequence-13.json').unlink()
    with pytest.raises((PermissionError,ValueError,FileNotFoundError)):
        DurableNonceSequenceV2(tmp_path,**kwargs)


def test_challenge_claim_and_commit_are_single_use_and_out_of_order_fails_closed(tmp_path):
    _,a,_,_=fixture();store,_=provision(tmp_path,a)
    store.claim('a'*64);store.claim('b'*64)
    store.advance('b'*64,14,verify=lambda previous:None)
    with pytest.raises(PermissionError):store.advance('a'*64,13,verify=lambda _:None)
    with pytest.raises(FileExistsError):store.claim('a'*64)
    with pytest.raises(PermissionError):store.advance('b'*64,15,verify=lambda _:None)
    assert store._read()['sequence']==14


def test_signature_failure_never_advances_durable_sequence(tmp_path):
    _,a,_,_=fixture();store,_=provision(tmp_path,a);store.claim('a'*64)
    def deny(_):raise PermissionError('synthetic invalid signature')
    with pytest.raises(PermissionError):store.advance('a'*64,13,verify=deny)
    assert store._read()['sequence']==12
    assert not list(tmp_path.glob('parent-v2-sequence-*'))


def test_failed_verification_cannot_retry_same_claimed_challenge(tmp_path):
    _,a,_,_=fixture();store,_=provision(tmp_path,a);store.claim('a'*64)
    def deny(_):raise PermissionError('invalid signature')
    with pytest.raises(PermissionError):store.advance('a'*64,13,verify=deny)
    with pytest.raises(FileExistsError):store.advance('a'*64,13,verify=lambda _:None)


def test_two_process_style_stores_cannot_claim_same_nonce(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    _,a,_,_=fixture();first,kwargs=provision(tmp_path,a)
    second=DurableNonceSequenceV2(tmp_path,**kwargs)
    def claim(store):
        try:store.claim('a'*64);return 'claimed'
        except FileExistsError:return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(claim,(first,second)))
    assert sorted(results)==['claimed','denied']


def test_crash_after_journal_before_highwater_commit_fences_epoch(tmp_path,monkeypatch):
    import os
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    _,a,_,_=fixture();store,kwargs=provision(tmp_path,a);store.claim('a'*64)
    def fail_replace(*_):raise OSError('invented crash before state commit')
    with monkeypatch.context() as patch:
        patch.setattr(os,'replace',fail_replace)
        with pytest.raises(OSError):store.advance('a'*64,13,verify=lambda _:None)
    with pytest.raises(PermissionError,match='partial commit'):
        DurableNonceSequenceV2(tmp_path,**kwargs)
    assert (tmp_path/'parent-v2-sequence-13.json').exists()


def test_foreign_owner_spool_denies_without_creating_state(tmp_path,monkeypatch):
    import os
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    _,a,_,_=fixture();_,kwargs=provision(tmp_path,a)
    actual=os.geteuid()
    monkeypatch.setattr(os,'geteuid',lambda:actual+1)
    with pytest.raises(PermissionError,match='own protected'):
        DurableNonceSequenceV2(tmp_path,**kwargs)
