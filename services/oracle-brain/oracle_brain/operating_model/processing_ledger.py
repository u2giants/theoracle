"""Explicit trusted compiler boundary; new candidates never enter legacy serving.

Protected application configuration authenticates registry/custody/semantic
admission. SQL independently proves current source authority and provided-byte
integrity. Neither a typed body nor a file hash grants authority.
"""
import json
from dataclasses import dataclass
from datetime import datetime,timezone
from uuid import UUID
from typing import Protocol,runtime_checkable
import psycopg
from psycopg.types.json import Jsonb
from .authority_adapter import ProcessingArtifactResolver
from .contracts import ArtifactManifest,PROCESSING_ARTIFACT_KINDS,canonical_bytes,digest
from .ledger import Ledger


@runtime_checkable
class ProcessingExtractionGuardProtocol(Protocol):
    """Core contract only; protected hosting startup authenticates the issuer.

    Structural conformance alone confers no authority. The opt-in V3 factory
    requires its exact concrete, current SQL/custody-bound guard constructor.
    """
    def authorize_manifest(self,manifest:ArtifactManifest,principal:UUID,now:datetime)->datetime:...
    def __call__(self,manifest:ArtifactManifest,payload:dict,principal:UUID,now:datetime)->None:...
    def valid_until(self,manifest:ArtifactManifest,payload:dict,principal:UUID,now:datetime)->datetime:...


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
        if (processing_extraction_guard is not None
                and not isinstance(processing_extraction_guard,ProcessingExtractionGuardProtocol)):
            raise PermissionError('protected processing extraction guard protocol required')
        self.processing_extraction_guard=processing_extraction_guard
        self.processing_compile_guard=processing_compile_guard
        super().__init__(database_url,blobs,principal=principal,processing_sources=processing_sources,
            processing_read_guard=processing_read_guard,reviewed_inventories=reviewed_inventories,
            can_read=lambda *a:False,current_source=processing_sources.current_for_processing,clock=clock)

    def persist(self,*,workspace_id,artifact_id,version,kind,payload,refs,permission_digest,
                compiler_digest,dependencies=(),failed=False,before_commit=None):
        if 'consolidation_core' in payload:
            raise PermissionError('qualified temporal revisions require canonical consolidation owner')
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
            deadline=min(deadline,manifest_until,
                self._validate_processing_guard(self.processing_extraction_guard,manifest,payload,now))
        if kind in {'processing_qualified_model_v1','processing_summary_v1','processing_recommendation_v1'}:
            if self.processing_compile_guard is None:
                raise PermissionError('independent current processing qualification required')
            now=self.clock()
            until=self._validate_processing_guard(self.processing_compile_guard,manifest,payload,now)
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

    def _validate_processing_guard(self,guard,manifest,payload,now):
        """Legacy behavior; exact protected hosting overrides may fuse one call."""
        if guard(manifest,payload,self.principal,now) is not None:
            raise PermissionError('processing guard did not validate')
        horizon=getattr(guard,'valid_until',None)
        if not callable(horizon):raise PermissionError('trusted semantic horizon required')
        until=horizon(manifest,payload,self.principal,now)
        if (not isinstance(until,datetime) or until.tzinfo is None
                or until.utcoffset() is None or until<=now or until<=self.clock()):
            raise PermissionError('finite current processing horizon required')
        return until

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

    def _validate_processing_extraction_after_read(self,manifest,payload,now):
        if (manifest.kind in {'processing_extraction_v1','processing_failed_extraction_v1'}
                and self.processing_extraction_guard is not None):
            if self.processing_extraction_guard(manifest,payload,self.principal,now) is not None:
                raise PermissionError('processing extraction read guard did not validate')
            self._extraction_horizon(manifest,payload,now)

    def _read_processing_authorized(self,*args,**kwargs):
        manifest,payload=super()._read_processing_authorized(*args,**kwargs)
        self._validate_processing_extraction_after_read(manifest,payload,self.clock())
        return manifest,payload


@runtime_checkable
class ProcessingValidationHorizonProtocol(Protocol):
    """One complete validation result; protocol conformance grants no authority."""
    def validate_current(self,manifest:ArtifactManifest,payload:dict,principal:UUID,now:datetime)->datetime:...


@dataclass(frozen=True)
class ValidatedQualifiedParentV3:
    """Local completed-boundary result, never a deserializable capability."""
    manifest: ArtifactManifest
    canonical_body: bytes
    valid_until: datetime

    def __post_init__(self):
        if (type(self.manifest) is not ArtifactManifest
                or self.manifest.kind!='processing_qualified_model_v1' or self.manifest.state!='ready'
                or type(self.canonical_body) is not bytes
                or not isinstance(self.valid_until,datetime) or self.valid_until.tzinfo is None
                or self.valid_until.utcoffset() is None):
            raise PermissionError('exact validated qualified parent result required')
        import hashlib
        if hashlib.sha256(self.canonical_body).hexdigest()!=self.manifest.content_hash:
            raise PermissionError('validated qualified parent content differs')


class PurposeProcessingCompilerLedgerV3(ProcessingCompilerLedger):
    """Closed core implementation; protected hosting authenticates actual guards.

    No result is stored or reused across calls. Legacy compiler defaults remain
    separate. The concrete class itself is not a grant or semantic admission.
    """
    def _validate_processing_guard(self,guard,manifest,payload,now):
        if not isinstance(guard,ProcessingValidationHorizonProtocol):
            raise PermissionError('complete current validation protocol required')
        until=guard.validate_current(manifest,payload,self.principal,now)
        if (not isinstance(until,datetime) or until.tzinfo is None
                or until.utcoffset() is None or until<=now or until<=self.clock()):
            raise PermissionError('finite current full validation deadline required')
        return until

    def _validate_processing_read_guard(self,manifest,payload,now):
        guard=(self.processing_extraction_guard if manifest.kind in
            {'processing_extraction_v1','processing_failed_extraction_v1'} else self.processing_read_guard)
        return self._validate_processing_guard(guard,manifest,payload,now)

    def read_validated_qualified_parent_v3(self,workspace_id,artifact_id,version):
        if type(self) is not PurposeProcessingCompilerLedgerV3:
            raise PermissionError('exact full compiler parent boundary required')
        # Wrong-kind targets are rejected before any private blob can open.
        expected,_=self.processing_sources.artifact_metadata(workspace_id,artifact_id,version)
        if expected.kind!='processing_qualified_model_v1' or expected.state!='ready':
            raise PermissionError('exact qualified model parent required')
        manifest,payload,until=self._read_processing_boundary(workspace_id,artifact_id,version)
        if (manifest!=expected or not isinstance(until,datetime) or until.tzinfo is None
                or until.utcoffset() is None or until<=self.clock()):
            raise PermissionError('parent authority expired after metadata recheck')
        return ValidatedQualifiedParentV3(manifest,canonical_bytes(payload),until)

    def _validate_processing_extraction_after_read(self,manifest,payload,now):
        # The full body hook already validated this same boundary exactly once,
        # before the independent current metadata reread. Never cache its result.
        return None


def require_explicit_compiler_ledger_v3(ledger):
    """Closed implementation boundary only, never permission or paid evidence."""
    if type(ledger) not in (ProcessingCompilerLedger,PurposeProcessingCompilerLedgerV3):
        raise PermissionError('actual explicit compiler ledger required')
