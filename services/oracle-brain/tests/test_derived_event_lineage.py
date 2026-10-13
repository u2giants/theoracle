"""Invented trust contexts only: no real capture/authentication/admission proof."""
import base64
from datetime import datetime,timedelta,timezone
import json
from uuid import UUID
import pytest
import psycopg
from test_minimized_observations import invented
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.ingest.minimized_observations import canonical,sha,PROCESS
from oracle_brain.operating_model.ingest.operational_export import Mapping,parse_export
from oracle_brain.operating_model.ingest.derived_event_lineage import (
    EventIntakeAdmission,TrustedEventIntake,admitted_refs,derive_from_receipts)
from oracle_brain.operating_model.ingest.event_store import import_derived_events
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt

NOW=datetime(2026,1,1,tzinfo=timezone.utc)
WORKSPACE=UUID(int=1);ACTOR=UUID(int=2)

@pytest.fixture(autouse=True)
def invented_database_scope(monkeypatch):
    # In-memory stand-in only; positive database persistence is a separate gate.
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(psycopg,'connect',lambda *_:Connection())
    monkeypatch.setattr('oracle_brain.operating_model.ledger._lock',lambda *_:None)
    monkeypatch.setattr('oracle_brain.operating_model.ledger._has_authority_conn',lambda *_:True)

class Blobs:
    def __init__(self):self.puts=[]
    def put(self,workspace,payload):
        self.puts.append(payload);return 'invented-blob',digest(payload)

def context():
    events,references=invented();originals=[canonical(events),canonical(references),b'Invented documented review step']
    receipts=[]
    for index,raw in enumerate(originals,10):
        ref=SourceRef(workspace_id=WORKSPACE,source_id=UUID(int=index),revision=1,
            original_sha256=sha(raw),reading_sha256=sha(raw),parser_id='invented-authoritative-export')
        receipts.append(SourceReceipt(ref=ref,reading=raw.decode(),display_revision='r1'))
    mapping=Mapping(columns={'event_id':'event_id','case_id':'case_id','activity_id':'activity','timestamp':'timestamp','lifecycle':'lifecycle','status':'status'},
        source_system='invented',process_id='invented-documentary-process',scope='invented',
        activity_map={event['activity']:'invented-review' for event in events})
    proof=EventIntakeAdmission(purpose='derived-point-observation-intake',workspace_id=WORKSPACE,
        actor_id=ACTOR,minimized_ref=receipts[0].ref,original_references_ref=receipts[1].ref,
        documentary_refs=(receipts[2].ref,),source_process=PROCESS,
        capture_authenticity='authenticated-original-captures',capture_receipt_hash='a'*64,
        documentary_mapping_receipt_hash='b'*64,mapping_hash=digest(mapping.model_dump(mode='json')),
        permission_digest='c'*64,issuer_actor=UUID(int=3),reviewer_actor=UUID(int=4),
        observed_at=NOW-timedelta(seconds=1),expires_at=NOW+timedelta(seconds=60))
    trust=TrustedEventIntake(admission=proof,trusted_admission_hash=digest(proof.model_dump(mode='json')),
        current_capture_receipt_hash='a'*64,current_mapping_receipt_hash='b'*64,
        current_permission_digest='c'*64,checked_at=NOW)
    return trust,mapping,{str(receipt.ref.source_id):receipt for receipt in receipts}

def make_ledger(trust,receipts,*,resolver=None):
    return Ledger('invented-unused',Blobs(),principal=ACTOR,can_read=lambda *_:True,
        current_source=lambda workspace,source:receipts[str(source)],
        event_intake_resolver=resolver if resolver is not None else lambda _:trust,clock=lambda:NOW)

def derived_payload(trust,mapping,receipts):
    refs=admitted_refs(trust,workspace_id=WORKSPACE,actor_id=ACTOR,mapping=mapping,permission_digest='c'*64,now=NOW)
    data,lineage=derive_from_receipts(trust,receipts)
    log,q=parse_export(data,'csv',WORKSPACE,mapping,NOW,NOW+timedelta(days=1))
    payload={'source_refs':[ref.model_dump(mode='json') for ref in refs],
        'event_import':log.model_dump(mode='json'),'format':'csv','mapping':mapping.model_dump(mode='json'),
        'raw_export_base64':base64.b64encode(data).decode(),'event_derivation':lineage.model_dump(mode='json'),
        'input_bytes_kind':'derived-point-observation-csv','quarantine':list(q),'actual_data_acceptance':'unavailable'}
    return refs,log,payload

def persist(ledger,refs,log,payload):
    return ledger.persist(workspace_id=WORKSPACE,artifact_id=log.import_id,version=1,kind='event_import',
        payload=payload,refs=refs,permission_digest='c'*64,compiler_digest='d'*64)

def test_no_runtime_trust_refuses_before_original_resolution_database_or_blob(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('must not resolve originals or contact database')
    monkeypatch.setattr(psycopg,'connect',denied)
    ledger=Ledger('unused',Blobs(),principal=ACTOR,can_read=denied,current_source=denied)
    trust,mapping,receipts=context()
    with pytest.raises(PermissionError,match='authenticated capture'):
        import_derived_events(ledger,mapping=mapping,window_start=NOW,window_end=NOW+timedelta(days=1),permission_digest='c'*64,compiler_digest='d'*64)
    assert not ledger.blobs.puts

@pytest.mark.parametrize('fault',['self_review','hash','capture','mapping','permission','expiry','clock','actor','missing_documentary_mapping'])
def test_forged_stale_or_changed_external_context_denied(fault):
    trust,mapping,_=context();proof=trust.admission
    if fault=='self_review':
        proof=proof.model_copy(update={'reviewer_actor':proof.issuer_actor})
        trust=trust.model_copy(update={'admission':proof,'trusted_admission_hash':digest(proof.model_dump(mode='json'))})
    elif fault=='hash':trust=trust.model_copy(update={'trusted_admission_hash':'e'*64})
    elif fault=='capture':trust=trust.model_copy(update={'current_capture_receipt_hash':'e'*64})
    elif fault=='mapping':trust=trust.model_copy(update={'current_mapping_receipt_hash':'e'*64})
    elif fault=='permission':trust=trust.model_copy(update={'current_permission_digest':'e'*64})
    elif fault=='expiry':
        proof=proof.model_copy(update={'expires_at':NOW})
        trust=trust.model_copy(update={'admission':proof,'trusted_admission_hash':digest(proof.model_dump(mode='json'))})
    elif fault=='clock':trust=trust.model_copy(update={'checked_at':NOW-timedelta(seconds=16)})
    elif fault=='actor':
        proof=proof.model_copy(update={'actor_id':UUID(int=99)})
        trust=trust.model_copy(update={'admission':proof,'trusted_admission_hash':digest(proof.model_dump(mode='json'))})
    else:mapping=mapping.model_copy(update={'columns':{key:value for key,value in mapping.columns.items() if key!='status'}})
    with pytest.raises(PermissionError):
        admitted_refs(trust,workspace_id=WORKSPACE,actor_id=ACTOR,mapping=mapping,permission_digest='c'*64,now=NOW)

def test_existing_original_refs_remain_distinct_from_derived_csv_identity():
    trust,mapping,receipts=context();data,lineage=derive_from_receipts(trust,receipts)
    assert lineage.minimized_ref==trust.admission.minimized_ref
    assert lineage.original_references_ref==trust.admission.original_references_ref
    assert lineage.documentary_refs==trust.admission.documentary_refs
    assert len({lineage.minimized_export_sha256,lineage.original_references_sha256,lineage.derived_csv_sha256})==3
    assert lineage.derived_csv_sha256==sha(data)

def test_direct_ledger_cannot_launder_derived_csv_as_original(monkeypatch):
    trust,mapping,receipts=context();ledger=make_ledger(trust,receipts)
    refs,log,payload=derived_payload(trust,mapping,receipts)
    payload.pop('event_derivation');payload.pop('input_bytes_kind')
    refs=(refs[0],);payload['source_refs']=[refs[0].model_dump(mode='json')]
    with pytest.raises(ValueError,match='explicit admitted derivation'):persist(ledger,refs,log,payload)
    assert not ledger.blobs.puts

@pytest.mark.parametrize('fault',['csv','original','lineage','missing_label'])
def test_exact_original_reproduction_and_lineage_are_required_before_blob(fault):
    trust,mapping,receipts=context();ledger=make_ledger(trust,receipts)
    refs,log,payload=derived_payload(trust,mapping,receipts)
    if fault=='csv':
        raw=base64.b64decode(payload['raw_export_base64'])+b'\n'
        payload['raw_export_base64']=base64.b64encode(raw).decode();payload['event_import']['input_hash']=sha(raw)
    elif fault=='original':
        original=receipts[str(refs[0].source_id)]
        raw=original.reading+' '
        badref=original.ref.model_copy(update={'reading_sha256':sha(raw.encode())})
        receipts[str(refs[0].source_id)]=original.model_copy(update={'ref':badref,'reading':raw})
    elif fault=='lineage':payload['event_derivation']['derived_csv_sha256']='e'*64
    else:payload.pop('input_bytes_kind')
    with pytest.raises((ValueError,PermissionError)):persist(ledger,refs,log,payload)
    assert not ledger.blobs.puts

def test_transaction_rechecks_external_capture_admission_before_any_insert(monkeypatch):
    trust,mapping,receipts=context();refs,log,payload=derived_payload(trust,mapping,receipts)
    expired_proof=trust.admission.model_copy(update={'expires_at':NOW})
    expired=trust.model_copy(update={'admission':expired_proof,'trusted_admission_hash':digest(expired_proof.model_dump(mode='json'))})
    calls=iter([trust,expired]);ledger=make_ledger(trust,receipts,resolver=lambda _:next(calls));queries=[]
    class Result:
        def fetchone(self):return None
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query,args=None):queries.append(query);return Result()
    monkeypatch.setattr(psycopg,'connect',lambda *_:Connection())
    monkeypatch.setattr('oracle_brain.operating_model.ledger._lock',lambda *_:None)
    with pytest.raises(PermissionError,match='fresh event intake'):persist(ledger,refs,log,payload)
    assert not any(query.lstrip().startswith('INSERT') for query in queries)

def test_import_path_checks_actual_scope_before_current_original_reading(monkeypatch):
    trust,mapping,receipts=context();ledger=make_ledger(trust,receipts)
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(psycopg,'connect',lambda *_:Connection())
    monkeypatch.setattr('oracle_brain.operating_model.ingest.event_store._lock',lambda *_:None)
    monkeypatch.setattr('oracle_brain.operating_model.ingest.event_store._has_authority_conn',lambda *_:False)
    def denied(*args):raise AssertionError('scope denial must precede original reading')
    ledger.current_source=denied
    with pytest.raises(PermissionError,match='current event-import scope'):
        import_derived_events(ledger,mapping=mapping,window_start=NOW,window_end=NOW+timedelta(days=1),permission_digest='c'*64,compiler_digest='d'*64)

def test_admitted_invented_import_keeps_parent_sources_and_explicit_derived_bytes(monkeypatch):
    trust,mapping,receipts=context();ledger=make_ledger(trust,receipts);calls=[]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(psycopg,'connect',lambda *_:Connection())
    monkeypatch.setattr('oracle_brain.operating_model.ingest.event_store._lock',lambda *_:None)
    monkeypatch.setattr('oracle_brain.operating_model.ingest.event_store._has_authority_conn',lambda *_:True)
    ledger.persist=lambda **arguments:calls.append(arguments) or 'invented-manifest'
    manifest,log=import_derived_events(ledger,mapping=mapping,window_start=NOW,window_end=NOW+timedelta(days=1),permission_digest='c'*64,compiler_digest='d'*64)
    assert manifest=='invented-manifest' and len(log.events)==816 and len(log.case_censoring)==360
    assert len(calls[0]['refs'])==3 and calls[0]['refs'][0]==trust.admission.minimized_ref
    payload=calls[0]['payload'];assert payload['input_bytes_kind']=='derived-point-observation-csv'
    assert payload['event_derivation']['derived_csv_sha256']==log.input_hash
    assert payload['event_derivation']['minimized_export_sha256']==trust.admission.minimized_ref.original_sha256
    assert log.input_hash!=trust.admission.minimized_ref.original_sha256
    assert payload['actual_data_acceptance']=='unavailable'

def test_direct_persist_cannot_drop_unmapped_observations_even_with_invented_trust():
    trust,mapping,receipts=context();missing=dict(mapping.activity_map);missing.pop(next(iter(missing)))
    mapping=mapping.model_copy(update={'activity_map':missing})
    proof=trust.admission.model_copy(update={'mapping_hash':digest(mapping.model_dump(mode='json'))})
    trust=trust.model_copy(update={'admission':proof,'trusted_admission_hash':digest(proof.model_dump(mode='json'))})
    ledger=make_ledger(trust,receipts);refs,log,payload=derived_payload(trust,mapping,receipts)
    with pytest.raises(PermissionError,match='complete explicitly mapped'):persist(ledger,refs,log,payload)
    assert not ledger.blobs.puts

def test_direct_persist_scope_denial_precedes_original_reading(monkeypatch):
    trust,mapping,receipts=context();refs,log,payload=derived_payload(trust,mapping,receipts)
    ledger=make_ledger(trust,receipts)
    monkeypatch.setattr('oracle_brain.operating_model.ledger._has_authority_conn',lambda *_:False)
    def denied(*args):raise AssertionError('current scope denial must precede original resolution')
    ledger.current_source=denied
    with pytest.raises(PermissionError,match='before original resolution'):persist(ledger,refs,log,payload)
    assert not ledger.blobs.puts
