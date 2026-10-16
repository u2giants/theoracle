"""Bounded existing-queue processing delivery; graph work never holds SQL locks."""
from dataclasses import dataclass
from datetime import datetime,timezone
import asyncio,json,re
from typing import Protocol,runtime_checkable
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from oracle_brain.outbox import ProjectionEvent
from .contracts import ArtifactManifest,ProcessingProjectionReceiptBodyV3,canonical_bytes,digest
from .processing_ledger import ProcessingCompilerLedger
from .projection_delivery import signature


@dataclass(frozen=True)
class ProcessingProjectionAuthorityWindowV3:
    """Current observation freshness and independently bounded operation lifetime.

    A typed record is not authority: protected hosting supplies the actual
    appointed adapter and validates every external and current SQL constraint.
    """
    current_until:datetime
    operation_horizon:datetime

    def __post_init__(self):
        for value in (self.current_until,self.operation_horizon):
            if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError('explicit aware projection window required')
        if self.current_until>self.operation_horizon:
            raise ValueError('current proof cannot exceed operation horizon')


@runtime_checkable
class ProcessingProjectionAuthorityProtocol(Protocol):
    """Pure contract; protected hosting enforces the actual appointed adapter."""
    def authorize_current(self) -> ProcessingProjectionAuthorityWindowV3: ...


class ProcessingProjectionIncomplete(PermissionError):
    """Unacknowledged generation; task completion is not remote-stop evidence."""
    def __init__(self,task,deadline,graph_name,reason):
        super().__init__('paid projection incomplete; generation quarantined')
        self.task,self.deadline,self.graph_name,self.reason=task,deadline,graph_name,reason


def _deadline(value):
    if (not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None
            or value<=datetime.now(timezone.utc)):
        raise PermissionError('current finite projection deadline required')
    return value


def _current_window(authority):
    window=authority.authorize_current()
    if type(window) is not ProcessingProjectionAuthorityWindowV3:
        raise PermissionError('explicit currentness and operation window required')
    _deadline(window.current_until);_deadline(window.operation_horizon)
    if window.current_until>window.operation_horizon:
        raise PermissionError('projection proof exceeds operation horizon')
    return window


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
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='2s'")
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


def _validate_paid_ack_context(lease,receipt,manifest,payload):
    """Bind the ONE actual final guarded read to this exact paid delivery."""
    from .sdk_projection import ProcessingSDKProjection
    from .paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
    if type(receipt) is not dict or type(receipt.get('schema_version')) is not int or receipt['schema_version']!=3:
        raise PermissionError('exact integer paid receipt schema required')
    body=ProcessingProjectionReceiptBodyV3.model_validate_json(canonical_bytes(receipt))
    event=lease.event
    expected=ArtifactManifest.model_validate_json(canonical_bytes(event.payload.get('manifest')))
    if (event.operation!='project' or event.payload!={'namespace':'oracle_processing_v1','manifest':expected.model_dump(mode='json')}
            or manifest!=expected or manifest.kind!='processing_qualified_model_v1' or manifest.state!='ready'
            or (manifest.workspace_id,manifest.artifact_id,manifest.version)!=(event.workspace_id,event.assertion_id,event.revision)
            or digest(payload)!=manifest.content_hash
            or manifest.source_digest!=digest({'refs':payload['source_refs']})
            or (body.event_id,body.workspace_id,body.artifact_id,body.version)!=(str(event.event_id),str(event.workspace_id),str(event.assertion_id),event.revision)
            or (body.content_hash,body.source_digest,body.permission_digest)!=(manifest.content_hash,manifest.source_digest,manifest.permission_digest)
            or (body.lease_role,body.lease_token,body.lease_attempt,body.lease_until)!=(lease.lease_role,str(lease.lease_token),event.attempts,lease.lease_until.isoformat())
            or not re.fullmatch(r'oracle_processing_v1_'+event.workspace_id.hex+'_'+event.assertion_id.hex+'_'+str(event.revision)+r'_[0-9a-f]{32}',body.graph_name)
            or body.record_digest!=digest({'records':ProcessingSDKProjection.records(payload)})
            or body.projection_digest!=ProcessingSDKProjection.processing_projection_digest(payload)
            or body.embedding_inventory_hash!=digest(processing_embedding_inventory_v3(payload).model_dump(mode='json'))):
        raise PermissionError('final current paid event/manifest/content/projection/lease differs')


def acknowledge_processing_projection(ledger,lease,receipt,seal,*,secret,caller_deadline=None,authority=None):
    """Trusted application verified graph/HMAC; SQL cannot observe that network."""
    import hmac
    binding=_compiler(ledger)
    if not isinstance(lease,ProcessingProjectionLease) or lease.lease_role!=binding.expected_session_role:
        raise PermissionError('actual current lease owner required')
    if not hmac.compare_digest(signature(secret,receipt),seal):raise PermissionError('processing receipt signature differs')
    event=lease.event
    manifest,payload=ledger.read_with_manifest(event.workspace_id,event.assertion_id,event.revision)
    if receipt.get('schema_version')==3:
        _validate_paid_ack_context(lease,receipt,manifest,payload)
    horizon=getattr(ledger.processing_read_guard,'valid_until',None)
    if not callable(horizon):raise PermissionError('trusted processing semantic horizon required')
    semantic_deadline=horizon(manifest,payload,ledger.principal,ledger.clock())
    if (not isinstance(semantic_deadline,datetime) or semantic_deadline.tzinfo is None
            or semantic_deadline.utcoffset() is None or semantic_deadline<=datetime.now(timezone.utc)):
        raise PermissionError('current trusted semantic horizon required')
    deadline=min(binding.expires_at,semantic_deadline,lease.lease_until)
    if receipt.get('schema_version')==3:
        if not isinstance(authority,ProcessingProjectionAuthorityProtocol) or caller_deadline is None:
            raise PermissionError('actual paid projector authority and original deadline required')
        # Outside SQL locks: the hosting adapter rechecks its original external
        # appointment, target, paid custody, current compiler/source and semantics.
        # The earlier semantic guard deadline is a freshness proof, not the
        # operation duration. The exact protected window rechecks those same
        # semantics/current grants LAST and supplies both distinct constraints.
        window=_current_window(authority)
        deadline=min(binding.expires_at,lease.lease_until,_deadline(caller_deadline),
            window.operation_horizon,window.current_until)
    elif caller_deadline is not None:
        deadline=min(deadline,_deadline(caller_deadline))
    event=lease.event
    with psycopg.connect(ledger.url) as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='2s'")
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
    from .sdk_projection import PaidProcessingSDKProjectionV3
    if isinstance(projection,PaidProcessingSDKProjectionV3):
        raise PermissionError('paid V3 projection requires explicit strict V3 delivery')
    return await _project_processing_event(ledger,lease,projection,secret=secret,projector_id=projector_id,authority=None)


async def project_paid_processing_event_v3(ledger,lease,projection,*,secret,projector_id,authority):
    from .sdk_projection import PaidProcessingSDKProjectionV3
    if type(projection) is not PaidProcessingSDKProjectionV3 or not isinstance(authority,ProcessingProjectionAuthorityProtocol):
        raise PermissionError('actual strict paid V3 projector and authority required')
    return await _project_processing_event(ledger,lease,projection,secret=secret,projector_id=projector_id,authority=authority)


async def _project_processing_event(ledger,lease,projection,*,secret,projector_id,authority):
    # This concrete SDK type is supplied by the independently owned SDK lane;
    # missing integration fails closed, never falls back to legacy projection.
    from .sdk_projection import ProcessingSDKProjection,PaidProcessingSDKProjectionV3
    paid=authority is not None
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
    async def graph_work():
        count=(await projection.connection.query('MATCH (n) RETURN count(n)')).result_set[0][0]
        if count:await projection.load(ledger,event.workspace_id,event.assertion_id,event.revision)
        else:await projection.build(ledger,event.workspace_id,event.assertion_id,event.revision)
        await projection.verify(payload)
        if paid:
            from .paid_sdk_embeddings_v3 import PaidSDKProjectionProofV3
            proof=await projection.paid_projection_proof(payload)
            if type(proof) is not PaidSDKProjectionProofV3:
                raise PermissionError('actual verified complete paid SDK proof required')
            return proof
    original_deadline=None;proof=None
    if paid:
        horizon=getattr(ledger.processing_read_guard,'valid_until',None)
        if not callable(horizon):raise PermissionError('current paid semantic horizon required')
        _deadline(horizon(manifest,payload,ledger.principal,ledger.clock()))
        # Fresh current proof is obtained LAST before graph work. Its short
        # observation age never renews or truncates the fixed operation lifetime.
        window=_current_window(authority)
        original_deadline=min(_deadline(binding.expires_at),_deadline(lease.lease_until),window.operation_horizon)
        # The actual graph task remains owned/observable after timeout. Cancel
        # is a request, not evidence that a remote write stopped. Hosting retains
        # UNKNOWN in its existing protected spool and refuses generation reuse.
        task=asyncio.create_task(graph_work(),name='oracle-paid-projection-'+projection.graph_name)
        try:
            done,_=await asyncio.wait({task},timeout=max(0,(original_deadline-datetime.now(timezone.utc)).total_seconds()))
        except asyncio.CancelledError as error:
            task.cancel()
            raise ProcessingProjectionIncomplete(task,original_deadline,projection.graph_name,'caller-cancelled') from error
        if not done:
            task.cancel()
            raise ProcessingProjectionIncomplete(task,original_deadline,projection.graph_name,'deadline')
        try:
            proof=task.result()
            _deadline(original_deadline) # never promote a late completed result
        except BaseException as error:
            raise ProcessingProjectionIncomplete(task,original_deadline,projection.graph_name,'graph-failed-or-late') from error
    else:await graph_work()
    # Both source and independent semantic authority are checked after network
    # work, before the short fenced SQL ACK. No implicit direct projection path.
    if not paid:
        again,latest=ledger.read_with_manifest(event.workspace_id,event.assertion_id,event.revision)
        if again!=manifest or latest!=payload:raise PermissionError('processing input changed during projection')
    # The paid ACK owns its ONE final actual guarded read and strict equality
    # checks. It does not accept a pregraph body as current authority. Keeping
    # another full read here only consumed the original lease twice.
    guard=ledger.processing_read_guard
    horizon=getattr(guard,'valid_until',None)
    if not callable(horizon):raise PermissionError('trusted processing semantic horizon required')
    receipt={'schema_version':3 if paid else 1,'event_id':str(event.event_id),'workspace_id':str(event.workspace_id),
        'artifact_id':str(event.assertion_id),'version':event.revision,'content_hash':manifest.content_hash,
        'source_digest':manifest.source_digest,'permission_digest':manifest.permission_digest,
        'graph_name':projection.graph_name,'record_digest':digest({'records':projection.records(payload)}),
        'projection_schema':'qualified-evidence-projection-v1','projection_digest':projection.processing_projection_digest(payload),
        'sdk_version':'1.4.0','projector_id':projector_id,'lease_role':lease.lease_role,
        'lease_token':str(lease.lease_token),'lease_attempt':event.attempts,'lease_until':lease.lease_until.isoformat()}
    if paid:receipt.update(proof.model_dump(mode='json'))
    seal=signature(secret,receipt)
    return acknowledge_processing_projection(ledger,lease,receipt,seal,secret=secret,
        caller_deadline=original_deadline,authority=authority)
