"""Fixed raw PDF startup and currentness; never creates a grant or provider key."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import os,re,hashlib

from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalPopulationV1
from oracle_brain.operating_model.original_source_authority_v1 import OriginalSourceBindingV1,OriginalSourceResolverV1,OriginalPopulationSnapshotV1
from oracle_brain.operating_model.raw_original_context_v1 import RawOriginalPhaseContextV1
from oracle_brain.operating_model.raw_vision_policy_v1 import RawVisionTokenPolicyV1
from .purpose_journey_v2 import _worker_file,_worker_json,_worker_parse,_require
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import RawBillingBoundsV1
from .purpose_transport import PurposeTLSBindingV2
from .custody import DurableNonceSequenceV2
from .raw_original_observer_v1 import RawOriginalObserverAdmissionV1,RawOriginalObserverClientV1,RawOriginalCurrentnessConsumerV1,RawOriginalObservedCurrentnessV1

HASH=r'^[0-9a-f]{64}$'

class RawPrivateFileV1(StrictRecord):
    path:str
    sha256:str=Field(pattern=HASH)

class RawObserverTLSV1(StrictRecord):
    hostname:str
    port:int=Field(strict=True,ge=1,le=65535)
    server_uri:str
    client_uri:str
    ca:RawPrivateFileV1
    certificate:RawPrivateFileV1
    key:RawPrivateFileV1

class RawOriginalProviderConfigV1(StrictRecord):
    schema_version:Literal[1]=1
    purpose:Literal['raw-original-provider-startup-v1']='raw-original-provider-startup-v1'
    population:RawOriginalPopulationV1
    actor_id:UUID
    phase_purpose:Literal['source-original-reading','source-original-review']
    expected_owner_role:str
    expected_session_role:str
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    billing_bounds:RawPrivateFileV1|None=None
    reading_packet:RawPrivateFileV1|None=None
    database_url:RawPrivateFileV1
    database_ca:RawPrivateFileV1
    database_hostname:str
    database_port:int=Field(strict=True,ge=1,le=65535)
    database_name:str
    context:RawPrivateFileV1
    observer_admission:RawPrivateFileV1
    observer_tls:RawObserverTLSV1
    observer_spool:str
    observer_namespace:str
    observer_initialization_hash:str=Field(pattern=HASH)
    original_root:str
    original_root_identity:tuple[int,int,int]
    storage_profile_hash:str=Field(pattern=HASH)
    vision_policy:RawPrivateFileV1
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw startup version required')
        return v

    @model_validator(mode='after')
    def finite_independent_startup(self):
        if (len({self.actor_id,self.issuer_actor,self.reviewer_actor})!=3
            or not self.valid_from<self.expires_at<=self.population.expires_at<=self.original_horizon
            or self.original_root_identity[2]!=os.getuid()
            or any(v<0 for v in self.original_root_identity)):
            raise ValueError('independent bounded raw startup required')
        return self

class RawOriginalProviderAppointmentV1(StrictRecord):
    schema_version:Literal[1]=1
    purpose:Literal['raw-original-provider-appointment-v1']='raw-original-provider-appointment-v1'
    config_sha256:str=Field(pattern=HASH)
    context_sha256:str=Field(pattern=HASH)
    population:RawOriginalPopulationV1
    actor_id:UUID
    expected_session_role:str
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw appointment version required')
        return v

@dataclass(frozen=True)
class RawOriginalBillingEvidenceV1:
    """Protected observed bytes, not proof of route, terms or spend authority.

    Both commitments are named separately even under the canonical-file policy.
    Caller construction authenticates neither a protected read nor appointment.
    """
    raw_bytes:bytes
    bounds:RawBillingBoundsV1
    original_file_sha256:str
    canonical_record_sha256:str

    def __post_init__(self):
        _require(type(self.raw_bytes) is bytes and 0<len(self.raw_bytes)<=100000
            and type(self.bounds) is RawBillingBoundsV1,
            'exact bounded billing evidence required')
        parsed=_worker_parse(self.raw_bytes,RawBillingBoundsV1)
        canonical=canonical_bytes(parsed.model_dump(mode='json'))
        _require(self.raw_bytes==canonical and parsed==self.bounds
            and type(self.original_file_sha256) is str and re.fullmatch(HASH,self.original_file_sha256)
            and type(self.canonical_record_sha256) is str and re.fullmatch(HASH,self.canonical_record_sha256)
            and hashlib.sha256(self.raw_bytes).hexdigest()==self.original_file_sha256
            and digest(parsed.model_dump(mode='json'))==self.canonical_record_sha256,
            'original billing bytes and canonical record commitments differ')


def _billing_matches_context(bounds,context,now):
    # These are the billing identity/route/window predicates of the pure endpoint
    # comparator, not its metadata pricing/capacity verdict. The future factory
    # must separately supply actual broker identity and actual observed wires.
    x=RawOriginalPhaseContextV1.model_validate_json(context.model_dump_json())
    j=x.job;q=j.pricing
    expected=(q.account,q.key_fingerprint,q.ledger_registry_hash,q.terms_hash)
    _require(type(bounds) is RawBillingBoundsV1
        and (bounds.account,bounds.key_fingerprint,bounds.ledger_registry_hash,bounds.terms_hash)==expected
        and q.account=='key-sha256:'+q.key_fingerprint and bounds.model==q.model
        and q.admitted_register_hash==j.register_hash
        and q.terms_hash==j.processing_request.terms_hash
        and digest(q.model_dump(mode='json'))==x.pricing_quote_hash
        and q.is_byok==(bounds.route=='byok')
        and q.valid_from<=now<q.expires_at<=bounds.expires_at and bounds.valid_from<=now,
        'protected billing bounds differ from current exact context quote')
    _require(all(getattr(q,name)==getattr(bounds,name) for name in
        ('upstream_input_per_million_usd','upstream_output_per_million_usd',
         'upstream_per_image_fee_usd','upstream_per_request_fee_usd')),
        'protected billing upstream bounds differ from current quote')


@dataclass(frozen=True)
class RawOriginalAuthorityWindowV1:
    current_until:datetime
    operation_horizon:datetime
    sql_receipt_hash:str
    observer_witness_hash:str

    def __post_init__(self):
        if (any(type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None
                for v in (self.current_until,self.operation_horizon))
            or self.current_until>self.operation_horizon
            or any(type(v) is not str or re.fullmatch(HASH,v) is None
                for v in (self.sql_receipt_hash,self.observer_witness_hash))):
            raise PermissionError('finite exact raw authorization window required')

@dataclass(frozen=True)
class RawOriginalObservedAuthorityWindowV1:
    """Captured actual evidence bytes only, never a caller-issued authority.

    Constructing/replaying this descriptive record does not repeat SQL, TLS or
    replay advancement. Obtain current evidence through the appointed settings.
    """
    window:RawOriginalAuthorityWindowV1
    before_snapshot_bytes:bytes
    after_snapshot_bytes:bytes
    observer_evidence:RawOriginalObservedCurrentnessV1
    observed_at:datetime

    def __post_init__(self):
        if (type(self.window) is not RawOriginalAuthorityWindowV1
                or type(self.observer_evidence) is not RawOriginalObservedCurrentnessV1
                or type(self.observed_at) is not datetime or self.observed_at.tzinfo is None
                or self.observed_at.utcoffset() is None
                or any(type(raw) is not bytes or not 0<len(raw)<=100_000
                    for raw in (self.before_snapshot_bytes,self.after_snapshot_bytes))):
            raise PermissionError('exact bounded observed raw window evidence required')
        before=self.before_snapshot;after=self.after_snapshot;observed=self.observer_evidence
        # Revalidate the signature/bytes too, including constructed/tampered DTOs.
        RawOriginalObservedCurrentnessV1(**observed.__dict__)
        RawOriginalAuthorityWindowV1(**self.window.__dict__)
        _require(before.population==after.population==observed.witness.population
            and before.actual_principal_id==after.actual_principal_id==observed.admission.principal_id
            and before.session_role==after.session_role
            and before.original_allocation_hash==after.original_allocation_hash
            and before.original_horizon==after.original_horizon,
            'observed raw SQL/observer identity differs')
        _require(canonical_bytes(before.model_dump(mode='json'))==self.before_snapshot_bytes
            and canonical_bytes(after.model_dump(mode='json'))==self.after_snapshot_bytes
            and self.window.sql_receipt_hash==hashlib.sha256(self.after_snapshot_bytes).hexdigest()
            and self.window.observer_witness_hash==hashlib.sha256(observed.witness_bytes).hexdigest()
            and observed.observed_at<=self.observed_at<self.window.current_until,
            'observed raw window bytes/hash/horizon differ')

    @property
    def before_snapshot(self):
        return OriginalPopulationSnapshotV1.model_validate_json(self.before_snapshot_bytes)

    @property
    def after_snapshot(self):
        return OriginalPopulationSnapshotV1.model_validate_json(self.after_snapshot_bytes)


@dataclass(frozen=True)
class RawOriginalProviderSettingsV1:
    config:RawOriginalProviderConfigV1
    config_path:Path
    config_sha256:str
    appointment_path:Path
    appointment_sha256:str
    appointment:RawOriginalProviderAppointmentV1
    resolver:OriginalSourceResolverV1
    observer:RawOriginalCurrentnessConsumerV1
    context:RawOriginalPhaseContextV1
    vision_policy:RawVisionTokenPolicyV1

    def _current_settings_pins(self):
        c=self.config;now=datetime.now(timezone.utc)
        _require(type(self) is RawOriginalProviderSettingsV1
            and type(c) is RawOriginalProviderConfigV1 and type(self.appointment) is RawOriginalProviderAppointmentV1
            and type(self.context) is RawOriginalPhaseContextV1 and type(self.vision_policy) is RawVisionTokenPolicyV1
            and type(self.resolver) is OriginalSourceResolverV1 and type(self.observer) is RawOriginalCurrentnessConsumerV1
            and type(self.resolver.binding) is OriginalSourceBindingV1
            and type(self.observer.admission) is RawOriginalObserverAdmissionV1
            and type(self.observer.transport) is RawOriginalObserverClientV1
            and type(self.observer.transport.binding) is PurposeTLSBindingV2
            and type(self.observer.replay) is DurableNonceSequenceV2,
            'actual current protected raw settings required')
        _require(_worker_json(self.config_path,self.config_sha256,RawOriginalProviderConfigV1)==c
            and _worker_json(self.appointment_path,self.appointment_sha256,RawOriginalProviderAppointmentV1)==self.appointment
            and _worker_json(c.context.path,c.context.sha256,RawOriginalPhaseContextV1)==self.context
            and _worker_json(c.vision_policy.path,c.vision_policy.sha256,RawVisionTokenPolicyV1)==self.vision_policy,
            'raw startup metadata changed')
        # _FixedTLSClientV2 caches its SSLContext at startup. Recheck BOTH
        # protected material and actual loaded target pins before every boundary.
        raw_url=_worker_file(c.database_url.path,c.database_url.sha256,limit=8192)
        _worker_file(c.database_ca.path,c.database_ca.sha256)
        from psycopg.conninfo import conninfo_to_dict
        try:
            url=raw_url.decode().strip();params=conninfo_to_dict(url);port=int(params.get('port') or 5432)
        except Exception:
            raise PermissionError('protected original SQL target changed') from None
        _require(type(self.resolver.url) is str and self.resolver.url==url
            and params.get('host')==c.database_hostname and port==c.database_port
            and params.get('dbname')==c.database_name and params.get('user')==c.expected_session_role
            and params.get('sslmode')=='verify-full' and params.get('sslrootcert')==c.database_ca.path,
            'actual own original SQL URL/CA/target differs')
        admission=_worker_json(c.observer_admission.path,c.observer_admission.sha256,RawOriginalObserverAdmissionV1)
        _require(admission==self.observer.admission
            and digest(admission.model_dump(mode='json'))==self.observer.admission_hash==c.observer_admission.sha256,
            'protected observer admission changed')
        t=c.observer_tls
        for material in (t.ca,t.certificate,t.key):
            _worker_file(material.path,material.sha256)
        actual=self.observer.transport.binding
        _require((actual.hostname,actual.port,actual.server_uri,actual.client_uri,
            actual.ca_file,actual.certificate_file,actual.key_file,actual.timeout)==
            (t.hostname,t.port,t.server_uri,t.client_uri,Path(t.ca.path),Path(t.certificate.path),Path(t.key.path),5),
            'actual loaded original observer TLS target differs')
        # Validate exact field types and current certificate URI too; do not
        # replace the cached context or silently accept newly rotated material.
        PurposeTLSBindingV2(**actual.__dict__)
        a=self.appointment;x=self.context;b=self.resolver.binding
        _require(a.config_sha256==self.config_sha256 and a.context_sha256==c.context.sha256
            and a.issuer_actor==c.issuer_actor and a.reviewer_actor==c.reviewer_actor
            and all(getattr(a,name)==getattr(c,name) for name in
                ('population','actor_id','expected_session_role','original_allocation_hash','original_horizon'))
            and x.population==c.population and x.actor_id==c.actor_id and x.expected_session_role==c.expected_session_role
            and x.job.purpose==c.phase_purpose and x.original_allocation_hash==c.original_allocation_hash
            and x.original_horizon==c.original_horizon and x.vision_token_policy_hash==c.vision_policy.sha256
            and b.population==c.population and b.principal==c.actor_id and b.purpose==c.phase_purpose
            and b.expected_owner_role==c.expected_owner_role and b.expected_session_role==c.expected_session_role
            and b.original_allocation_hash==c.original_allocation_hash and b.original_horizon==c.original_horizon
            and b.expires_at==c.expires_at and self.observer.admission.population==c.population
            and self.observer.admission.principal_id==c.actor_id
            and self.observer.admission_hash==c.observer_admission.sha256
            and self.observer.admission.client_uri==c.observer_tls.client_uri
            and self.observer.admission.observer_uri==c.observer_tls.server_uri,
            'raw loaded startup/context/consumer pins differ')
        _require(c.valid_from<=now and self.appointment.valid_from<=now
            and now<min(c.expires_at,self.appointment.expires_at,self.context.phase_expires_at),
            'actual current protected raw settings required')
        return min(self.context.phase_expires_at,self.vision_policy.expires_at,self.appointment.expires_at)

    def current_window(self):
        horizon=self._current_settings_pins()
        window=_current_window(self.config,self.resolver,self.observer,horizon)
        self._current_settings_pins()
        _require(datetime.now(timezone.utc)<window.current_until,'raw authorization expired before return')
        return window

    def observed_window(self):
        horizon=self._current_settings_pins()
        observed=_observed_current_window(self.config,self.resolver,self.observer,horizon)
        self._current_settings_pins()
        _require(datetime.now(timezone.utc)<observed.window.current_until,'raw authorization expired before return')
        return observed

    def read_review_prompt(self,rendered):
        """Own reviewer SQL metadata plus protected exact actual reading body.

        The historical reader admission may expire. Only current independently
        appointed reviewer rights permit this read; no requester getter is used.
        """
        from oracle_brain.ingest import originals
        from oracle_brain.operating_model.original_source_authority_v1 import OriginalReviewReadingInputV1
        from oracle_brain.operating_model.original_qualification_v1 import parse_original_response_commit_v1
        from .raw_original_views_v1 import RawPDFViewsV1
        import json
        self._current_settings_pins();x=self.context;j=x.job;pointer=self.config.reading_packet
        _require(j.purpose=='source-original-review' and type(rendered) is RawPDFViewsV1
            and type(pointer) is RawPrivateFileV1 and rendered.raw_ref==j.raw_ref,
            'appointed protected review reading input required')
        before=self.resolver.original_review_reading_input_v1(j.reading_commit_hash)
        _require(type(before) is OriginalReviewReadingInputV1,'actual own SQL reader metadata required')
        raw=_worker_file(pointer.path,pointer.sha256,limit=originals.MAX_ORIGINAL_BYTES)
        from oracle_brain.operating_model.native_factory import _unique_object,_deny_constant
        body=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_deny_constant)
        _require(type(body) is dict,'exact protected reading body required')
        reader_population=RawOriginalPopulationV1.model_validate_json(canonical_bytes(body['population']))
        reading=originals.parse_original_reading_response_v1(bytes.fromhex(body['response_utf8_hex']),
            rendered=rendered,population=reader_population,principal=UUID(body['principal_id']),model=body['model_id'])
        record=parse_original_response_commit_v1(bytes.fromhex(before.reading_commit_canonical_utf8_hex),phase='reading')
        _require(raw==reading.body and reading.body_hash==pointer.sha256==record.reading_body_hash
            and reading.reading_sha256==record.reading_sha256 and record.raw_ref==j.raw_ref
            and record.view_manifest_hash==j.view_manifest_hash==rendered.view_manifest_hash
            and record.locator_map_hash==j.locator_map_hash==rendered.locator_map_hash
            and record.population_id==reader_population.population_id==before.reader_population_id
            and record.operation_registry_hash==reader_population.operation_registry_hash==before.reader_operation_registry_hash
            and reader_population.runtime_hash==before.reader_runtime_hash
            and body['principal_id']==str(before.reader_principal_id) and body['model_id']==before.reader_model_id
            and record.original_root_hash==x.population.original_root_hash
            and record.allocation_hash==x.original_allocation_hash and record.original_horizon==x.original_horizon,
            'actual committed reader metadata and protected body differ')
        prompt=originals.original_review_prompt_v1(reading,rendered=rendered,population=x.population,
            principal=x.actor_id,model=j.pricing.model)
        after=self.resolver.original_review_reading_input_v1(j.reading_commit_hash)
        _require(type(after) is OriginalReviewReadingInputV1
            and before.model_dump(exclude={'reviewer_snapshot','checked_at','valid_until'})==
                after.model_dump(exclude={'reviewer_snapshot','checked_at','valid_until'})
            and self.config.reading_packet==pointer
            and _worker_file(pointer.path,pointer.sha256,limit=originals.MAX_ORIGINAL_BYTES)==raw,
            'current reviewer or exact protected reading changed')
        self._current_settings_pins()
        _require(datetime.now(timezone.utc)<min(before.valid_until,after.valid_until),
            'actual own reviewer read expired before return')
        return prompt

    def read_billing_bounds(self):
        """Read actual appointed prospective bounds; never reserve or dispatch.

        No caller DTO, digest or route can substitute for the protected pointer.
        Legacy settings/current_window do not require this optional source input.
        """
        self._current_settings_pins()
        pointer=self.config.billing_bounds
        _require(type(pointer) is RawPrivateFileV1,'appointed protected billing pointer required')
        raw=_worker_file(pointer.path,pointer.sha256,limit=100000)
        bounds=_worker_parse(raw,RawBillingBoundsV1)
        record=RawOriginalBillingEvidenceV1(raw,bounds,pointer.sha256,digest(bounds.model_dump(mode='json')))
        _billing_matches_context(bounds,self.context,datetime.now(timezone.utc))
        self._current_settings_pins()
        _require(self.config.billing_bounds==pointer
            and _worker_file(pointer.path,pointer.sha256,limit=100000)==raw,
            'protected billing pointer or actual bytes changed before return')
        _billing_matches_context(bounds,self.context,datetime.now(timezone.utc))
        return record

    def read_pdf_views(self):
        from oracle_brain.operating_model.artifact_storage import FileBlobStore,OriginalObjectRefV1,ReservationOriginalObjectRefV1
        from .raw_original_views_v1 import render_raw_pdf_views_v1
        self.current_window()
        c=self.config;r=self.context.job.raw_ref
        capability=self.resolver.original_revision_access_v1(r.source_id,r.revision)
        reservation=UUID(capability['private_object_key'].split('/')[-1])
        ref=ReservationOriginalObjectRefV1(OriginalObjectRefV1(r.workspace_id,r.source_id,r.revision,
            r.original_sha256,r.byte_count,r.media_type,c.storage_profile_hash),reservation)
        _require(ref.key==capability['private_object_key'],'exact actual original storage key required')
        store=FileBlobStore._from_provisioned_original_root(Path(c.original_root),c.original_root_identity)
        observation=canonical_bytes({'schema_version':1,'purpose':'original-intake-byte-custody-v1',
            'reservation_id':str(reservation),'source_id':str(r.source_id),'workspace_id':str(r.workspace_id),
            'revision':r.revision,'private_object_key':ref.key,'original_sha256':r.original_sha256,
            'byte_count':r.byte_count,'storage_profile_hash':c.storage_profile_hash})
        self.current_window()
        actual=_worker_file(Path(c.original_root)/'intake-observations'/str(reservation)/'custody.json',r.custody_locator_seal_sha256)
        _require(actual==observation,'actual intake original custody differs')
        self.current_window()  # Fresh complete population immediately before original bytes.
        raw=store._read_original_bytes(ref)
        rendered=render_raw_pdf_views_v1(raw,r,expected_view_policy_hash=self.context.view_policy_hash)
        self.current_window()
        return rendered

def _window_from_observations(c,before,witness,after,phase_horizon,observer_admission_expires_at,now):
    """Single pure window rule for both retained and observed currentness paths."""
    _require(before.population==after.population==c.population
        and before.actual_principal_id==after.actual_principal_id==c.actor_id
        and before.session_role==after.session_role==c.expected_session_role
        and before.original_allocation_hash==after.original_allocation_hash==c.original_allocation_hash
        and before.original_horizon==after.original_horizon==c.original_horizon,
        'actual complete raw population changed')
    horizon=min(before.valid_until,after.valid_until,c.expires_at,c.original_horizon,phase_horizon,observer_admission_expires_at)
    current=min(horizon,witness.expires_at)
    _require(now<current,'raw authorization expired at final current boundary')
    return RawOriginalAuthorityWindowV1(current,horizon,digest(after.model_dump(mode='json')),
        digest(witness.model_dump(mode='json')))


def _current_window(c,resolver,observer,phase_horizon):
    # Preserve the retained fake-current unit seam and actual SQL/network order.
    before=resolver.original_population_current_v1(c.population.population_id)
    witness=observer.current(c.population)
    after=resolver.original_population_current_v1(c.population.population_id)
    return _window_from_observations(c,before,witness,after,phase_horizon,observer.admission.expires_at,
        datetime.now(timezone.utc))


def _observed_current_window(c,resolver,observer,phase_horizon):
    def capture(snapshot):
        _require(type(snapshot) is OriginalPopulationSnapshotV1,'actual typed original SQL snapshot required')
        raw=canonical_bytes(snapshot.model_dump(mode='json'))
        _require(OriginalPopulationSnapshotV1.model_validate_json(raw)==snapshot,
            'actual original SQL snapshot changed')
        return raw
    before=resolver.original_population_current_v1(c.population.population_id)
    before_bytes=capture(before)  # Actual snapshot captured BEFORE observer IO.
    observed=observer.observed_current(c.population)
    _require(type(observed) is RawOriginalObservedCurrentnessV1,'actual observed raw envelope required')
    after=resolver.original_population_current_v1(c.population.population_id)
    after_bytes=capture(after)
    now=datetime.now(timezone.utc)
    window=_window_from_observations(c,before,observed.witness,after,phase_horizon,
        observer.admission.expires_at,now)
    return RawOriginalObservedAuthorityWindowV1(window,before_bytes,after_bytes,observed,now)


def load_raw_original_provider_settings_v1(config_path,expected_config_sha256,*,appointment_path,
        expected_appointment_sha256,issuer_actor,reviewer_actor):
    _require(type(issuer_actor) is UUID and type(reviewer_actor) is UUID
        and all(type(h) is str and re.fullmatch(HASH,h) for h in (expected_config_sha256,expected_appointment_sha256)),
        'external raw startup pins required')
    c=_worker_json(config_path,expected_config_sha256,RawOriginalProviderConfigV1)
    a=_worker_json(appointment_path,expected_appointment_sha256,RawOriginalProviderAppointmentV1)
    now=datetime.now(timezone.utc)
    _require(a.config_sha256==expected_config_sha256 and a.context_sha256==c.context.sha256
        and a.issuer_actor==c.issuer_actor==issuer_actor and a.reviewer_actor==c.reviewer_actor==reviewer_actor
        and c.valid_from<=now<c.expires_at<=a.expires_at<=c.original_horizon and a.valid_from<=now,
        'independently appointed raw startup required')
    for name in ('population','actor_id','expected_session_role','original_allocation_hash','original_horizon'):
        _require(getattr(c,name)==getattr(a,name),'raw appointment/config differs')
    # Explicit appointment permits only own SQL URL/CA bootstrap reads.
    raw=_worker_file(c.database_url.path,c.database_url.sha256,limit=8192)
    _worker_file(c.database_ca.path,c.database_ca.sha256)
    from psycopg.conninfo import conninfo_to_dict
    try:
        url=raw.decode().strip();p=conninfo_to_dict(url);port=int(p.get('port') or 5432)
    except Exception:raise PermissionError('invalid protected raw SQL credential shape') from None
    _require(p.get('host')==c.database_hostname and port==c.database_port and p.get('dbname')==c.database_name
        and p.get('user')==c.expected_session_role and p.get('sslmode')=='verify-full'
        and p.get('sslrootcert')==c.database_ca.path,'exact own raw TLS SQL target required')
    binding=OriginalSourceBindingV1(c.population,c.actor_id,c.phase_purpose,c.expected_owner_role,
        c.expected_session_role,c.original_allocation_hash,c.original_horizon,c.expires_at)
    resolver=OriginalSourceResolverV1(url,binding=binding)
    resolver.original_population_current_v1(c.population.population_id)
    admission=_worker_json(c.observer_admission.path,c.observer_admission.sha256,RawOriginalObserverAdmissionV1)
    _require(admission.population==c.population and admission.principal_id==c.actor_id
        and admission.client_uri==c.observer_tls.client_uri and admission.observer_uri==c.observer_tls.server_uri,
        'independent raw observer subject/target differs')
    t=c.observer_tls
    for f in (t.ca,t.certificate,t.key):_worker_file(f.path,f.sha256)
    tls=PurposeTLSBindingV2(t.hostname,t.port,t.server_uri,t.client_uri,Path(t.ca.path),Path(t.certificate.path),Path(t.key.path),timeout=5)
    replay=DurableNonceSequenceV2(c.observer_spool,namespace=c.observer_namespace,
        appointment_hash=c.observer_admission.sha256,minimum_sequence=admission.minimum_sequence,
        initialization_receipt_hash=c.observer_initialization_hash)
    observer=RawOriginalCurrentnessConsumerV1(admission=admission,trusted_admission_hash=c.observer_admission.sha256,
        transport=RawOriginalObserverClientV1(tls),replay=replay)
    _current_window(c,resolver,observer,c.expires_at)
    context=_worker_json(c.context.path,c.context.sha256,RawOriginalPhaseContextV1)
    policy=_worker_json(c.vision_policy.path,c.vision_policy.sha256,RawVisionTokenPolicyV1)
    _require(context.population==c.population and context.actor_id==c.actor_id
        and context.expected_session_role==c.expected_session_role and context.job.purpose==c.phase_purpose
        and context.original_allocation_hash==c.original_allocation_hash and context.original_horizon==c.original_horizon
        and context.vision_token_policy_hash==c.vision_policy.sha256,'actual raw context/startup differs')
    settings=RawOriginalProviderSettingsV1(c,Path(config_path),expected_config_sha256,Path(appointment_path),
        expected_appointment_sha256,a,resolver,observer,context,policy)
    settings.current_window()
    return settings
