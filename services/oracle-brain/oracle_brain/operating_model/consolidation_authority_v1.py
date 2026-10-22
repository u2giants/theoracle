"""Fixed canonical SQL revision/history consumer; no issuance or cross-request cache.

Installation supplies every binding and retained semantic pin independently.
Private body reads happen with no SQL connection held, followed by a new actual
current authority transaction. A lost write acknowledgement is UNKNOWN, not retry.
"""
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
import hashlib
from pathlib import Path
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from .contracts import ArtifactManifest,canonical_bytes,digest
from .consolidation_contracts_v1 import ConsolidationCoreV1,readable_diff,applicable_assertions
from .purpose_qualification_v3 import PurposeAssemblyQualificationV3
from .semantic_acceptance import sealed

from contextlib import contextmanager
from .request_deadline_v1 import (request_remaining_v1,sql_remaining_v1 as _sql_remaining_v1,
    sql_execute_v1 as _execute_v1,sql_rearm_v1,_sql_window_v1,_sql_send_window_v1)


from .protected_sql_connection_v1 import _connection_v1


_FUNCTIONS=(
 'hosting_consolidated_model_version_v1(uuid,integer,uuid,text,text,text,timestamp with time zone)',
 'commit_processing_model_revision_v1(jsonb,bytea,bytea,bytea,jsonb,uuid,text,text,text,timestamp with time zone,uuid)',
 'hosting_historical_consolidated_model_v1(uuid,timestamp with time zone,timestamp with time zone,uuid,text,text,text,timestamp with time zone)',
 'hosting_current_consolidated_model_v1(uuid,uuid,text,text,text,timestamp with time zone)',
 'record_processing_model_review_v1(uuid,integer,text,text,bytea,jsonb,text,uuid,uuid,text,text,text,timestamp with time zone)',
 'hosting_processing_review_diff_v1(uuid,integer,uuid,text,text,text,timestamp with time zone)',
 'hosting_processing_model_revision_v1(uuid,integer,uuid,text,text,text,timestamp with time zone)',
 'hosting_historical_source_revision_v1(jsonb,uuid,text,text,text,timestamp with time zone)',
 'record_processing_model_decision_change_v1(uuid,text,uuid,uuid,text,text,text,timestamp with time zone)',
 'hosting_processing_decision_event_v1(uuid,uuid,text,text,text,timestamp with time zone)')


@dataclass(frozen=True)
class ConsolidationBindingV1:
    appointment_id: UUID
    principal_id: UUID
    workspace_id: UUID
    model_id: UUID
    session_login: str
    expected_owner: str
    operation: str
    runtime_hash: str
    registry_hash: str
    config_hash: str
    ca_path: str
    ca_sha256: str
    original_horizon: datetime
    retained_semantic_admissions: frozenset[str]
    capability_body_hashes: tuple[tuple[str,str],...]

    def __post_init__(self):
        if (self.operation not in {'consolidate','history-read','business-review'}
                or any(type(x) is not UUID for x in (self.appointment_id,self.principal_id,self.workspace_id,self.model_id))
                or not self.session_login or not self.expected_owner or self.session_login==self.expected_owner
                or self.original_horizon.tzinfo is None or self.original_horizon.utcoffset() is None
                or type(self.retained_semantic_admissions) is not frozenset
                or type(self.capability_body_hashes) is not tuple or any(type(p) is not tuple or len(p)!=2 for p in self.capability_body_hashes)
                or not self.retained_semantic_admissions or len(self.retained_semantic_admissions)>64):
            raise PermissionError('external finite exact processing appointment required')
        expected={x.split('(')[0] for x in _FUNCTIONS}|{'_commit_processing_candidate_canonical_v1'}
        if len(dict(self.capability_body_hashes))!=len(self.capability_body_hashes) or set(dict(self.capability_body_hashes))!=expected:
            raise PermissionError('exact external capability body fingerprints required')
        import re
        if any(not re.fullmatch('[0-9a-f]{64}',h) for h in (self.runtime_hash,self.registry_hash,self.config_hash,self.ca_sha256,*self.retained_semantic_admissions,*(h for _,h in self.capability_body_hashes))):
            raise PermissionError('exact externally pinned hashes required')


@dataclass(frozen=True)
class ConsolidationReviewSnapshotV1:
    metadata:dict
    valid_until:datetime


class ConsolidationOutcomeUnknown(PermissionError):
    pass


class ConsolidationAuthorityV1:
    def __init__(self,url,*,binding,delivery_capability_body_hashes=()):
        if type(binding) is not ConsolidationBindingV1:raise PermissionError('exact fixed installation binding required')
        self.url,self.binding=url,binding
        from .consolidated_delivery_v1 import DELIVERY_FUNCTIONS
        import re
        pins=delivery_capability_body_hashes
        if (type(pins) is not tuple or any(type(p) is not tuple or len(p)!=2 for p in pins)
                or len(dict(pins))!=len(pins)
                or pins and (set(dict(pins))!={x.split('(')[0] for x in DELIVERY_FUNCTIONS}
                    or any(type(v) is not str or not re.fullmatch('[a-f0-9]{64}',v) for _,v in pins))):
            raise PermissionError('exact independently pinned readonly delivery catalog required')
        self.delivery_capability_body_hashes=pins
        params=psycopg.conninfo.conninfo_to_dict(url)
        if params.get('sslmode')!='verify-full' or params.get('sslrootcert')!=binding.ca_path or params.get('user')!=binding.session_login:
            raise PermissionError('pinned verify-full processing connection required')
        self._ca()

    def _ca(self):
        if hashlib.sha256(Path(self.binding.ca_path).read_bytes()).hexdigest()!=self.binding.ca_sha256:
            raise PermissionError('pinned CA changed')

    def _deadline(self,deadline):
        request_remaining_v1(required=False)
        now=datetime.now(timezone.utc)
        if (not isinstance(deadline,datetime) or deadline.tzinfo is None or deadline.utcoffset() is None
                or deadline<=now or deadline>self.binding.original_horizon or deadline>now+timedelta(seconds=30)):
            raise PermissionError('original fixed bounded caller deadline required')
        return deadline

    def _check(self,c,deadline):
        self._ca();b=self.binding
        if datetime.now(timezone.utc)>=min(deadline,b.original_horizon) or not c.pgconn.ssl_in_use:
            raise PermissionError('current bounded TLS processing context required')
        if _execute_v1(c,deadline,'SELECT session_user,current_user').fetchone()!=(b.session_login,b.session_login):
            raise PermissionError('actual processing login changed')
        rows=_execute_v1(c,deadline,'''SELECT p.oid,n.nspname,p.proname,r.rolname,p.prosecdef,pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p.prosrc,'UTF8')),'hex'),p.proconfig FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
          WHERE p.oid IN (SELECT pg_catalog.to_regprocedure(x) FROM pg_catalog.unnest(%s::text[]) x)''',
          (['oracle2.'+s for s in _FUNCTIONS],)).fetchall()
        if (len(rows)!=len(_FUNCTIONS) or any(n!='oracle2' or owner!=b.expected_owner or defin is not True or body_hash!=dict(b.capability_body_hashes)[name] or settings!=['search_path=pg_catalog, oracle2'] for _,n,name,owner,defin,body_hash,settings in rows)
                or {r[2] for r in rows}!={s.split('(')[0] for s in _FUNCTIONS}):
            raise PermissionError('fixed canonical capability owners differ')
        private=_execute_v1(c,deadline,"""SELECT n.nspname,r.rolname,p.prosecdef,
          NOT EXISTS(SELECT 1 FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) x WHERE x.grantee<>p.proowner),pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p.prosrc,'UTF8')),'hex'),p.proconfig
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
          WHERE p.oid=pg_catalog.to_regprocedure('oracle2._commit_processing_candidate_canonical_v1(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamp with time zone)')""").fetchone()
        if private!=('oracle2',b.expected_owner,True,True,dict(b.capability_body_hashes)['_commit_processing_candidate_canonical_v1'],['search_path=pg_catalog, oracle2']):
            raise PermissionError('canonical owner-private helper identity or ACL changed')
        remaining=max(1,min(2000,int(_sql_remaining_v1(deadline)*1000)))
        sql_rearm_v1(c,deadline,timeout_ms=remaining)

    def _arguments(self,deadline):
        b=self.binding
        return (b.appointment_id,b.runtime_hash,b.registry_hash,b.config_hash,deadline)

    def _metadata(self,model,*,deadline,valid_at=None,known_at=None,version=None):
        self._deadline(deadline)
        if self.binding.operation!='history-read' or type(model) is not UUID or model!=self.binding.model_id:raise PermissionError('distinct fixed history appointment required')
        with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as c:
            self._check(c,deadline)
            if version is not None:
                if type(version) is not int or version<1 or valid_at is not None or known_at is not None:raise PermissionError('exact retained version selector required')
                result=_execute_v1(c,deadline,'SELECT oracle2.hosting_consolidated_model_version_v1(%s,%s,%s,%s,%s,%s,%s)',(model,version,*self._arguments(deadline))).fetchone()[0]
            elif valid_at is None and known_at is None:
                result=_execute_v1(c,deadline,'SELECT oracle2.hosting_current_consolidated_model_v1(%s,%s,%s,%s,%s,%s)',(model,*self._arguments(deadline))).fetchone()[0]
            elif valid_at is not None and known_at is not None:
                result=_execute_v1(c,deadline,'SELECT oracle2.hosting_historical_consolidated_model_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(model,valid_at,known_at,*self._arguments(deadline))).fetchone()[0]
            else:raise ValueError('both explicit historical times required')
            self._check(c,deadline)
            if datetime.now(timezone.utc)>=datetime.fromisoformat(result['validUntil']):raise PermissionError('SQL scope expired')
        self._check_after_close(deadline,result)
        return result

    def _check_after_close(self,deadline,result):
        request_remaining_v1(required=False)
        self._ca()
        if datetime.now(timezone.utc)>=min(deadline,self.binding.original_horizon,datetime.fromisoformat(result['validUntil'])):
            raise PermissionError('authority expired at connection close')

    def _read_model_packet_v1(self,model,*,blobs,deadline,valid_at=None,known_at=None,version=None):
        before=self._metadata(model,deadline=deadline,valid_at=valid_at,known_at=known_at,version=version)
        manifest=ArtifactManifest.model_validate_json(canonical_bytes(before['manifest']))
        if manifest.workspace_id!=self.binding.workspace_id:raise PermissionError('cross-workspace capability')
        # Existing immutable private-object owner; no caller path/URL/role selector.
        import json
        request_remaining_v1(required=False)
        raw=blobs.read(manifest.private_object_key,manifest.content_hash)
        request_remaining_v1(required=False)
        payload=json.loads(raw)
        if digest(payload)!=manifest.content_hash:raise PermissionError('retained model bytes differ')
        core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
        from .source_receipts import SourceRef
        actual_refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in payload['source_refs'])
        permitted_refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in before['sourceRefs'])
        if (len(set(actual_refs))!=len(actual_refs) or set(actual_refs)!=set(permitted_refs) or set(core.model.source_refs)!=set(actual_refs)
                or digest({'refs':payload['source_refs']})!=manifest.source_digest):
            raise PermissionError('exact complete qualified source population differs')
        q=PurposeAssemblyQualificationV3.model_validate_json(canonical_bytes(payload['assembly_qualification']));admission=q.admission
        recorded=datetime.fromisoformat(before['recordedAt'])
        if (sealed(admission) not in self.binding.retained_semantic_admissions
                or admission.captured_schema!='purpose-captured-consolidation-v1'
                or admission.runtime_hash!=manifest.compiler_digest or admission.compiler_permission_hash!=manifest.permission_digest
                or digest({k:v for k,v in payload.items() if k!='assembly_qualification'})!=admission.final_envelope_hash
                or not admission.candidate_created_at<=recorded<admission.expires_at
                or before['mode']=='current' and datetime.now(timezone.utc)>=admission.expires_at
                or core.model.model_id!=model or core.model.workspace_id!=manifest.workspace_id
                or core.model.version!=manifest.version):
            raise PermissionError('exact retained independently qualified temporal body required')
        after=self._metadata(model,deadline=deadline,valid_at=valid_at,known_at=known_at,version=version)
        if after!=before:raise PermissionError('current history capability changed during private read')
        self._check_after_close(deadline,after)
        return core,after,payload

    def _check_delivery_catalog_v1(self,connection,deadline):
        from .consolidated_delivery_v1 import DELIVERY_FUNCTIONS,DELIVERY_SIGNATURE
        self._check(connection,deadline)
        pins=dict(self.delivery_capability_body_hashes)
        if set(pins)!={x.split('(')[0] for x in DELIVERY_FUNCTIONS}:
            raise PermissionError('separately installed retained delivery consumer missing')
        for signature in DELIVERY_FUNCTIONS:
            row=_execute_v1(connection,deadline,"""SELECT p.oid,r.rolname,p.prosecdef,p.provolatile,p.proconfig,
                pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p.prosrc,'UTF8')),'hex'),
                pg_catalog.has_function_privilege(SESSION_USER,p.oid,'EXECUTE')
                FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
                WHERE p.oid=pg_catalog.to_regprocedure(%s)""",('oracle2.'+signature,)).fetchone()
            if (row is None or row[1:3]!=(self.binding.expected_owner,True)
                    or row[4]!=['search_path=pg_catalog, oracle2'] or row[5]!=pins[signature.split('(')[0]]
                    or signature==DELIVERY_SIGNATURE and (row[3]!='v' or row[6] is not True)):
                raise PermissionError('exact retained delivery capability identity changed')
            grants=_execute_v1(connection,deadline,"""SELECT coalesce(r.rolname,'PUBLIC'),x.is_grantable
                FROM pg_catalog.pg_proc p CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) x
                LEFT JOIN pg_catalog.pg_roles r ON r.oid=x.grantee
                WHERE p.oid=%s AND x.privilege_type='EXECUTE' AND x.grantee<>p.proowner""",(row[0],)).fetchall()
            if signature==DELIVERY_SIGNATURE:
                from .consolidated_delivery_v1 import validate_direct_history_getter_acl_v1
                _sql_remaining_v1(deadline)
                validate_direct_history_getter_acl_v1(connection,row[0],required_login=self.binding.session_login,deadline=deadline)
                _sql_remaining_v1(deadline)
            elif grants:raise PermissionError('retained delivery private helper ACL changed')

    def projection_delivery_v1(self,model,version,*,deadline,valid_at=None,known_at=None):
        from .consolidated_delivery_v1 import ConsolidatedReadDeliveryV1
        from .source_receipts import SourceRef
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        if self.binding.operation!='history-read' or type(model) is not UUID or model!=self.binding.model_id or type(version) is not int or version<1:
            raise PermissionError('exact actual own history delivery consumer required')
        before=self._metadata(model,deadline=deadline,valid_at=valid_at,known_at=known_at)
        if before['manifest']['version']!=version:raise PermissionError('selected model changed before delivery read')
        request_remaining_v1()
        with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as connection:
            request_remaining_v1();self._check_delivery_catalog_v1(connection,deadline)
            raw=_execute_v1(connection,deadline,'SELECT oracle2.hosting_consolidated_projection_delivery_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (model,version,valid_at,known_at,*self._arguments(deadline))).fetchone()[0]
            request_remaining_v1();self._check_delivery_catalog_v1(connection,deadline)
        request_remaining_v1()
        result=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(raw))
        if ((result.workspace_id,result.model_id,result.version,result.model_content_hash)!=(self.binding.workspace_id,model,version,before['manifest']['content_hash'])
                or set(result.source_refs)!={SourceRef.model_validate_json(canonical_bytes(r)) for r in before['sourceRefs']}
                or (result.valid_at,result.known_at)!=(valid_at,known_at)
                or not result.checked_at<=datetime.now(timezone.utc)<result.valid_until<=min(deadline,self.binding.original_horizon)):
            raise PermissionError('actual retained delivery/read scope differs')
        after=self._metadata(model,deadline=deadline,valid_at=valid_at,known_at=known_at)
        if before!=after:raise PermissionError('recipient model changed during retained delivery read')
        self._check_after_close(deadline,after);request_remaining_v1()
        return result

    def read_serving_packet_v1(self,model,*,blobs,deadline,valid_at=None,known_at=None):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        metadata=self._metadata(model,deadline=deadline,valid_at=valid_at,known_at=known_at)
        version=metadata['manifest']['version']
        before=self.projection_delivery_v1(model,version,deadline=deadline,valid_at=valid_at,known_at=known_at)
        request_remaining_v1()
        core,actual,payload=self._read_model_packet_v1(model,blobs=blobs,deadline=deadline,valid_at=valid_at,known_at=known_at)
        request_remaining_v1()
        after=self.projection_delivery_v1(model,version,deadline=deadline,valid_at=valid_at,known_at=known_at)
        fixed=lambda r:r.model_dump(mode='json',exclude={'checked_at','valid_until'})
        if metadata!=actual or fixed(before)!=fixed(after):raise PermissionError('retained model or delivery changed around private body')
        return core,actual,payload,after

    def review_v1(self,*,model,version,content_hash,decision,scope,assertions,bundle_hash,idempotency,deadline):
        self._deadline(deadline)
        if self.binding.operation!='business-review' or model!=self.binding.model_id:raise PermissionError('separate scoped business decision appointment required')
        attempted=False;body_complete=False
        try:
            with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as c:
                self._check(c,deadline)
                attempted=True
                result=_execute_v1(c,deadline,'SELECT oracle2.record_processing_model_review_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (model,version,content_hash,decision,canonical_bytes(scope),Jsonb(assertions),bundle_hash,idempotency,*self._arguments(deadline))).fetchone()[0]
                self._check(c,deadline)
                body_complete=True
        except (psycopg.errors.SerializationFailure,psycopg.errors.UniqueViolation,psycopg.errors.InsufficientPrivilege):
            if body_complete:raise ConsolidationOutcomeUnknown('decision commit/close outcome UNKNOWN; read-only reconciliation required, no retry') from None
            raise
        except Exception:
            if attempted:raise ConsolidationOutcomeUnknown('business review outcome UNKNOWN; read-only reconciliation required, no automatic retry') from None
            raise
        try:
            self._check_after_close(deadline,result)
            # Independent fresh purpose recheck after actual write ACK/connection close.
            with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as c:
                self._check(c,deadline)
                fresh=_execute_v1(c,deadline,'SELECT oracle2.hosting_processing_review_diff_v1(%s,%s,%s,%s,%s,%s,%s)',
                    (model,version,*self._arguments(deadline))).fetchone()[0]
                if fresh['currentVersion']!=version or fresh['currentContentHash']!=content_hash:
                    raise PermissionError('accepted version changed after commit')
                self._check(c,deadline)
            self._check_after_close(deadline,fresh)
        except Exception:
            raise ConsolidationOutcomeUnknown('decision committed but current readback unavailable; read-only reconciliation required, no retry') from None
        return result


    def decision_change_v1(self,*,target_event,action,idempotency,deadline):
        self._deadline(deadline)
        if (self.binding.operation!='business-review' or type(target_event) is not UUID
                or type(idempotency) is not UUID or action not in {'challenge','withdraw'}):
            raise PermissionError('fixed currently scoped decision-change capability required')
        attempted=False;body_complete=False
        try:
            with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as c:
                self._check(c,deadline);attempted=True
                result=_execute_v1(c,deadline,'SELECT oracle2.record_processing_model_decision_change_v1(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (target_event,action,idempotency,*self._arguments(deadline))).fetchone()[0]
                self._check(c,deadline)
                body_complete=True
        except (psycopg.errors.SerializationFailure,psycopg.errors.UniqueViolation,psycopg.errors.InsufficientPrivilege):
            if body_complete:raise ConsolidationOutcomeUnknown('decision commit/close outcome UNKNOWN; read-only reconciliation required, no retry') from None
            raise
        except Exception:
            if attempted:raise ConsolidationOutcomeUnknown('decision change outcome UNKNOWN; read-only reconciliation required, no automatic retry') from None
            raise
        try:
            self._check_after_close(deadline,result)
            with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as c:
                self._check(c,deadline)
                fresh=_execute_v1(c,deadline,'SELECT oracle2.hosting_processing_decision_event_v1(%s,%s,%s,%s,%s,%s)',
                    (result['eventId'],*self._arguments(deadline))).fetchone()[0]
                self._check(c,deadline)
            self._check_after_close(deadline,fresh)
        except Exception:
            raise ConsolidationOutcomeUnknown('decision committed but current readback unavailable; read-only reconciliation required, no retry') from None
        return result


    def read_model_v1(self,model,*,blobs,deadline,valid_at=None,known_at=None):
        core,metadata,_=self._read_model_packet_v1(model,blobs=blobs,deadline=deadline,valid_at=valid_at,known_at=known_at)
        return core,metadata

    def read_answer_v1(self,model,*,scope,blobs,deadline,valid_at=None,known_at=None):
        from .consolidation_contracts_v1 import AssertionScopeV1
        if type(scope) is not AssertionScopeV1:raise PermissionError('explicit typed documentary query scope required')
        at=valid_at if valid_at is not None else datetime.now(timezone.utc)
        core,metadata,payload=self._read_model_packet_v1(model,blobs=blobs,deadline=deadline,valid_at=valid_at,known_at=known_at)
        selected=applicable_assertions(core,valid_at=at,scope=scope)
        observations={o['observation_id']:o for o in payload['observations']}
        findings={f['finding_id']:f for f in payload.get('findings',[])}
        def documentary(assertion):
            groups={}
            for polarity,ids in (('supporting',assertion.supporting_observations),('opposing',assertion.opposing_observations),('unknown',assertion.unknown_finding_ids),('temporal',assertion.temporal_observations)):
                groups[polarity]=tuple(quote for identifier in ids for quote in (findings[identifier]['evidence_refs'] if polarity=='unknown' else observations[identifier]['evidence']))
            return {'assertion':assertion.model_dump(mode='json'),'evidence':groups,'authority':'reported','policyEligibility':'unknown'}
        def possible(a):
            for key in ('process','customer','product','region'):
                offer,query=getattr(a.scope,key),getattr(scope,key)
                if offer.mode=='exact' and query.mode=='exact' and not set(offer.identities)&set(query.identities):return False
            return True
        unresolved=tuple(a for a in core.assertions if possible(a) and (a.valid_time=='unknown' or any(getattr(a.scope,k).mode=='unknown' for k in ('process','customer','product','region'))))
        response={'modelId':str(model),'version':core.model.version,'contentHash':metadata['manifest']['content_hash'],
            'mode':metadata['mode'],'validAt':at.isoformat(),'knownAt':known_at.isoformat() if known_at is not None else 'current',
            'assertions':tuple(documentary(a) for a in selected[:64]),'unresolved':tuple(documentary(a) for a in unresolved[:16]),
            'totalApplicable':len(selected),'totalUnresolved':len(unresolved),'truncated':len(selected)>64 or len(unresolved)>16,
            'policyEligibility':'unknown','modelConfirmed':False,'businessDecisions':metadata.get('businessDecisions',())}
        fresh=self._metadata(model,deadline=deadline,valid_at=valid_at,known_at=known_at)
        if fresh!=metadata:raise PermissionError('documentary query authority changed during answer packing')
        self._check_after_close(deadline,fresh)
        return response

    def review_metadata_v1(self,model,*,expected_version,deadline):
        self._deadline(deadline)
        if self.binding.operation!='business-review' or model!=self.binding.model_id or type(expected_version) is not int or expected_version<1:
            raise PermissionError('fixed exact current business review selector required')
        with _connection_v1(self.url,deadline,require_pinned_address=bool(self.delivery_capability_body_hashes)) as c:
            self._check(c,deadline)
            result=_execute_v1(c,deadline,'SELECT oracle2.hosting_processing_review_diff_v1(%s,%s,%s,%s,%s,%s,%s)',
                (model,expected_version,*self._arguments(deadline))).fetchone()[0]
            self._check(c,deadline)
        self._check_after_close(deadline,result)
        return result

    def read_review_diff_v1(self,model,*,expected_version,blobs,deadline,history_authority=None):
        return self.read_review_snapshot_v1(model,expected_version=expected_version,blobs=blobs,deadline=deadline,history_authority=history_authority).metadata

    def read_review_snapshot_v1(self,model,*,expected_version,blobs,deadline,history_authority=None):
        """Both exact per-principal capabilities, no automatic rebase/approval."""
        current=self.review_metadata_v1(model,expected_version=expected_version,deadline=deadline)
        redacted={**{k:current[k] for k in ('modelId','currentVersion','currentContentHash','conflict')},
            'basePermitted':False,'message':'Base history is not permitted; reload current review.',
            'automaticRebase':False,'policyEligibility':'unknown'}
        def redacted_packet(value):
            end=min(deadline,self.binding.original_horizon,datetime.fromisoformat(value['validUntil']))
            self._check_after_close(end,value)
            return ConsolidationReviewSnapshotV1({**redacted,'currentVersion':value['currentVersion'],'currentContentHash':value['currentContentHash']},end)
        if (type(history_authority) is not ConsolidationAuthorityV1 or history_authority.binding.operation!='history-read'
                or (history_authority.binding.principal_id,history_authority.binding.workspace_id,history_authority.binding.model_id)
                !=(self.binding.principal_id,self.binding.workspace_id,self.binding.model_id)):
            return redacted_packet(current)
        try:
            latest,latest_metadata,latest_payload=history_authority._read_model_packet_v1(model,blobs=blobs,deadline=deadline,version=current['currentVersion'])
            base,base_metadata,base_payload=history_authority._read_model_packet_v1(model,blobs=blobs,deadline=deadline,version=expected_version)
            if base.model.version!=expected_version or latest.model.version!=current['currentVersion']:return redacted_packet(current)
            changes=readable_diff(base,latest) if base.model.version!=latest.model.version else ()
        except (PermissionError,psycopg.Error):
            # Reprove current access before even returning the redacted refresh.
            return redacted_packet(self.review_metadata_v1(model,expected_version=expected_version,deadline=deadline))
        fresh=self.review_metadata_v1(model,expected_version=expected_version,deadline=deadline)
        if fresh!=current:return redacted_packet(fresh)
        response={**redacted,'basePermitted':True,'message':'Review exact changes before a new decision.',
            'baseRecordedAt':base_metadata['recordedAt'],'currentRecordedAt':latest_metadata['recordedAt'],
            'currentAssertions':tuple(_review_assertion(latest_payload,a) for a in latest.assertions[:64]),
            'totalAssertions':len(latest.assertions),'businessDecisions':latest_metadata.get('businessDecisions',()),
            'changes':tuple({**change,'beforeEvidence':_review_evidence(base_payload,change['before']),
                'afterEvidence':_review_evidence(latest_payload,change['after'])} for change in changes[:64]),
            'totalChanges':len(changes),'truncated':len(changes)>64 or len(latest.assertions)>64}
        # Reprove each independent history scope AFTER all private diff packing.
        try:
            latest_fresh=history_authority._metadata(model,deadline=deadline,version=latest.model.version)
            base_fresh=history_authority._metadata(model,deadline=deadline,version=base.model.version)
            if latest_fresh!=latest_metadata or base_fresh!=base_metadata:raise PermissionError('history review snapshot changed')
        except (PermissionError,psycopg.Error):
            return redacted_packet(self.review_metadata_v1(model,expected_version=expected_version,deadline=deadline))
        final=self.review_metadata_v1(model,expected_version=expected_version,deadline=deadline)
        if final!=current:return redacted_packet(final)
        end=min(deadline,self.binding.original_horizon,history_authority.binding.original_horizon,
            *(datetime.fromisoformat(m['validUntil']) for m in (final,latest_fresh,base_fresh)))
        history_authority._check_after_close(end,latest_fresh);self._check_after_close(end,final)
        return ConsolidationReviewSnapshotV1(response,end)


def _review_evidence(payload,assertion):
    if assertion is None:return None
    observations={o['observation_id']:o for o in payload['observations']};findings={f['finding_id']:f for f in payload.get('findings',[])}
    return {polarity:tuple(quote for key in assertion.get(field,()) for quote in (findings[key]['evidence_refs'] if polarity=='unknown' else observations[key]['evidence']))
        for polarity,field in (('supporting','supporting_observations'),('opposing','opposing_observations'),('unknown','unknown_finding_ids'),('temporal','temporal_observations'))}

def _review_assertion(payload,assertion):
    body=assertion.model_dump(mode='json')
    return {'assertion':body,'evidence':_review_evidence(payload,body)}
