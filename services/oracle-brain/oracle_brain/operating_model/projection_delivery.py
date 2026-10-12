"""The existing outbox carries sealed new-core artifacts, never old accepted policy."""
import json,hmac,hashlib
from datetime import datetime,timezone
import psycopg
from psycopg.types.json import Jsonb
from oracle_brain.knowledge.authority import _lock
from .contracts import ArtifactManifest,canonical_bytes,digest

def signature(secret,payload):
    if len(secret)<32:raise ValueError('projection signing key must have at least 32 bytes')
    return hmac.new(secret,canonical_bytes(payload),hashlib.sha256).hexdigest()

async def project_event(ledger,event,projection,*,secret,projector_id):
    if not projector_id or event.payload.get('namespace')!='oracle_operating_model_v1' or event.operation!='project':raise PermissionError('new artifact projection namespace required')
    manifest=ArtifactManifest.model_validate_json(json.dumps(event.payload['manifest']))
    if (manifest.workspace_id,manifest.artifact_id,manifest.version)!=(event.workspace_id,event.assertion_id,event.revision) or manifest.state!='ready':raise PermissionError('projection event manifest mismatch')
    payload=ledger.read(event.workspace_id,event.assertion_id,event.revision)
    if digest(payload)!=manifest.content_hash:raise PermissionError('projection content seal mismatch')
    count=(await projection.connection.query('MATCH (n) RETURN count(n)')).result_set[0][0]
    if count:
        await projection.load(ledger,event.workspace_id,event.assertion_id,event.revision)
    else:await projection.build(ledger,event.workspace_id,event.assertion_id,event.revision)
    await projection.verify(payload)
    receipt={'schema_version':1,'event_id':str(event.event_id),'workspace_id':str(event.workspace_id),'artifact_id':str(event.assertion_id),'version':event.revision,'content_hash':manifest.content_hash,'source_digest':manifest.source_digest,'permission_digest':manifest.permission_digest,'graph_name':projection.graph_name,'record_digest':digest({'records':projection.records(payload)}),'sdk_version':'1.4.0','projector_id':projector_id,'applied_at':datetime.now(timezone.utc).isoformat()}
    seal=signature(secret,receipt)
    return mark_delivered(ledger,event,receipt,seal,secret=secret)

def mark_delivered(ledger,event,receipt,seal,*,secret):
    if not hmac.compare_digest(signature(secret,receipt),seal):raise PermissionError('forged artifact projection receipt')
    expected={'event_id':str(event.event_id),'workspace_id':str(event.workspace_id),'artifact_id':str(event.assertion_id),'version':event.revision}
    if any(receipt.get(k)!=v for k,v in expected.items()):raise PermissionError('artifact receipt identity mismatch')
    with psycopg.connect(ledger.url) as conn:
        _lock(conn,event.workspace_id)
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'operating-lineage:{event.workspace_id}',))
        row=conn.execute('SELECT workspace_id,assertion_id,revision,operation,payload FROM oracle2.outbox WHERE event_id=%s FOR UPDATE',(event.event_id,)).fetchone()
        if row!=(event.workspace_id,event.assertion_id,event.revision,event.operation,event.payload):raise PermissionError('outbox changed before receipt')
        manifest=ArtifactManifest.model_validate_json(json.dumps(event.payload['manifest']))
        if receipt.get('content_hash')!=manifest.content_hash or receipt.get('source_digest')!=manifest.source_digest or receipt.get('permission_digest')!=manifest.permission_digest or receipt.get('sdk_version')!='1.4.0':raise PermissionError('artifact receipt seal mismatch')
        latest=conn.execute("SELECT max(version) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s AND state='ready'",(event.workspace_id,event.assertion_id)).fetchone()[0]
        if latest!=event.revision:raise PermissionError('stale artifact projection receipt')
        if digest(ledger.read(event.workspace_id,event.assertion_id,event.revision))!=manifest.content_hash:raise PermissionError('current artifact changed before receipt')
        prior=conn.execute('SELECT payload,signature FROM oracle2.operating_projection_receipts WHERE event_id=%s',(event.event_id,)).fetchone()
        if prior:
            # Replay verifies and returns the previously signed delivery; timestamps do not rewrite history.
            if any(prior[0].get(key)!=receipt[key] for key in ('event_id','workspace_id','artifact_id','version','content_hash','source_digest','permission_digest','graph_name','record_digest','sdk_version')):raise ValueError('artifact projection replay changed')
            if not hmac.compare_digest(signature(secret,prior[0]),prior[1]):raise PermissionError('prior receipt signature mismatch')
            return {**prior[0],'signature':prior[1]}
        conn.execute('INSERT INTO oracle2.operating_projection_receipts(event_id,workspace_id,artifact_id,version,payload,signature) VALUES(%s,%s,%s,%s,%s,%s)',(event.event_id,event.workspace_id,event.assertion_id,event.revision,Jsonb(receipt),seal))
        conn.execute('UPDATE oracle2.outbox SET delivered_at=now(),lease_until=NULL WHERE event_id=%s',(event.event_id,))
    return {**receipt,'signature':seal}
