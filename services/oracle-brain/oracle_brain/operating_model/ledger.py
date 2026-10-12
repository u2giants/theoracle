"""Postgres artifact ledger. Projection is derived; sealed blobs and current sources govern reads."""
import json
from uuid import UUID, uuid4
from collections.abc import Callable
import psycopg
from psycopg.types.json import Jsonb
from .contracts import ArtifactManifest, digest
from .source_receipts import SourceReceipt, SourceRef, resolve_receipt
from .observations import Observation, create_observation
from .findings import Finding, validate_finding
from .workflows.process_model import WorkflowModel
from .workflows.process_validate import validate_workflow
from .model import BusinessOperatingModel
from .assembly import validate_assembly
from .process_analysis.event_contracts import LogReceipt
from .ingest.operational_export import Mapping,parse_export
from oracle_brain.knowledge.authority import _lock,_has_authority_conn

class Ledger:
    def __init__(self, database_url: str, blobs, *, principal: UUID,
                 can_read: Callable[[UUID, UUID, UUID], bool],
                 current_source: Callable[[UUID, UUID], SourceReceipt],
                 reviewed_inventories: dict[str, dict] | None = None):
        self.url, self.blobs, self.principal = database_url, blobs, principal
        self.can_read, self.current_source = can_read, current_source
        self.reviewed_inventories = reviewed_inventories or {}

    def authorize_refs(self, refs: tuple[SourceRef, ...], workspace_id: UUID) -> dict[str, SourceReceipt]:
        receipts = {}
        for ref in refs:
            if ref.workspace_id != workspace_id or not self.can_read(workspace_id, self.principal, ref.source_id):
                raise PermissionError('source access denied')
            receipts[str(ref.source_id)] = resolve_receipt(ref, f'r{ref.revision}', self.current_source)
        if not refs:
            raise PermissionError('artifact must have an authoritative source manifest')
        return receipts

    def persist(self, *, workspace_id: UUID, artifact_id: UUID, version: int, kind: str,
                payload: dict, refs: tuple[SourceRef, ...], permission_digest: str,
                compiler_digest: str, dependencies: tuple[tuple[str,str,str], ...] = (),
                failed: bool = False, before_commit: Callable[[], None] | None = None) -> ArtifactManifest:
        receipts = self.authorize_refs(refs, workspace_id)
        if payload.get('source_refs') != [r.model_dump(mode='json') for r in refs]:
            raise ValueError('payload source manifest mismatch')
        # Validate persisted typed records, never trusting a graph description.
        validated_observations={}
        for raw in payload.get('observations', []):
            observation = Observation.model_validate_json(json.dumps(raw))
            expected = create_observation(receipts[str(observation.ref.source_id)], observation.occurrence_key,
                                          observation.kind, observation.scope, observation.value, observation.evidence)
            validated_observations[observation.observation_id]=observation
            if expected != observation:
                raise ValueError('observation identity does not match its immutable support')
        for raw in payload.get('findings', []):
            validate_finding(Finding.model_validate_json(json.dumps(raw)), receipts,
                             inventories=self.reviewed_inventories)
        for raw in payload.get('workflows',[]):
            model=WorkflowModel.model_validate_json(json.dumps(raw))
            if model.workspace_id!=workspace_id or not set(model.source_refs)<=set(refs):raise ValueError('workflow source outside artifact manifest')
            if model.status!='reported':raise PermissionError('model output cannot confer confirmed policy')
            validate_workflow(model,validated_observations)
        for raw in payload.get('operating_models',[]):
            model=BusinessOperatingModel.model_validate_json(json.dumps(raw))
            if model.workspace_id!=workspace_id or not set(model.source_refs)<=set(refs):raise ValueError('company source outside artifact manifest')
            validate_assembly(model,validated_observations)
        event_log=None
        if kind=='event_import':
            event_log=LogReceipt.model_validate_json(json.dumps(payload['event_import']))
            event_mapping=Mapping.model_validate_json(json.dumps(payload['mapping']))
            if event_log.workspace_id!=workspace_id or event_log.import_id!=artifact_id or event_log.mapping_hash!=digest(event_mapping.model_dump(mode='json')):raise ValueError('event artifact identity mismatch')
            import base64,hashlib
            raw=base64.b64decode(payload['raw_export_base64'],validate=True)
            if hashlib.sha256(raw).hexdigest()!=event_log.input_hash:raise ValueError('event original hash mismatch')
            derived,quarantined=parse_export(raw,payload['format'],workspace_id,event_mapping,event_log.window_start,event_log.window_end)
            if derived!=event_log or list(quarantined)!=payload['quarantine']:raise ValueError('event records do not reproduce exact raw export')
        key, seal = self.blobs.put(workspace_id, payload)
        source_digest = digest({'refs':[r.model_dump(mode='json') for r in refs]})
        manifest = ArtifactManifest(workspace_id=workspace_id,artifact_id=artifact_id,version=version,kind=kind,
          input_digest=source_digest,source_digest=source_digest,permission_digest=permission_digest,
          compiler_digest=compiler_digest,dependency_digest=digest({'dependencies':sorted(dependencies)}),
          content_hash=seal,private_object_key=key,state='failed' if failed else 'ready')
        with psycopg.connect(self.url) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (f'operating-model:{workspace_id}:{artifact_id}',))
            previous = conn.execute('SELECT manifest FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s AND version=%s', (workspace_id,artifact_id,version)).fetchone()
            if previous:
                if previous[0] != manifest.model_dump(mode='json'):
                    raise ValueError('same artifact version has different content')
                return manifest
            # Recheck permissions and source revision inside the write boundary.
            _lock(conn,workspace_id)
            if event_log and not _has_authority_conn(conn,workspace_id,self.principal,'event-import:'+event_mapping.scope):raise PermissionError('event import authority changed')
            self.authorize_refs(refs, workspace_id)
            for receipt in receipts.values():
                raw = receipt.model_dump(mode='json')
                prior = conn.execute('SELECT receipt FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s AND source_id=%s AND revision=%s', (workspace_id,receipt.ref.source_id,receipt.ref.revision)).fetchone()
                if prior and prior[0] != raw:
                    # Aliases do not change admitted source identity or text.
                    if {k:v for k,v in prior[0].items() if k!='aliases'} != {k:v for k,v in raw.items() if k!='aliases'}:
                        raise ValueError('source revision tampering')
                conn.execute('INSERT INTO oracle2.operating_model_source_receipts(workspace_id,source_id,revision,original_hash,reading_hash,parser_id,receipt) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (workspace_id,receipt.ref.source_id,receipt.ref.revision,receipt.ref.original_sha256,receipt.ref.reading_sha256,receipt.ref.parser_id,Jsonb(raw)))
            for raw in payload.get('observations',[]):
                prior = conn.execute('SELECT payload FROM oracle2.document_observations WHERE workspace_id=%s AND observation_id=%s',(workspace_id,raw['observation_id'])).fetchone()
                if prior and prior[0]!=raw:
                    raise ValueError('same observation has different content')
                conn.execute('INSERT INTO oracle2.document_observations VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(workspace_id,raw['observation_id'],UUID(raw['ref']['source_id']),raw['ref']['revision'],Jsonb(raw)))
            conn.execute('INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(workspace_id,artifact_id,version,kind,manifest.input_digest,manifest.source_digest,permission_digest,compiler_digest,manifest.dependency_digest,seal,key,manifest.state,Jsonb(manifest.model_dump(mode='json'))))
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'operating-lineage:{workspace_id}',))
            for upstream_kind,upstream_id,upstream_revision in dependencies:
                if upstream_kind not in {'source','permission','identity','artifact','event_window','compiler','dependency'} or not upstream_id or not upstream_revision:
                    raise ValueError('explicit upstream dependency required')
                if upstream_kind=='artifact':
                    upstream_uuid=UUID(upstream_id)
                    upstream_version=int(upstream_revision)
                    if upstream_uuid==artifact_id and upstream_version==version:raise ValueError('artifact lineage cycle')
                    prior=conn.execute('SELECT 1 FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s AND version=%s AND state=%s',(workspace_id,upstream_uuid,upstream_version,'ready')).fetchone()
                    if not prior:raise ValueError('upstream artifact unavailable')
                    self.read(workspace_id,upstream_uuid,upstream_version)
                    cycle=conn.execute("""WITH RECURSIVE ancestors(artifact_id,version) AS (
                      SELECT %s::uuid,%s::integer UNION
                      SELECT d.upstream_id::uuid,d.upstream_revision::integer FROM oracle2.artifact_dependencies d JOIN ancestors a
                      ON d.artifact_id=a.artifact_id AND d.version=a.version
                      WHERE d.workspace_id=%s AND d.upstream_kind='artifact'
                    ) SELECT 1 FROM ancestors WHERE artifact_id=%s AND version=%s LIMIT 1""",(upstream_uuid,upstream_version,workspace_id,artifact_id,version)).fetchone()
                    if cycle:raise ValueError('artifact lineage cycle')
            for upstream_kind,upstream_id,upstream_revision in dependencies + tuple(('source',str(r.source_id),str(r.revision)) for r in refs):
                conn.execute('INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(workspace_id,artifact_id,version,upstream_kind,upstream_id,upstream_revision))
            if event_log:
                conn.execute('INSERT INTO oracle2.operational_imports(workspace_id,import_id,revision,mapping_hash,window_hash,quality,accepted_count,quarantined_count,content_hash,artifact_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(workspace_id,event_log.import_id,version,event_log.mapping_hash,digest({'start':event_log.window_start.isoformat(),'end':event_log.window_end.isoformat()}),Jsonb({'notes':list(event_log.quality_notes),'censoring':event_log.case_censoring}),len(event_log.events),len(event_log.quarantined_rows),seal,artifact_id))
            if not failed:
                conn.execute('INSERT INTO oracle2.outbox(event_id,workspace_id,assertion_id,revision,operation,payload) VALUES(%s,%s,%s,%s,%s,%s)',(uuid4(),workspace_id,artifact_id,version,'project',Jsonb({'namespace':'oracle_operating_model_v1','manifest':manifest.model_dump(mode='json')})))
            if before_commit:
                before_commit()
        return manifest

    def read(self, workspace_id: UUID, artifact_id: UUID, version: int, *, include_failed: bool=False) -> dict:
        with psycopg.connect(self.url) as conn:
            row = conn.execute('SELECT manifest FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s AND version=%s',(workspace_id,artifact_id,version)).fetchone()
            denied = conn.execute('SELECT 1 FROM oracle2.artifact_invalidations WHERE workspace_id=%s AND artifact_id=%s AND version=%s LIMIT 1',(workspace_id,artifact_id,version)).fetchone()
        if not row or denied:
            raise PermissionError('artifact unavailable or invalidated')
        manifest = ArtifactManifest.model_validate_json(json.dumps(row[0]))
        if manifest.state!='ready' and not include_failed:
            raise PermissionError('failed extraction cannot serve')
        payload = json.loads(self.blobs.read(manifest.private_object_key,manifest.content_hash))
        refs = tuple(SourceRef.model_validate_json(json.dumps(r)) for r in payload['source_refs'])
        self.authorize_refs(refs,workspace_id)
        if digest({'refs':[r.model_dump(mode='json') for r in refs]}) != manifest.source_digest:
            raise ValueError('source manifest seal mismatch')
        return payload

    def append_review(self, *, workspace_id: UUID, artifact_id: UUID, version: int,
                      finding_id: str, event_id: UUID, action: str, scope: str,
                      note: str, authority: Callable) -> dict:
        if action not in {'annotate','resolve','supersede','withdraw'} or not scope or not note:
            raise ValueError('invalid scoped review')
        payload = self.read(workspace_id,artifact_id,version)
        finding = next((Finding.model_validate_json(json.dumps(f)) for f in payload.get('findings',[]) if f['finding_id']==finding_id),None)
        if finding is None or finding.scope != scope:
            raise PermissionError('finding not in exact review scope')
        if finding.origin=='legacy_unverified' and action!='annotate':
            raise ValueError('unverified legacy finding needs re-anchoring, not resolution')
        event = {'artifact_id':str(artifact_id),'version':version,'finding_hash':digest(finding.model_dump(mode='json')),'note':note}
        with psycopg.connect(self.url) as conn:
            authority(conn,workspace_id,self.principal,scope)
            self.authorize_refs(finding.source_refs,workspace_id)
            prior=conn.execute('SELECT finding_id,actor_id,scope,action,payload FROM oracle2.finding_events WHERE workspace_id=%s AND event_id=%s',(workspace_id,event_id)).fetchone()
            expected=(finding_id,self.principal,scope,action,event)
            if prior and prior!=expected:
                raise ValueError('same review event has different content')
            conn.execute('INSERT INTO oracle2.finding_events(workspace_id,finding_id,event_id,actor_id,scope,action,payload) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(workspace_id,finding_id,event_id,self.principal,scope,action,Jsonb(event)))
        return event
