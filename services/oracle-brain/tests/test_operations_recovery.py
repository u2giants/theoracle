"""Invented recovery orchestration only; no real backup/durable/live claim."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from oracle_brain.operations.recovery import (
    AcceptedEvent, RecoverySnapshot, RecoveryResult, packet_digest, rebuild, replay,
    DeliveryObservation, RetainedDeliveryReceipt, resume,
)
from oracle_brain.sources.withdrawal import DERIVED_STORES, Tombstone


class Store:
    def __init__(self, name, calls, fail=False):
        self.name, self.calls, self.fail = name, calls, fail
    def purge(self, source_id, revision):
        self.calls.append(('purge', self.name, source_id, revision))
        if self.fail:raise OSError('invented store failure')


def event(workspace=None, source=None, **changes):
    values = dict(workspace_id=workspace or uuid4(), event_id=uuid4(),
        source_id=source or uuid4(), sequence=1, revision=1,
        operation='project', payload_digest='a'*64)
    return AcceptedEvent(**(values | changes))


def snapshot(events):
    return RecoverySnapshot(workspace_id=events[0].workspace_id, backup_id=uuid4(),
        events=events, event_packet_digest=packet_digest(events))


def adapters(packet, *, calls=None, fail=None, allowed=None, prior=(), backup=(), current=()):
    calls = [] if calls is None else calls
    return dict(expected_workspace_id=packet.workspace_id,
        stores={name:Store(name,calls,fail==name) for name in DERIVED_STORES},
        backup_tombstones=backup, current_tombstones=current, prior_events=prior,
        current_can_read=allowed or (lambda _:True),
        project=lambda item:calls.append(('project',item.event_id)))


def test_exact_snapshot_rebuild_duplicate_and_nonserving_flags():
    first=event();second=event(first.workspace_id,sequence=2)
    packet=snapshot((first,second));calls=[]
    result=rebuild(packet,**adapters(packet,calls=calls))
    assert result.applied==(first.event_id,second.event_id)
    assert result.accounted_events==(first,second)
    assert result.serving_authorized is False and result.live_proof_required is True
    calls.clear()
    repeated=replay(packet,**adapters(packet,calls=calls,prior=result.accounted_events))
    assert repeated.applied==() and repeated.duplicates==(first.event_id,second.event_id)
    assert calls==[]
    with pytest.raises(ValidationError):
        RecoveryResult(**(result.model_dump() | {'serving_authorized':True}))


def test_equal_event_duplicate_in_packet_projects_once():
    item=event();packet=snapshot((item,item));calls=[]
    result=replay(packet,**adapters(packet,calls=calls))
    assert calls==[('project',item.event_id)]
    assert result.applied==(item.event_id,) and result.duplicates==(item.event_id,)


@pytest.mark.parametrize('damage',['digest','workspace','foreign-event','payload-collision',
    'prior-collision','sequence','revision','unacknowledged','duplicate-sequence'])
def test_bad_packets_denied_before_any_adapter_mutation(damage):
    first=event();second=event(first.workspace_id,first.source_id,sequence=2,revision=2)
    prior=()
    if damage=='foreign-event':second=second.model_copy(update={'workspace_id':uuid4()})
    if damage=='payload-collision':second=first.model_copy(update={'payload_digest':'b'*64})
    if damage=='sequence':second=second.model_copy(update={'sequence':0})
    if damage=='revision':second=second.model_copy(update={'revision':1})
    if damage=='duplicate-sequence':second=second.model_copy(update={'sequence':1})
    if damage=='unacknowledged':second=second.model_copy(update={'acknowledged':False})
    packet=snapshot((first,second))
    if damage=='digest':packet=packet.model_copy(update={'event_packet_digest':'f'*64})
    if damage=='workspace':packet=packet.model_copy(update={'workspace_id':uuid4()})
    if damage=='prior-collision':prior=(first.model_copy(update={'payload_digest':'b'*64}),)
    calls=[];options=adapters(packet,calls=calls,prior=prior,
        current=(Tombstone(str(first.source_id),None),))
    if damage=='workspace':options['expected_workspace_id']=first.workspace_id
    with pytest.raises((ValueError,PermissionError)):
        replay(packet,**options)
    assert calls==[]


def test_old_revision_cannot_follow_prior_reconciled_revision():
    first=event(revision=2);old=event(first.workspace_id,first.source_id,sequence=2,revision=1)
    packet=snapshot((old,));calls=[]
    with pytest.raises(ValueError,match='revision'):
        replay(packet,**adapters(packet,calls=calls,prior=(first,)))
    assert calls==[]


def test_backup_and_current_tombstone_union_all_six_before_projection():
    old=event();current=event(old.workspace_id,sequence=2);keep=event(old.workspace_id,sequence=3)
    packet=snapshot((old,current,keep));calls=[]
    result=replay(packet,**adapters(packet,calls=calls,
        backup=(Tombstone(str(old.source_id),1),),
        current=(Tombstone(str(current.source_id),None),)))
    assert result.blocked==(old.event_id,current.event_id) and result.applied==(keep.event_id,)
    assert result.accounted_events==(old,current,keep)
    assert [row[0] for row in calls]==['purge']*12+['project']
    assert {row[1] for row in calls[:-1]}==set(DERIVED_STORES)


def test_whole_source_tombstone_dominates_revision_without_touching_other_source():
    gone=event();keep=event(gone.workspace_id,sequence=2);packet=snapshot((gone,keep));calls=[]
    result=rebuild(packet,**adapters(packet,calls=calls,
        backup=(Tombstone(str(gone.source_id),1),),
        current=(Tombstone(str(gone.source_id),None),Tombstone(str(gone.source_id),1))))
    assert result.blocked==(gone.event_id,) and result.applied==(keep.event_id,)
    assert len([row for row in calls if row[0]=='purge'])==6
    assert all(row[2:]==(str(gone.source_id),None) for row in calls[:-1])


@pytest.mark.parametrize('name',DERIVED_STORES)
def test_one_store_failure_stops_all_later_callbacks(name):
    item=event();packet=snapshot((item,));calls=[]
    with pytest.raises(OSError,match='invented'):
        replay(packet,**adapters(packet,calls=calls,fail=name,
            current=(Tombstone(str(item.source_id),None),)))
    assert [row[1] for row in calls]==list(DERIVED_STORES[:DERIVED_STORES.index(name)+1])
    assert all(row[0]=='purge' for row in calls)


def test_revoked_source_never_projects_but_unrelated_source_preserved():
    gone=event();keep=event(gone.workspace_id,sequence=2);packet=snapshot((gone,keep));calls=[]
    result=replay(packet,**adapters(packet,calls=calls,allowed=lambda e:e.source_id!=gone.source_id))
    assert calls==[('project',keep.event_id)] and result.blocked==(gone.event_id,)


def test_revocation_during_projection_aborts_before_later_projection():
    first=event();second=event(first.workspace_id,sequence=2);packet=snapshot((first,second));calls=[]
    def allowed(_):return not calls
    with pytest.raises(PermissionError,match='quarantined'):
        replay(packet,**adapters(packet,calls=calls,allowed=allowed))
    assert calls==[('project',first.event_id)]


def test_withdraw_event_purges_and_never_projects_as_fact():
    item=event(operation='withdraw');packet=snapshot((item,));calls=[]
    result=replay(packet,**adapters(packet,calls=calls))
    assert result.applied==(item.event_id,)
    assert len(calls)==6 and all(row[0]=='purge' for row in calls)


@pytest.mark.parametrize('damage',['missing-store','extra-store','bad-tombstone'])
def test_invalid_adapter_population_or_tombstone_fails_before_callbacks(damage):
    item=event();packet=snapshot((item,));calls=[];options=adapters(packet,calls=calls)
    if damage=='missing-store':options['stores'].pop('graph')
    if damage=='extra-store':options['stores']['foreign']=Store('foreign',calls)
    if damage=='bad-tombstone':options['current_tombstones']=(Tombstone(str(item.source_id),True),)
    with pytest.raises(ValueError):replay(packet,**options)
    assert calls==[]


def delivery(state='sent', **changes):
    values=dict(workspace_id=uuid4(),effect_id=uuid4(),intent_digest='a'*64,state=state)
    values.update(changes)
    return DeliveryObservation(**values)


def retained(observation, **changes):
    return RetainedDeliveryReceipt(**(dict(workspace_id=observation.workspace_id,
        effect_id=observation.effect_id,intent_digest=observation.intent_digest,
        receipt_id='retained-invented-receipt') | changes))


def classify(items,**changes):
    options=dict(expected_workspace_id=items[0].workspace_id,current_allowed=lambda _:True,
        host_enabled=True,validate_retained_receipt=lambda _:True)
    return resume(items,**(options | changes))


def test_sent_matching_retained_receipt_preserved_without_send_capability():
    observed=delivery();observed=observed.model_copy(update={'receipt':retained(observed)})
    assert classify((observed,))[0].state=='preserve'
    assert classify((observed,),validate_retained_receipt=lambda _:False)[0].state=='UNKNOWN'
    assert classify((delivery(),))[0].state=='UNKNOWN'


@pytest.mark.parametrize('state',['recorded','pending','failed','uncertain'])
def test_unconfirmed_effect_stays_unknown_even_with_receipt_no_safe_resend(state):
    observed=delivery(state);observed=observed.model_copy(update={'receipt':retained(observed)})
    def forbidden(_):pytest.fail('non-sent effect cannot gain retry authority')
    assert classify((observed,),validate_retained_receipt=forbidden)[0].state=='UNKNOWN'


@pytest.mark.parametrize('options',[{'host_enabled':False},{'current_allowed':lambda _:False}])
def test_current_denial_or_disabled_host_blocks_preservation(options):
    observed=delivery();observed=observed.model_copy(update={'receipt':retained(observed)})
    assert classify((observed,),**options)[0].state=='blocked'


@pytest.mark.parametrize('field',['workspace_id','effect_id','intent_digest'])
def test_receipt_identity_mismatch_denies_before_delivery_observer(field):
    observed=delivery();changed='f'*64 if field=='intent_digest' else uuid4()
    observed=observed.model_copy(update={'receipt':retained(observed,**{field:changed})})
    def forbidden(_):pytest.fail('invalid identity reached observer')
    with pytest.raises(ValueError):classify((observed,),current_allowed=forbidden)


def test_foreign_duplicate_delivery_observation_denied_before_observer():
    first=delivery();foreign=delivery();calls=[]
    for items in ((first,foreign),(first,first)):
        with pytest.raises(PermissionError):
            classify(items,current_allowed=lambda e:calls.append(e) or True)
    assert calls==[]


def test_no_ready_or_send_callback_accepted():
    item=event();packet=snapshot((item,));options=adapters(packet)
    with pytest.raises(TypeError):replay(packet,**options,ready=lambda:None)
    observed=delivery()
    with pytest.raises(TypeError):resume((observed,),expected_workspace_id=observed.workspace_id,
        current_allowed=lambda _:True,host_enabled=True,
        validate_retained_receipt=lambda _:True,send=lambda _:None)


@pytest.mark.parametrize('source',['not-a-uuid','UPPER'])
def test_ambiguous_tombstone_identity_never_silently_misses_withdrawal(source):
    item=event();packet=snapshot((item,));calls=[]
    identity='AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA' if source=='UPPER' else source
    with pytest.raises(ValueError,match='canonical event identity'):
        replay(packet,**adapters(packet,calls=calls,current=(Tombstone(identity,None),)))
    assert calls==[]


def test_projection_failure_leaves_later_events_unattempted():
    first=event();second=event(first.workspace_id,sequence=2);packet=snapshot((first,second));calls=[]
    options=adapters(packet,calls=calls)
    def failure(item):
        calls.append(item.event_id)
        raise OSError('invented projection outage')
    options['project']=failure
    with pytest.raises(OSError,match='projection outage'):replay(packet,**options)
    assert calls==[first.event_id]


def test_snapshot_and_observed_effect_population_bounds():
    item=event()
    with pytest.raises(ValidationError):snapshot((item,)*4097)
    observed=delivery()
    with pytest.raises(ValueError):classify((observed,)*4097)


@pytest.mark.parametrize('allowed',[True,False])
def test_project_then_same_revision_withdrawal_purges_before_any_read_or_projection(allowed):
    first=event();withdraw=event(first.workspace_id,first.source_id,
        sequence=2,revision=1,operation='withdraw')
    packet=snapshot((first,withdraw));calls=[]
    def read(item):
        assert len(calls)==6 and all(row[0]=='purge' for row in calls)
        return allowed
    result=replay(packet,**adapters(packet,calls=calls,allowed=read))
    assert result.blocked==(first.event_id,) and result.applied==(withdraw.event_id,)
    assert len(calls)==6 and all(row[2:]==(str(first.source_id),1) for row in calls)
    assert result.accounted_events==(first,withdraw) and result.serving_authorized is False


def test_withdrawal_of_older_revision_preserves_newer_projection_and_its_order():
    newest=event(revision=2);withdraw=event(newest.workspace_id,newest.source_id,
        sequence=2,revision=1,operation='withdraw')
    packet=snapshot((newest,withdraw));calls=[]
    result=replay(packet,**adapters(packet,calls=calls))
    assert result.applied==(newest.event_id,withdraw.event_id) and result.blocked==()
    assert [row[0] for row in calls]==['purge']*6+['project']
    assert calls[-1]==('project',newest.event_id)
    assert all(row[2:]==(str(newest.source_id),1) for row in calls[:-1])


def test_earlier_withdrawal_prevents_later_same_revision_project_from_serving():
    withdraw=event(operation='withdraw');later=event(withdraw.workspace_id,withdraw.source_id,
        sequence=2,revision=1)
    packet=snapshot((withdraw,later));calls=[]
    result=replay(packet,**adapters(packet,calls=calls))
    assert result.applied==(withdraw.event_id,) and result.blocked==(later.event_id,)
    assert len(calls)==6 and all(row[0]=='purge' for row in calls)


def test_prior_withdrawal_survives_separate_replay_even_with_denied_read():
    withdraw=event(operation='withdraw');later=event(withdraw.workspace_id,withdraw.source_id,
        sequence=2,revision=1)
    packet=snapshot((later,));calls=[]
    result=replay(packet,**adapters(packet,calls=calls,prior=(withdraw,),allowed=lambda _:False))
    assert result.blocked==(later.event_id,) and not result.applied
    assert len(calls)==6 and all(row[0]=='purge' for row in calls)


def test_withdrawal_is_purged_even_when_its_read_observer_would_fail():
    withdraw=event(operation='withdraw');packet=snapshot((withdraw,));calls=[]
    def forbidden(_):pytest.fail('deletion must not depend on read permission')
    result=replay(packet,**adapters(packet,calls=calls,allowed=forbidden))
    assert result.applied==(withdraw.event_id,) and len(calls)==6
