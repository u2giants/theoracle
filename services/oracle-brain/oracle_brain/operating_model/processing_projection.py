"""Bounded existing-queue processing delivery; graph work never holds SQL locks."""
from dataclasses import dataclass
from datetime import datetime,timezone
import json,re
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from oracle_brain.models import ProjectionEvent
from .contracts import ArtifactManifest,digest
from .processing_ledger import ProcessingCompilerLedger
from .projection_delivery import signature


@dataclass(frozen=True)
class ProcessingProjectionLease:
    event:ProjectionEvent
    lease_role:str
    lease_token:UUID
    lease_until:datetime


def _compiler(ledger):
    if not isinstance(ledger,ProcessingCompilerLedger):
        raise PermissionError('trusted processing compiler delivery context required')
    return ledger.processing_sources.binding


def lease_processing_projection(ledger,workspace_id,*,lease_seconds=60):
    binding=_compiler(ledger)
    if not isinstance(workspace_id,UUID) or type(lease_seconds) is not int or not 1<=lease_seconds<=60:
        raise PermissionError('bounded exact processing workspace lease required')
    with psycopg.connect(ledger.url) as conn:
        ledger.processing_sources._check(conn)
        row=conn.execute('SELECT oracle2.lease_processing_projection(%s,%s,%s,%s)',
            (workspace_id,binding.runtime_hash,binding.source_registry_hash,lease_seconds)).fetchone()
        ledger.processing_sources._check(conn)
    if not row or row[0] is None:return None
    r=row[0]
    event=ProjectionEvent(UUID(r['event_id']),UUID(r['workspace_id']),UUID(r['assertion_id']),r['revision'],r['operation'],r['payload'],r['attempts'])
    until=datetime.fromisoformat(r['lease_until'])
    if (r['lease_role']!=binding.expected_session_role or until.tzinfo is None
            or until<=datetime.now(timezone.utc) or event.workspace_id!=workspace_id):
        raise PermissionError('processing lease context differs')
    return ProcessingProjectionLease(event,r['lease_role'],UUID(r['lease_token']),until)


def acknowledge_processing_projection(ledger,lease,receipt,seal,*,secret):
    """Trusted application verified graph/HMAC; SQL cannot observe that network."""
    import hmac
    binding=_compiler(ledger)
    if not isinstance(lease,ProcessingProjectionLease) or lease.lease_role!=binding.expected_session_role:
        raise PermissionError('actual current lease owner required')
    if not hmac.compare_digest(signature(secret,receipt),seal):raise PermissionError('processing receipt signature differs')
    event=lease.event
    manifest,payload=ledger.read_with_manifest(event.workspace_id,event.assertion_id,event.revision)
    horizon=getattr(ledger.processing_read_guard,'valid_until',None)
    if not callable(horizon):raise PermissionError('trusted processing semantic horizon required')
    semantic_deadline=horizon(manifest,payload,ledger.principal,ledger.clock())
    if (not isinstance(semantic_deadline,datetime) or semantic_deadline.tzinfo is None
            or semantic_deadline.utcoffset() is None or semantic_deadline<=datetime.now(timezone.utc)):
        raise PermissionError('current trusted semantic horizon required')
    deadline=min(binding.expires_at,semantic_deadline,lease.lease_until)
    event=lease.event
    with psycopg.connect(ledger.url) as conn:
        ledger.processing_sources._check(conn)
        row=conn.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (event.event_id,event.workspace_id,lease.lease_token,event.attempts,Jsonb(receipt),seal,
             binding.runtime_hash,binding.source_registry_hash,deadline)).fetchone()
        ledger.processing_sources._check(conn)
        if conn.execute('SELECT clock_timestamp()<%s',(deadline,)).fetchone()[0] is not True:
            raise PermissionError('processing semantic authority expired before ACK')
    if not row or row[0]!={'receipt':receipt,'signature':seal}:
        raise PermissionError('processing receipt acknowledgment differs')
    return {**receipt,'signature':seal}


async def project_processing_event(ledger,lease,projection,*,secret,projector_id):
    # This concrete SDK type is supplied by the independently owned SDK lane;
    # missing integration fails closed, never falls back to legacy projection.
    from .sdk_projection import ProcessingSDKProjection
    binding=_compiler(ledger)
    if (not isinstance(lease,ProcessingProjectionLease) or not isinstance(projection,ProcessingSDKProjection)
            or not isinstance(projector_id,str) or not projector_id
            or lease.lease_role!=binding.expected_session_role
            or lease.lease_until<=datetime.now(timezone.utc)):
        raise PermissionError('trusted current processing projection and lease required')
    event=lease.event
    manifest=ArtifactManifest.model_validate_json(json.dumps(event.payload.get('manifest')))
    if (event.operation!='project' or event.payload!={'namespace':'oracle_processing_v1','manifest':manifest.model_dump(mode='json')}
            or manifest.kind!='processing_qualified_model_v1' or manifest.state!='ready'
            or (manifest.workspace_id,manifest.artifact_id,manifest.version)!=(event.workspace_id,event.assertion_id,event.revision)
            or not re.fullmatch(r'oracle_processing_v1_'+event.workspace_id.hex+'_'+event.assertion_id.hex+'_'+str(event.revision)+r'_[0-9a-f]{32}',projection.graph_name)):
        raise PermissionError('exact qualified processing event required')
    current,payload=ledger.read_with_manifest(event.workspace_id,event.assertion_id,event.revision)
    if current!=manifest or digest(payload)!=manifest.content_hash:raise PermissionError('processing event seal differs')
    count=(await projection.connection.query('MATCH (n) RETURN count(n)')).result_set[0][0]
    if count:await projection.load(ledger,event.workspace_id,event.assertion_id,event.revision)
    else:await projection.build(ledger,event.workspace_id,event.assertion_id,event.revision)
    await projection.verify(payload)
    # Both source and independent semantic authority are checked after network
    # work, before the short fenced SQL ACK. No implicit direct projection path.
    again,latest=ledger.read_with_manifest(event.workspace_id,event.assertion_id,event.revision)
    if again!=manifest or latest!=payload:raise PermissionError('processing input changed during projection')
    guard=ledger.processing_read_guard
    horizon=getattr(guard,'valid_until',None)
    if not callable(horizon):raise PermissionError('trusted processing semantic horizon required')
    receipt={'schema_version':1,'event_id':str(event.event_id),'workspace_id':str(event.workspace_id),
        'artifact_id':str(event.assertion_id),'version':event.revision,'content_hash':manifest.content_hash,
        'source_digest':manifest.source_digest,'permission_digest':manifest.permission_digest,
        'graph_name':projection.graph_name,'record_digest':digest({'records':projection.records(payload)}),
        'sdk_version':'1.4.0','projector_id':projector_id,'lease_role':lease.lease_role,
        'lease_token':str(lease.lease_token),'lease_attempt':event.attempts,'lease_until':lease.lease_until.isoformat()}
    seal=signature(secret,receipt)
    return acknowledge_processing_projection(ledger,lease,receipt,seal,secret=secret)
