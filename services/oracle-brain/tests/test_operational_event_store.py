from datetime import datetime,timezone
from uuid import uuid4
import hashlib,json,os
from pathlib import Path
import pytest,psycopg
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt
from oracle_brain.operating_model.ingest.operational_export import Mapping
from oracle_brain.operating_model.ingest.event_store import import_events
from oracle_brain.operating_model.contracts import digest


def test_raw_event_import_manifest_index_and_replay_are_atomic(admin_url,tmp_path):
    with psycopg.connect(admin_url) as conn:conn.execute((Path(__file__).parents[1]/'sql/004_workflow_integrity.sql').read_text())
    workspace,actor,source=uuid4(),uuid4(),uuid4()
    raw=b'id,case,activity,time\nE,C,Review,2026-01-01T00:00:00Z\n';seal=hashlib.sha256(raw).hexdigest()
    receipt=SourceReceipt(ref=SourceRef(workspace_id=workspace,source_id=source,revision=1,original_sha256=seal,reading_sha256=seal,parser_id='synthetic-csv'),reading=raw.decode(),display_revision='r1')
    ledger=Ledger(admin_url,FileBlobStore(tmp_path),principal=actor,can_read=lambda *_:True,current_source=lambda *_:receipt)
    mapping=Mapping(columns={'event_id':'id','case_id':'case','activity_id':'activity','timestamp':'time'},source_system='invented',process_id='review',scope='synthetic',activity_map={'Review':'review-step'})
    args=dict(format='csv',mapping=mapping,window_start=datetime(2026,1,1,tzinfo=timezone.utc),window_end=datetime(2026,1,2,tzinfo=timezone.utc),permission_digest='a'*64,compiler_digest='b'*64)
    with pytest.raises(PermissionError,match='scope'):import_events(ledger,receipt,raw,**args)
    # Direct fixture grant is synthetic setup, never a production owner shortcut.
    with psycopg.connect(admin_url) as conn:conn.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(uuid4(),workspace,actor,uuid4()))
    manifest,log=import_events(ledger,receipt,raw,**args)
    assert len(log.events)==1 and ledger.read(workspace,log.import_id,1)['raw_export_base64']
    assert import_events(ledger,receipt,raw,**args)[0]==manifest
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.operational_imports WHERE workspace_id=%s',(workspace,)).fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s',(workspace,)).fetchone()[0]==1
    modified=ledger.read(workspace,log.import_id,1);modified['event_import']['events'][0]['activity_id']='invented-unmapped'
    with pytest.raises(ValueError,match='reproduce exact raw'):ledger.persist(workspace_id=workspace,artifact_id=log.import_id,version=2,kind='event_import',payload=modified,refs=(receipt.ref,),permission_digest='a'*64,compiler_digest='b'*64)
