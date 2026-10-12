"""Opaque event jobs bind actor, release, declared process and exact original receipt."""
import base64,json
from datetime import datetime
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from .contracts import digest
from .cutover import selected
from .source_receipts import SourceRef
from .ingest.event_store import import_events
from .ingest.operational_export import Mapping,MAX_BYTES
from oracle_brain.knowledge.authority import _has_authority_conn,_lock

def execute_event(database_url,run_id,workspace_id,ledger,synthetic):
    with psycopg.connect(database_url) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('operating-action:'+str(run_id),))
        row=conn.execute("SELECT actor_id,operation,payload,release_id,release_hash,status,result FROM oracle2.operating_action_runs WHERE run_id=%s AND workspace_id=%s AND expires_at>now()",(run_id,workspace_id)).fetchone()
        if not row or row[1]!='event_import' or row[5] not in {'pending','completed'}:raise PermissionError('action unavailable')
        actor,_,payload,release_id,release_hash,status,result=row
        if actor!=ledger.principal:raise PermissionError('action actor mismatch')
        release=selected(database_url,workspace_id)
        if release.release_id!=release_id or release.content_hash()!=release_hash:raise PermissionError('release changed')
        # Private event admission is a separate gate; this release implements invented imports only.
        if not synthetic or release.acceptance_state!='synthetic':raise PermissionError('private event admission unavailable')
        mapping=Mapping.model_validate_json(json.dumps(payload['mapping']))
        if payload['process_id']!=mapping.process_id:raise ValueError('mapping process mismatch')
        current=ledger.read(workspace_id,release.artifact_id,release.artifact_version)
        processes=[p for model in current['operating_models'] for p in model['processes']]
        process=next((p for p in processes if p['process_id']==mapping.process_id),None)
        if not process or process['scope']!=mapping.scope:raise PermissionError('mapped process outside current declared scope')
        refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in payload['source_refs'])
        if len(refs)!=1:raise ValueError('one exact export source required')
        receipts=ledger.authorize_refs(refs,workspace_id);receipt=receipts[str(refs[0].source_id)]
        if not _has_authority_conn(conn,workspace_id,actor,'event-import:'+mapping.scope):raise PermissionError('current scoped event authority required')
        if status=='completed':return result
        data=base64.b64decode(payload['raw_export_base64'],validate=True)
        if len(data)>MAX_BYTES:raise ValueError('event upload limit exceeded')
        # Release and source checks occur again after parsing within ledger persistence.
        manifest,log=import_events(ledger,receipt,data,format=payload['format'],mapping=mapping,
            window_start=datetime.fromisoformat(payload['window_start']),window_end=datetime.fromisoformat(payload['window_end']),
            permission_digest=release.permission_digest,compiler_digest=release.runtime_digest)
        if selected(database_url,workspace_id)!=release:raise PermissionError('release changed during import')
        ledger.authorize_refs(refs,workspace_id)
        result={'state':'completed','run_id':str(run_id),'import_id':str(log.import_id),'input_hash':log.input_hash,'mapping_hash':log.mapping_hash,
            'accepted_count':len(log.events),'quarantined_count':len(log.quarantined_rows),'quality_notes':list(log.quality_notes),'actual_data_acceptance':'unavailable'}
        conn.execute("UPDATE oracle2.operating_action_runs SET status='completed',result=%s WHERE run_id=%s AND status='pending'",(Jsonb(result),run_id))
        return result


def execute_review(database_url,run_id,workspace_id,ledger,synthetic):
    from .authority_adapter import require_review
    with psycopg.connect(database_url) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('operating-action:'+str(run_id),))
        row=conn.execute("SELECT actor_id,payload,release_id,release_hash,status,result FROM oracle2.operating_action_runs WHERE run_id=%s AND workspace_id=%s AND operation='finding_review' AND expires_at>now()",(run_id,workspace_id)).fetchone()
        if not row or row[0]!=ledger.principal or row[4] not in {'pending','completed'}:raise PermissionError('review action unavailable')
        actor,payload,release_id,release_hash,status,result=row
        release=selected(database_url,workspace_id)
        if not synthetic or release.acceptance_state!='synthetic':raise PermissionError('private review action admission unavailable')
        if release.release_id!=release_id or release.content_hash()!=release_hash:raise PermissionError('review release changed')
        if not isinstance(payload.get('note'),str) or not 1<=len(payload['note'])<=4000:raise ValueError('bounded review note required')
        ledger.read(workspace_id,release.artifact_id,release.artifact_version)
        with psycopg.connect(database_url) as auth_conn:require_review(auth_conn,workspace_id,actor,payload['scope'])
        if status=='completed':return result
        ledger.append_review(workspace_id=workspace_id,artifact_id=release.artifact_id,version=release.artifact_version,
            finding_id=payload['finding_id'],event_id=run_id,action=payload['action'],scope=payload['scope'],note=payload['note'],authority=require_review)
        result={'state':'completed','run_id':str(run_id),'review_recorded':True,'policy_promoted':False}
        conn.execute("UPDATE oracle2.operating_action_runs SET status='completed',result=%s WHERE run_id=%s AND status='pending'",(Jsonb(result),run_id))
        return result
