"""Explicit trusted compiler boundary; new candidates never enter legacy serving.

Protected application configuration authenticates registry/custody/semantic
admission. SQL independently proves current source authority and provided-byte
integrity. Neither a typed body nor a file hash grants authority.
"""
import json
from datetime import datetime,timezone
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from .authority_adapter import ProcessingArtifactResolver
from .contracts import ArtifactManifest,PROCESSING_ARTIFACT_KINDS,canonical_bytes,digest
from .ledger import Ledger


class ProcessingCompilerLedger(Ledger):
    def __init__(self,database_url,blobs,*,principal,processing_sources,
                 processing_compile_guard=None,processing_read_guard=None,processing_extraction_guard=None,
                 reviewed_inventories=None,clock=None):
        if (not isinstance(processing_sources,ProcessingArtifactResolver)
                or database_url!=processing_sources.url
                or processing_sources.binding.profile!='candidate-compiler'
                or processing_sources.binding.principal!=principal):
            raise PermissionError('fixed current processing compiler required')
        if processing_compile_guard is not None and not callable(processing_compile_guard):
            raise PermissionError('trusted processing compile guard required')
        if processing_extraction_guard is not None:
            # Imported only for the opt-in path; the legacy/source V1 path keeps
            # its existing imports and behavior. A duck type is not authority.
            from .purpose_journey import ProcessingCompilerExtractionGuardV2
            if type(processing_extraction_guard) is not ProcessingCompilerExtractionGuardV2:
                raise PermissionError('exact protected processing extraction guard required')
        self.processing_extraction_guard=processing_extraction_guard
        self.processing_compile_guard=processing_compile_guard
        super().__init__(database_url,blobs,principal=principal,processing_sources=processing_sources,
            processing_read_guard=processing_read_guard,reviewed_inventories=reviewed_inventories,
            can_read=lambda *a:False,current_source=processing_sources.current_for_processing,clock=clock)

    def persist(self,*,workspace_id,artifact_id,version,kind,payload,refs,permission_digest,
                compiler_digest,dependencies=(),failed=False,before_commit=None):
        if (kind not in PROCESSING_ARTIFACT_KINDS or not isinstance(workspace_id,UUID)
                or not isinstance(artifact_id,UUID) or type(version) is not int or version<1
                or type(failed) is not bool or failed!=(kind in {'processing_failed_extraction_v1','processing_failed_assembly_v1'})
                or compiler_digest!=self.processing_sources.binding.runtime_hash
                or not refs or len(set(refs))!=len(refs)
                or len({r.source_id for r in refs})!=len(refs)):
            raise PermissionError('canonical reported processing artifact required')
        receipts=self.authorize_refs(refs,workspace_id)
        self.validate_reported_payload(payload,refs,workspace_id,receipts)
        if any(f.get('status') not in {'unresolved','needs_evidence'} for f in payload.get('findings',())):
            raise PermissionError('compiler cannot confer an authorized finding review')
        deps=tuple(sorted(set(tuple(d) for d in dependencies)|{('source',str(r.source_id),str(r.revision)) for r in refs}))
        if any(len(d)!=3 or d[0] not in {'source','artifact'} or any(not isinstance(v,str) or not v for v in d) for d in deps):
            raise PermissionError('explicit source/artifact processing lineage required')
        payload_bytes=canonical_bytes(payload)
        seal=digest(payload);key=f'operating-model/{workspace_id}/{seal}.json'
        ref_bytes=canonical_bytes({'refs':[r.model_dump(mode='json') for r in refs]})
        dep_bytes=canonical_bytes({'dependencies':deps})
        import hashlib
        source_digest=hashlib.sha256(ref_bytes).hexdigest()
        manifest=ArtifactManifest(workspace_id=workspace_id,artifact_id=artifact_id,version=version,kind=kind,
            input_digest=source_digest,source_digest=source_digest,permission_digest=permission_digest,
            compiler_digest=compiler_digest,dependency_digest=hashlib.sha256(dep_bytes).hexdigest(),
            content_hash=seal,private_object_key=key,state='failed' if failed else 'ready')
        deadline=self.processing_sources.binding.expires_at
        if (kind in {'processing_extraction_v1','processing_failed_extraction_v1'}
                and self.processing_extraction_guard is not None):
            now=self.clock()
            manifest_until=self._authorize_processing_blob(manifest)
            if self.processing_extraction_guard(manifest,payload,self.principal,now) is not None:
                raise PermissionError('processing extraction guard did not validate')
            deadline=min(deadline,manifest_until,self._extraction_horizon(manifest,payload,now))
        if kind in {'processing_qualified_model_v1','processing_summary_v1'}:
            if self.processing_compile_guard is None:
                raise PermissionError('independent current processing qualification required')
            now=self.clock()
            if self.processing_compile_guard(manifest,payload,self.principal,now) is not None:
                raise PermissionError('processing compile guard did not validate')
            horizon=getattr(self.processing_compile_guard,'valid_until',None)
            if not callable(horizon):raise PermissionError('trusted semantic horizon required')
            until=horizon(manifest,payload,self.principal,now)
            if (not isinstance(until,datetime) or until.tzinfo is None or until.utcoffset() is None or until<=now):
                raise PermissionError('finite current semantic horizon required')
            deadline=min(deadline,until)
        # Object storage may involve a network. It occurs BEFORE any SQL hold.
        if self.blobs.put(workspace_id,payload)!=(key,seal):
            raise ValueError('private processing object identity differs')
        with psycopg.connect(self.url) as conn:
            self.processing_sources._check(conn)
            actual=conn.execute('SELECT session_user').fetchone()[0]
            if actual!=self.processing_sources.binding.expected_session_role:
                raise PermissionError('compiler database connection identity differs')
            row=conn.execute('SELECT oracle2.commit_processing_candidate(%s,%s,%s,%s,%s,%s,%s,%s)',
                (Jsonb(manifest.model_dump(mode='json')),payload_bytes,ref_bytes,dep_bytes,
                 Jsonb([r.model_dump(mode='json') for r in receipts.values()]),
                 self.processing_sources.binding.runtime_hash,self.processing_sources.binding.source_registry_hash,
                 deadline)).fetchone()
            if not row or row[0]!=manifest.model_dump(mode='json'):
                raise PermissionError('atomic processing persistence differs')
            if before_commit:before_commit()
            # Repeat SQL current-authority/lineage checks after any local callback.
            current,current_refs=self.processing_sources.artifact_metadata(workspace_id,artifact_id,version,connection=conn)
            if current!=manifest or set(current_refs)!=set(refs):raise PermissionError('processing persistence changed')
            self.processing_sources._check(conn)
            if conn.execute('SELECT clock_timestamp()<%s',(deadline,)).fetchone()[0] is not True:
                raise PermissionError('processing/semantic authority expired before commit')
        return manifest

    def _extraction_horizon(self,manifest,payload,now):
        until=self.processing_extraction_guard.valid_until(manifest,payload,self.principal,now)
        if (not isinstance(until,datetime) or until.tzinfo is None
                or until.utcoffset() is None or until<=now or until<=self.clock()):
            raise PermissionError('finite current extraction horizon required')
        return until

    def _authorize_processing_blob(self,manifest):
        if (manifest.kind in {'processing_extraction_v1','processing_failed_extraction_v1'}
                and self.processing_extraction_guard is not None):
            now=self.clock()
            until=self.processing_extraction_guard.authorize_manifest(manifest,self.principal,now)
            if (not isinstance(until,datetime) or until.tzinfo is None
                    or until.utcoffset() is None or until<=now or until<=self.clock()):
                raise PermissionError('finite current extraction manifest horizon required')
            return until

    def _read_processing_authorized(self,*args,**kwargs):
        manifest,payload=super()._read_processing_authorized(*args,**kwargs)
        if (manifest.kind in {'processing_extraction_v1','processing_failed_extraction_v1'}
                and self.processing_extraction_guard is not None):
            now=self.clock()
            if self.processing_extraction_guard(manifest,payload,self.principal,now) is not None:
                raise PermissionError('processing extraction read guard did not validate')
            self._extraction_horizon(manifest,payload,now)
        return manifest,payload
