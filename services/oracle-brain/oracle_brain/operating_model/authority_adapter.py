"""Retained authority primitives, with exact source visibility rather than workspace-only access."""
import hashlib
import json
from uuid import UUID
import psycopg
from oracle_brain.knowledge.authority import _lock, _has_authority_conn
from oracle_brain.ingest.originals import ReadingProvenance
from .source_receipts import SourceRef, SourceReceipt


def require_review(connection, workspace_id: UUID, actor_id: UUID, scope: str):
    _lock(connection, workspace_id)
    if not _has_authority_conn(connection, workspace_id, actor_id, 'finding-review:' + scope):
        raise PermissionError('current owner-rooted scoped finding review authority required')

class PostgresSources:
    def __init__(self, url: str, *, source_binding=None, synthetic: bool=False):
        from oracle_brain.operating_model.source_binding import SourceRoleBinding
        if source_binding is not None and not isinstance(source_binding,SourceRoleBinding):
            raise PermissionError('fixed source-role binding required')
        self.url,self.source_binding,self.synthetic = url,source_binding,synthetic
        with psycopg.connect(url) as conn:self._check(conn)

    def _check(self, conn):
        if self.source_binding is not None:
            self.source_binding.check(conn)
            return
        params=conn.info.get_parameters()
        if self.synthetic is not True or params.get('host') not in {'127.0.0.1','localhost','::1'} or not (params.get('dbname','').startswith('oracle_operating_model_test') or params.get('dbname') in {'oracle2','hosting_permissions_test'}):
            raise PermissionError('externally issued source-role binding required')
        roles=conn.execute("""WITH RECURSIVE memberships(oid) AS (
          SELECT oid FROM pg_roles WHERE rolname=SESSION_USER
          UNION SELECT m.roleid FROM pg_auth_members m JOIN memberships x ON m.member=x.oid)
          SELECT rolname FROM pg_roles WHERE oid IN (SELECT oid FROM memberships)
          AND rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor')""").fetchall()
        if roles:raise PermissionError('registered source role requires external binding')

    def can_read(self, workspace_id: UUID, principal: UUID, source_id: UUID) -> bool:
        with psycopg.connect(self.url) as conn:
            self._check(conn)
            allowed=_has_authority_conn(conn,workspace_id,principal,'source-read:' + str(source_id))
            self._check(conn)
            return allowed

    def current(self, workspace_id: UUID, source_id: UUID) -> SourceReceipt:
        with psycopg.connect(self.url) as conn:
            self._check(conn)
            rows = conn.execute('''SELECT s.revision,s.status,d.status,b.text,m.text
              FROM oracle2.sources s JOIN oracle2.drafts d
               ON d.source_id=s.source_id AND d.workspace_id=s.workspace_id
              JOIN oracle2.source_blocks b ON b.source_id=s.source_id AND b.workspace_id=s.workspace_id AND b.kind='original'
              LEFT JOIN oracle2.source_blocks m ON m.source_id=s.source_id AND m.workspace_id=s.workspace_id AND m.kind='original-metadata'
              WHERE s.workspace_id=%s AND s.source_id=%s''',(workspace_id,source_id)).fetchall()
            self._check(conn)
        if len(rows)!=1 or rows[0][1] not in {'draft','confirmed'} or rows[0][2]!='confirmed':
            raise PermissionError('current qualified source unavailable or withdrawn')
        revision, _, _, reading, metadata = rows[0]
        if not metadata:
            raise PermissionError('source lacks immutable original-reading provenance')
        provenance = ReadingProvenance.model_validate_json(metadata)
        reading_hash = hashlib.sha256(reading.encode()).hexdigest()
        if reading_hash != provenance.content_hash:
            raise ValueError('current original reading seal mismatch')
        ref = SourceRef(workspace_id=workspace_id,source_id=source_id,revision=revision,
                        original_sha256=provenance.original_hash,reading_sha256=reading_hash,
                        parser_id=provenance.parser_identity)
        return SourceReceipt(ref=ref,reading=reading,display_revision=f'r{revision}')


from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import re


@dataclass(frozen=True)
class ProcessingSourceBinding:
    """Identity pins from trusted immutable configuration, never request authority."""
    runtime_hash: str
    source_registry_hash: str
    expected_owner_role: str
    expected_session_role: str
    principal: UUID
    profile: str
    expires_at: datetime
    synthetic: bool = False

    def __post_init__(self):
        if (any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v)
                for v in (self.runtime_hash, self.source_registry_hash))
            or any(not isinstance(v, str) or not re.fullmatch('[a-z_][a-z0-9_]{0,62}', v)
                   for v in (self.expected_owner_role, self.expected_session_role))
            or not isinstance(self.principal, UUID)
            or not isinstance(self.profile,str)
            or self.profile not in {'source-reader','candidate-compiler','documentary-executor','gateway-metadata'}
            or not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None or type(self.synthetic) is not bool):
            raise PermissionError('complete immutable processing source pins required')


class ProcessingSourceResolver:
    """Explicit opt-in: raw qualification and metadata validity remain distinct.

    Caller must supply issuer-qualified immutable pins. Construction issues no
    appointments, role admissions or processing jobs and confers no authority.
    """
    _groups = ('oracle2_source_reader','oracle2_candidate_compiler',
               'oracle2_documentary_executor','oracle2_gateway_metadata')
    _signatures = {
        'oracle2.hosting_source_visible(uuid,uuid)': frozenset({
            'oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor'}),
        'oracle2._processing_source(uuid,uuid,uuid,text,text,boolean)': frozenset(),
        'oracle2.hosting_processing_source_receipt(uuid,uuid,uuid,text,text)':
            frozenset({'oracle2_source_reader','oracle2_candidate_compiler'}),
        'oracle2.hosting_current_source_identity(uuid,uuid,uuid,text,text)': frozenset(_groups),
    }

    def __init__(self, url: str, *, binding: ProcessingSourceBinding):
        if not isinstance(binding, ProcessingSourceBinding):
            raise PermissionError('fixed processing binding required')
        self.url, self.binding = url, binding
        with self._connection() as conn:
            self._check(conn)

    @property
    def metadata_only(self):
        return self.binding.profile in {'documentary-executor','gateway-metadata'}

    @contextmanager
    def _connection(self, connection=None):
        if connection is not None:
            wanted = psycopg.conninfo.conninfo_to_dict(self.url)
            actual = connection.info.get_parameters()
            try:expected_port=int(wanted.get('port') or 5432)
            except (TypeError,ValueError):raise PermissionError('processing connection port invalid') from None
            if (connection.info.port!=expected_port
                    or any(str(wanted.get(k, '')) != str(actual.get(k, '')) for k in ('host','dbname','user'))):
                raise PermissionError('processing connection target differs')
            yield connection
        else:
            with psycopg.connect(self.url, connect_timeout=5) as conn:
                yield conn

    def _check(self, conn):
        b = self.binding
        if datetime.now(timezone.utc) >= b.expires_at:
            raise PermissionError('processing caller admission expired')
        params = conn.info.get_parameters()
        if not conn.pgconn.ssl_in_use or params.get('sslmode') != 'verify-full':
            if (not b.synthetic or params.get('host') not in {'localhost','127.0.0.1','::1'}
                or not params.get('dbname','').startswith('oracle_operating_model_test')):
                raise PermissionError('processing ledger authenticated TLS required')
        row = conn.execute("""SELECT session_user,current_user,rolsuper,rolbypassrls,
            rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=session_user""").fetchone()
        group = 'oracle2_' + b.profile.replace('-','_')
        if (not row or row[0] != b.expected_session_role or row[1] not in {row[0],group}
                or any(row[2:])):
            raise PermissionError('processing session role differs')
        groups = conn.execute("""SELECT rolname::text FROM pg_roles WHERE rolname=ANY(%s)
            AND pg_has_role(session_user,oid,'MEMBER') ORDER BY rolname""", (list(self._groups),)).fetchall()
        if groups != [(group,)]:
            raise PermissionError('exclusive fixed processing role required')
        owner = conn.execute("""SELECT r.rolname,pg_has_role(session_user,r.oid,'MEMBER')
            FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'""").fetchone()
        if owner != (b.expected_owner_role,False):
            raise PermissionError('trusted schema owner differs or is reachable')
        reachable=conn.execute("""SELECT rolname::text FROM pg_roles WHERE
            pg_has_role(session_user,oid,'MEMBER') OR pg_has_role(session_user,oid,'SET')
            OR pg_has_role(session_user,oid,'USAGE')""").fetchall()
        if {r[0] for r in reachable}!={b.expected_session_role,group}:
            raise PermissionError('exact processing membership differs')
        flags=conn.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=%s',(group,)).fetchone()
        if flags is None or any(flags):
            raise PermissionError('fixed processing group flags differ')
        entry=conn.execute("SELECT rolcanlogin,rolinherit,pg_has_role(session_user,%s,'USAGE'),pg_has_role(session_user,%s,'SET') FROM pg_roles WHERE rolname=session_user",(group,group)).fetchone()
        if (not entry or not entry[0] or (row[1]==row[0] and not entry[2])
                or (row[1]==group and not entry[3])):
            raise PermissionError('actual processing inherit/SET entry differs')
        for signature, allowed in self._signatures.items():
            function = conn.execute("""SELECT r.rolname,p.prosecdef,p.proconfig
                FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=to_regprocedure(%s)""",
                (signature,)).fetchone()
            if function != (b.expected_owner_role,True,['search_path=pg_catalog, oracle2']):
                raise PermissionError('fixed processing function owner/config differs')
            if allowed is not None:
                grants = conn.execute("""SELECT coalesce(r.rolname,'PUBLIC'),a.is_grantable
                    FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                    LEFT JOIN pg_roles r ON r.oid=a.grantee
                    WHERE p.oid=to_regprocedure(%s) AND a.privilege_type='EXECUTE' AND a.grantee<>p.proowner""",
                    (signature,)).fetchall()
                if frozenset(name for name,_ in grants) != allowed or any(grantable for _,grantable in grants):
                    raise PermissionError('fixed processing function ACL differs')
        if b.profile != 'gateway-metadata':
            from .source_binding import SourceRoleBinding
            SourceRoleBinding(b.runtime_hash,b.source_registry_hash,synthetic=b.synthetic).check(conn)

    def _args(self, workspace_id, source_id):
        if not isinstance(workspace_id,UUID) or not isinstance(source_id,UUID):
            raise PermissionError('exact processing source identity required')
        b=self.binding
        return workspace_id,source_id,b.principal,b.runtime_hash,b.source_registry_hash

    def identity(self, workspace_id: UUID, source_id: UUID, *, connection=None) -> SourceRef:
        with self._connection(connection) as conn:
            self._check(conn)
            rows=conn.execute('SELECT * FROM oracle2.hosting_current_source_identity(%s,%s,%s,%s,%s)',
                              self._args(workspace_id,source_id)).fetchall()
            self._check(conn)
        if len(rows)!=1:
            raise PermissionError('unique current processing source identity required')
        revision,original,reading,parser,valid_until,checked_at=rows[0]
        return SourceRef(workspace_id=workspace_id,source_id=source_id,revision=revision,
                         original_sha256=original,reading_sha256=reading,parser_id=parser)

    def current_for_processing(self, workspace_id: UUID, source_id: UUID, *, connection=None) -> SourceReceipt:
        if self.metadata_only:
            raise PermissionError('metadata processing profile cannot read originals')
        with self._connection(connection) as conn:
            self._check(conn)
            rows=conn.execute('SELECT * FROM oracle2.hosting_processing_source_receipt(%s,%s,%s,%s,%s)',
                              self._args(workspace_id,source_id)).fetchall()
            self._check(conn)
        if len(rows)!=1:
            raise PermissionError('unique qualified processing original required')
        revision,original,reading_hash,parser,reading,metadata,valid_until,checked_at=rows[0]
        provenance=ReadingProvenance.model_validate_json(metadata)
        if (provenance.original_hash,provenance.content_hash,provenance.parser_identity)!=(original,reading_hash,parser):
            raise PermissionError('processing provenance differs')
        ref=SourceRef(workspace_id=workspace_id,source_id=source_id,revision=revision,
                      original_sha256=original,reading_sha256=reading_hash,parser_id=parser)
        return SourceReceipt(ref=ref,reading=reading,display_revision=f'r{revision}')

    def authorize_refs(self, refs, workspace_id, principal, *, connection=None):
        if principal != self.binding.principal or not refs:
            raise PermissionError('exact admitted processing actor and sources required')
        receipts={}
        for ref in refs:
            if ref.workspace_id != workspace_id:
                raise PermissionError('processing source workspace differs')
            receipt=(self.identity(workspace_id,ref.source_id,connection=connection) if self.metadata_only
                     else self.current_for_processing(workspace_id,ref.source_id,connection=connection))
            actual=receipt if isinstance(receipt,SourceRef) else receipt.ref
            if actual!=ref:
                raise PermissionError('processing source revision or seal changed')
            receipts[str(ref.source_id)]=receipt
        return receipts


@dataclass(frozen=True)
class ProcessingRunBinding:
    """Protected startup pins, never constructed from a request body."""
    source_binding: ProcessingSourceBinding
    descriptor_sha256: str
    parent_registry_sha256: str
    envelope_sha256: str

    def __post_init__(self):
        if (not isinstance(self.source_binding, ProcessingSourceBinding)
                or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v)
                       for v in (self.descriptor_sha256,self.parent_registry_sha256,self.envelope_sha256))):
            raise PermissionError('immutable processing run pins required')


class BoundProcessingSourceResolver(ProcessingSourceResolver):
    """One admitted run's short SQL hold; only local durable enqueue inside it."""
    def __init__(self, url: str, *, run_binding: ProcessingRunBinding):
        if not isinstance(run_binding,ProcessingRunBinding):
            raise PermissionError('immutable processing run binding required')
        self.run_binding=run_binding
        super().__init__(url,binding=run_binding.source_binding)

    @contextmanager
    def hold(self,descriptor,dispatch,*,connection=None):
        # Shared contracts come from the independently reviewed processing-context
        # lane. Missing integration fails closed; no substitute proof is minted.
        from .processing_context import ProcessingRunDescriptor,ProcessingDispatch,ProcessingAuthorityProof
        from .contracts import digest
        b=self.binding; pins=self.run_binding
        if (not isinstance(descriptor,ProcessingRunDescriptor)
                or not isinstance(dispatch,ProcessingDispatch)
                or b.profile not in {'source-reader','candidate-compiler','gateway-metadata'}
                or descriptor.actor_id!=b.principal
                or descriptor.runtime_hash!=b.runtime_hash
                or descriptor.source_registry_hash!=b.source_registry_hash
                or digest(descriptor.model_dump(mode='json'))!=pins.descriptor_sha256
                or descriptor.parent_registry_sha256!=pins.parent_registry_sha256
                or descriptor.envelope_sha256!=pins.envelope_sha256
                or dispatch not in descriptor.dispatches
                or dispatch.source_ref not in descriptor.source_refs
                or dispatch.source_ref.workspace_id!=descriptor.workspace_id
                or descriptor.purpose!='source-extraction'
                or datetime.now(timezone.utc)>=descriptor.expires_at):
            raise PermissionError('exact admitted processing run and dispatch required')
        ref=dispatch.source_ref
        with self._connection(connection) as conn:
            self._check(conn)
            rows=conn.execute('SELECT * FROM oracle2.hosting_current_source_identity(%s,%s,%s,%s,%s)',
                              self._args(descriptor.workspace_id,ref.source_id)).fetchall()
            if len(rows)!=1:
                raise PermissionError('unique processing proof identity required')
            revision,original,reading,parser,valid_until,checked_at=rows[0]
            actual=SourceRef(workspace_id=descriptor.workspace_id,source_id=ref.source_id,revision=revision,
                             original_sha256=original,reading_sha256=reading,parser_id=parser)
            expiry=min(valid_until,b.expires_at,descriptor.expires_at)
            if actual!=ref or checked_at>=expiry or datetime.now(timezone.utc)>=expiry:
                raise PermissionError('current processing proof identity or expiry differs')
            self._check(conn)
            proof=ProcessingAuthorityProof(workspace_id=descriptor.workspace_id,actor_id=b.principal,
                source_ref=ref,runtime_hash=b.runtime_hash,source_registry_hash=b.source_registry_hash,
                descriptor_sha256=pins.descriptor_sha256,parent_registry_sha256=pins.parent_registry_sha256,
                envelope_sha256=pins.envelope_sha256,purpose='source-extraction',
                session_role=b.expected_session_role,profile=b.profile,checked_at=checked_at,expires_at=expiry)
            yield proof
            # Actual database clock/grants are checked again before the local
            # transaction commits; wall-clock proof fields are not authority.
            if self.identity(descriptor.workspace_id,ref.source_id,connection=conn)!=ref:
                raise PermissionError('processing source changed during hold')
            self._check(conn)
            if datetime.now(timezone.utc)>=expiry:
                raise PermissionError('processing hold authority expired')


class ProcessingArtifactResolver(ProcessingSourceResolver):
    """Current generated metadata; no original bytes in artifact lookup."""
    _signatures={**ProcessingSourceResolver._signatures,
        'oracle2._processing_dependency_digest(uuid,uuid,integer)':frozenset(),
        'oracle2._processing_artifact_metadata(uuid,uuid,integer,uuid,text,text)':frozenset(),
        'oracle2.hosting_processing_extraction_seal(uuid,uuid,integer,uuid,text,text)':frozenset({'oracle2_candidate_compiler','oracle2_documentary_executor'}),
        'oracle2._processing_projection_actor(uuid,uuid,integer,text,text)':frozenset(),
        'oracle2._processing_projection_eligible(uuid,uuid,integer,jsonb,text,text)':frozenset(),
        'oracle2.lease_processing_projection(uuid,text,text,integer)':frozenset({'oracle2_candidate_compiler'}),
        'oracle2.ack_processing_projection(uuid,uuid,uuid,integer,jsonb,text,text,text,timestamp with time zone)':frozenset({'oracle2_candidate_compiler'}),
        'oracle2.commit_processing_candidate(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamp with time zone)':frozenset({'oracle2_candidate_compiler'}),
        'oracle2.hosting_processing_artifact(uuid,uuid,integer,uuid,text,text)':frozenset({'oracle2_candidate_compiler','oracle2_documentary_executor'}),
    }

    def artifact_metadata(self,workspace_id,artifact_id,version,*,connection=None):
        from .contracts import ArtifactManifest,PROCESSING_ARTIFACT_KINDS
        if (self.binding.profile not in {'candidate-compiler','documentary-executor'}
                or not isinstance(workspace_id,UUID) or not isinstance(artifact_id,UUID)
                or type(version) is not int or version<1):
            raise PermissionError('exact current processing artifact identity required')
        with self._connection(connection) as conn:
            self._check(conn)
            rows=conn.execute('SELECT * FROM oracle2.hosting_processing_artifact(%s,%s,%s,%s,%s,%s)',
                (workspace_id,artifact_id,version,self.binding.principal,self.binding.runtime_hash,self.binding.source_registry_hash)).fetchall()
            self._check(conn)
        if len(rows)!=1:raise PermissionError('unique current processing artifact required')
        manifest=ArtifactManifest.model_validate_json(json.dumps(rows[0][0]))
        refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in rows[0][1])
        if ((manifest.workspace_id,manifest.artifact_id,manifest.version)!=(workspace_id,artifact_id,version)
                or manifest.kind not in PROCESSING_ARTIFACT_KINDS or not refs
                or len(set(refs))!=len(refs)):
            raise PermissionError('current processing manifest differs')
        return manifest,refs


    def extraction_seal(self,workspace_id,artifact_id,version,*,connection=None):
        from .contracts import ProcessingExtractionSeal
        if (self.binding.profile not in {'candidate-compiler','documentary-executor'}
                or not isinstance(workspace_id,UUID) or not isinstance(artifact_id,UUID)
                or type(version) is not int or version<1):
            raise PermissionError('exact processing extraction seal identity required')
        with self._connection(connection) as conn:
            self._check(conn)
            rows=conn.execute('SELECT oracle2.hosting_processing_extraction_seal(%s,%s,%s,%s,%s,%s)',
                (workspace_id,artifact_id,version,self.binding.principal,self.binding.runtime_hash,self.binding.source_registry_hash)).fetchall()
            self._check(conn)
        if len(rows)!=1:raise PermissionError('unique current extraction seal required')
        seal=ProcessingExtractionSeal.model_validate_json(json.dumps(rows[0][0]))
        if (seal.workspace_id,seal.artifact_id,seal.version)!=(workspace_id,artifact_id,version):
            raise PermissionError('current extraction seal differs')
        return seal


_PURPOSE_PHASES_V2={
    'census':('source-census','chat'),
    'assembly':('operating-audit','chat'),
    'assessment':('independent-source-semantic-acceptance','chat'),
    'embedding':('source-extraction','embedding'),
}
_PURPOSE_RAW_SQL_V2={
    'source-census':'SELECT * FROM oracle2.hosting_source_census_receipt_v2(%s,%s,%s,%s,%s)',
    'operating-audit':'SELECT * FROM oracle2.hosting_operating_audit_receipt_v2(%s,%s,%s,%s,%s)',
    'independent-source-semantic-acceptance':'SELECT * FROM oracle2.hosting_independent_semantic_receipt_v2(%s,%s,%s,%s,%s)',
}
_PURPOSE_IDENTITY_SQL_V2={
    'source-census':'SELECT * FROM oracle2.hosting_source_census_identity_v2(%s,%s,%s,%s,%s)',
    'operating-audit':'SELECT * FROM oracle2.hosting_operating_audit_identity_v2(%s,%s,%s,%s,%s)',
    'independent-source-semantic-acceptance':'SELECT * FROM oracle2.hosting_independent_semantic_identity_v2(%s,%s,%s,%s,%s)',
    'source-extraction':'SELECT * FROM oracle2.hosting_projection_embedding_identity_v2(%s,%s,%s,%s,%s)',
}


@dataclass(frozen=True)
class PurposeSourceBindingV2:
    """External immutable startup pins. Construction is never appointment/issuance."""
    source: ProcessingSourceBinding
    phase: str
    purpose: str
    operation: str
    expected_provider_login: str
    caller_kind: str
    source_refs: tuple[SourceRef,...]
    population_digest: str
    descriptor_sha256: str
    parent_registry_sha256: str
    population_admission_sha256: str
    phase_registry_sha256: str
    projection_sha256: str

    def __post_init__(self):
        from .purpose_context import source_population_digest
        if (type(self.source) is not ProcessingSourceBinding
                or any(type(v) is not str for v in (self.phase,self.purpose,self.operation,self.caller_kind))
                or _PURPOSE_PHASES_V2.get(self.phase)!=(self.purpose,self.operation)
                or not isinstance(self.expected_provider_login,str)
                or not re.fullmatch('[a-z_][a-z0-9_]{0,62}',self.expected_provider_login)
                or self.caller_kind not in {'provider','gateway'}
                or type(self.source_refs) is not tuple or not self.source_refs
                or any(type(r) is not SourceRef for r in self.source_refs)
                or len({r.source_id for r in self.source_refs})!=len(self.source_refs)
                or len({r.workspace_id for r in self.source_refs})!=1
                or any(not re.fullmatch('[0-9a-f]{64}',r.parser_id) for r in self.source_refs)
                or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in (
                    self.population_digest,self.descriptor_sha256,self.parent_registry_sha256,
                    self.population_admission_sha256,self.phase_registry_sha256,self.projection_sha256))
                or source_population_digest(self.source_refs)!=self.population_digest):
            raise PermissionError('complete immutable purpose V2 pins required')
        if self.caller_kind=='provider':
            profile='gateway-metadata' if self.operation=='embedding' else 'source-reader'
            if self.source.profile!=profile or self.source.expected_session_role!=self.expected_provider_login:
                raise PermissionError('actual provider login/profile differs')
        elif self.source.profile!='gateway-metadata' or self.operation!='chat':
            raise PermissionError('only explicit chat gateway metadata profile permitted')


class _PurposeRoleVerifierV2(ProcessingSourceResolver):
    _signatures={**ProcessingSourceResolver._signatures,
        'oracle2._purpose_deadlines_v2()':frozenset(),
        'oracle2._purpose_source_v2(uuid,uuid,uuid,text,text,text,boolean)':frozenset(),
        **{f'oracle2.hosting_{name}_receipt_v2(uuid,uuid,uuid,text,text)':frozenset({'oracle2_source_reader'})
           for name in ('source_census','operating_audit','independent_semantic')},
        **{f'oracle2.hosting_{name}_identity_v2(uuid,uuid,uuid,text,text)':frozenset({'oracle2_source_reader','oracle2_gateway_metadata'})
           for name in ('source_census','operating_audit','independent_semantic')},
        'oracle2.hosting_projection_embedding_identity_v2(uuid,uuid,uuid,text,text)':frozenset({'oracle2_gateway_metadata'}),
        'oracle2._processing_dependency_digest(uuid,uuid,integer)':frozenset(),
        'oracle2._purpose_embedding_artifact_v2(uuid,uuid,integer,uuid,text,text)':frozenset(),
        'oracle2.hosting_projection_embedding_seal_v2(uuid,uuid,integer,uuid,text,text)':frozenset({'oracle2_gateway_metadata'}),
    }

    def _check(self,conn):
        super()._check(conn)
        # Executed before the fixed getter SELECT, so PostgreSQL actually arms
        # this statement's timer. Preserve any tighter positive caller deadline.
        conn.execute("SELECT set_config('statement_timeout',CASE WHEN current_setting('statement_timeout')::interval<=interval '0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN '5s' ELSE current_setting('statement_timeout') END,true)")


class PurposeSourceResolverV2:
    """Own-session current purpose source access; no V1 method/write fallback.

    Complete population pins come from independently admitted configuration.
    SQL validates each source, not filesystem registry/provider/issuer truth.
    Private parent/phase loading and provider calls must occur OUTSIDE holds.
    """
    def __init__(self,url: str,*,binding: PurposeSourceBindingV2):
        if type(binding) is not PurposeSourceBindingV2:
            raise PermissionError('exact externally admitted purpose binding required')
        self.url,self.binding=url,binding
        self._roles=_PurposeRoleVerifierV2(url,binding=binding.source)

    @property
    def metadata_only(self):
        return self.binding.source.profile=='gateway-metadata'

    def embedding_eligibility_seal(self,workspace_id,artifact_id,version,*,connection=None):
        from .contracts import ProcessingQualifiedProjectionSealV2
        b=self.binding;s=b.source
        if (b.phase!='embedding' or b.operation!='embedding' or b.caller_kind!='provider'
                or s.profile!='gateway-metadata' or s.expected_session_role!=b.expected_provider_login
                or not isinstance(workspace_id,UUID) or not isinstance(artifact_id,UUID)
                or type(version) is not int or version<1
                or any(r.workspace_id!=workspace_id for r in b.source_refs)):
            raise PermissionError('fixed own-login embedding metadata capability required')
        with self._roles._connection(connection) as conn:
            self._population(conn)
            rows=conn.execute('SELECT oracle2.hosting_projection_embedding_seal_v2(%s,%s,%s,%s,%s,%s)',
                (workspace_id,artifact_id,version,s.principal,s.runtime_hash,s.source_registry_hash)).fetchall()
            self._population(conn)
            if len(rows)!=1:raise PermissionError('unique qualified projection seal required')
            seal=ProcessingQualifiedProjectionSealV2.model_validate_json(json.dumps(rows[0][0]))
            if ((seal.workspace_id,seal.artifact_id,seal.version)!=(workspace_id,artifact_id,version)
                    or len(set(seal.source_refs))!=len(seal.source_refs)
                    or set(seal.source_refs)!=set(b.source_refs)
                    or len({(e.artifact_id,e.version) for e in seal.extraction_seals})!=len(seal.extraction_seals)
                    or any(e.workspace_id!=workspace_id or not set(e.source_refs)<=set(b.source_refs)
                           for e in seal.extraction_seals)
                    or set(r for e in seal.extraction_seals for r in e.source_refs)!=set(b.source_refs)):
                raise PermissionError('qualified projection complete population differs')
            # Canonical descriptor ordering is an application consistency pin;
            # this does not fabricate or replace the full manifest digest.
            return seal.model_copy(update={'source_refs':b.source_refs})

    def _check(self,conn):
        self._roles._check(conn)

    def _population(self,conn,*,raw=False):
        b=self.binding; s=b.source
        if raw and (b.caller_kind!='provider' or self.metadata_only or b.operation!='chat'):
            raise PermissionError('purpose context cannot open original bodies')
        query=(_PURPOSE_RAW_SQL_V2 if raw else _PURPOSE_IDENTITY_SQL_V2).get(b.purpose)
        if query is None:raise PermissionError('fixed purpose capability unavailable')
        self._check(conn)
        outputs=[];deadlines=[]
        for expected in b.source_refs:
            rows=conn.execute(query,(expected.workspace_id,expected.source_id,s.principal,s.runtime_hash,s.source_registry_hash)).fetchall()
            if len(rows)!=1:raise PermissionError('unique current purpose source required')
            row=rows[0]
            actual=SourceRef(workspace_id=expected.workspace_id,source_id=expected.source_id,revision=row[0],
                original_sha256=row[1],reading_sha256=row[2],parser_id=row[3])
            if actual!=expected:raise PermissionError('purpose full population source changed')
            if raw:
                provenance=ReadingProvenance.model_validate_json(row[5])
                if (provenance.original_hash,provenance.content_hash,provenance.parser_identity)!=(row[1],row[2],row[3]):
                    raise PermissionError('purpose original custody differs')
                output=SourceReceipt(ref=actual,reading=row[4],display_revision=f'r{actual.revision}')
            else:output=actual
            expiry,checked=row[-2:]
            if (not isinstance(expiry,datetime) or expiry.tzinfo is None or expiry.utcoffset() is None
                    or not isinstance(checked,datetime) or checked.tzinfo is None or checked.utcoffset() is None):
                raise PermissionError('actual finite purpose SQL clock required')
            outputs.append(output);deadlines.append(expiry)
        self._check(conn)
        now=conn.execute('SELECT clock_timestamp()').fetchone()[0]
        deadline=min(*deadlines,s.expires_at)
        if now>=deadline:raise PermissionError('purpose population authority expired')
        return tuple(outputs),deadline,now

    def identity(self,workspace_id,source_id,*,connection=None):
        if not any(r.workspace_id==workspace_id and r.source_id==source_id for r in self.binding.source_refs):
            raise PermissionError('source outside admitted full parent population')
        with self._roles._connection(connection) as conn:
            refs,_,_=self._population(conn)
        return next(r for r in refs if r.source_id==source_id)

    def read_population(self,*,connection=None):
        with self._roles._connection(connection) as conn:
            # Authorize EVERY source before opening the first original body.
            self._population(conn)
            receipts,_,_=self._population(conn,raw=True)
            self._population(conn)
        return receipts

    def current_for_purpose(self,workspace_id,source_id,*,connection=None):
        if not any(r.workspace_id==workspace_id and r.source_id==source_id for r in self.binding.source_refs):
            raise PermissionError('source outside admitted full parent population')
        return next(r for r in self.read_population(connection=connection) if r.ref.source_id==source_id)

    def _descriptor(self,descriptor,dispatch):
        from .contracts import digest
        from .purpose_context import PurposeRunDescriptorV2,PurposeDispatchV2
        b=self.binding;s=b.source
        if (type(descriptor) is not PurposeRunDescriptorV2 or type(dispatch) is not PurposeDispatchV2
                or digest(descriptor.model_dump(mode='json'))!=b.descriptor_sha256
                or descriptor.dispatch(dispatch.dispatch_id)!=dispatch
                or descriptor.workspace_id!=b.source_refs[0].workspace_id or descriptor.actor_id!=s.principal
                or descriptor.provider_login!=b.expected_provider_login
                or descriptor.phase!=b.phase or descriptor.purpose!=b.purpose or descriptor.operation!=b.operation
                or descriptor.runtime_hash!=s.runtime_hash or descriptor.source_registry_hash!=s.source_registry_hash
                or descriptor.parent_registry_sha256!=b.parent_registry_sha256
                or descriptor.population_admission_sha256!=b.population_admission_sha256
                or descriptor.phase_registry_sha256!=b.phase_registry_sha256
                or descriptor.population_digest!=b.population_digest
                or descriptor.source_refs!=b.source_refs or dispatch.source_refs!=b.source_refs
                or descriptor.issuer_actor==descriptor.reviewer_actor
                or descriptor.actor_id in {descriptor.issuer_actor,descriptor.reviewer_actor}):
            raise PermissionError('exact admitted purpose descriptor/dispatch required')
        return digest(dispatch.model_dump(mode='json'))

    @contextmanager
    def hold(self,descriptor,dispatch,*,connection=None):
        from .purpose_context import PurposeAuthorityProofV2
        b=self.binding;s=b.source
        dispatch_hash=self._descriptor(descriptor,dispatch)
        with self._roles._connection(connection) as conn:
            _,expiry,checked=self._population(conn)
            expiry=min(expiry,descriptor.expires_at)
            if checked>=expiry:raise PermissionError('purpose descriptor expired')
            caller,role=conn.execute('SELECT session_user,current_user').fetchone()
            if caller!=s.expected_session_role or (b.caller_kind=='provider' and caller!=descriptor.provider_login):
                raise PermissionError('actual purpose caller differs')
            proof=PurposeAuthorityProofV2(run_id=descriptor.run_id,workspace_id=descriptor.workspace_id,
                actor_id=descriptor.actor_id,admitted_provider_login=descriptor.provider_login,
                actual_caller_login=caller,dispatch_id=dispatch.dispatch_id,phase=b.phase,purpose=b.purpose,operation=b.operation,
                source_refs=b.source_refs,population_digest=b.population_digest,runtime_hash=s.runtime_hash,
                source_registry_hash=s.source_registry_hash,descriptor_sha256=b.descriptor_sha256,
                parent_registry_sha256=b.parent_registry_sha256,population_admission_sha256=b.population_admission_sha256,
                phase_registry_sha256=b.phase_registry_sha256,projection_sha256=b.projection_sha256,
                dispatch_hash=dispatch_hash,job_hash=dispatch.job_hash,request_hash=dispatch.request_hash,
                permission_hash=dispatch.permission_hash,session_role=role,profile=s.profile,
                checked_at=checked,expires_at=expiry)
            yield proof
            self._descriptor(descriptor,dispatch)
            _,current_expiry,now=self._population(conn)
            if now>=min(expiry,current_expiry):raise PermissionError('purpose authority expired before commit')
