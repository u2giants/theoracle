"""Explicit protected raw composition; no issuer, reviewer grant or SourceRef.

Only existing settings/broker owners supply authority. Original wire is retained
before inspection; failed/uncertain outcomes never redispatch or qualify source.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json,os
from pathlib import Path
from uuid import UUID

from oracle_brain.provider_policy import authorize
from oracle_brain.ingest import originals
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import NativeBrokerEgress,RawOriginalDispatchJobV1,_AuthorizedNative,verify_ledger,_unique_object,_deny_constant
from oracle_brain.operating_model.native_provider import amount
from oracle_brain.operating_model.provider_adapter import Budget,AdmittedAllocationLimitV2
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import compare_raw_endpoint_quote_v1
from oracle_brain.operating_model.raw_original_native_provider_v1 import open_raw_original_native_v1
from oracle_brain.operating_model.raw_original_paid_response_v1 import RawOriginalPaidResponseCommitV1
from .raw_original_settings_v1 import RawOriginalProviderSettingsV1,RawOriginalObservedAuthorityWindowV1
from .raw_original_request_v1 import validate_raw_original_request_v1
from .purpose_journey_v2 import _require,_worker_file


class RawOriginalOutcomeUnknown(RuntimeError):
    """A paid effect or custody/settlement may exist. No automatic retry."""


def _json(raw):
    _require(type(raw) is bytes and 0<len(raw)<=16*1024*1024,'bounded actual original wire required')
    return json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_deny_constant,parse_float=Decimal)


def _money(value):
    _require(type(value) in (int,Decimal),'exact numeric actual cost required')
    return amount(value)


def _usage(wire,job):
    """Conservative exact usage; unknown route remains unknown liability.

    Official shape: https://github.com/OpenRouterTeam/docs/blob/main/api_reference/overview.mdx
    NativeOpenRouter.send already adds upstream cost for is_byok=true. Never
    add it again here. This guard compares observations, not catalogue authority.
    """
    u=wire.get('usage');q=job.pricing
    _require(type(u) is dict and set(u)<= {'prompt_tokens','completion_tokens','total_tokens','cost','is_byok',
        'cost_details','prompt_tokens_details','completion_tokens_details','server_tool_use','server_tool_use_details'},
        'closed actual usage required')
    _require(type(u.get('is_byok')) is bool and u['is_byok']==q.is_byok,'actual billing route unknown or changed')
    for key,limit in (('prompt_tokens',job.input_tokens_upper_bound),('completion_tokens',q.max_output_tokens),
            ('total_tokens',job.input_tokens_upper_bound+q.max_output_tokens)):
        _require(type(u.get(key)) is int and 0<=u[key]<=limit,'exact bounded actual token usage required')
    _require(u['total_tokens']==u['prompt_tokens']+u['completion_tokens'],'actual token totals differ')
    _money(u.get('cost'))
    for key,allowed,parent in (('prompt_tokens_details',{'cached_tokens','cache_write_tokens','audio_tokens','video_tokens'},u['prompt_tokens']),
            ('completion_tokens_details',{'reasoning_tokens','audio_tokens','image_tokens'},u['completion_tokens'])):
        if key not in u:continue
        d=u[key];_require(type(d) is dict and set(d)<=allowed,'closed token details required')
        for name,value in d.items():
            _require(type(value) is int and 0<=value<=parent,'strict actual token detail required')
            if name in {'audio_tokens','video_tokens','image_tokens'}:_require(value==0,'unrequested media usage')
    for key in ('server_tool_use','server_tool_use_details'):
        if key in u and u[key] is not None:
            _require(type(u[key]) is dict and not u[key],'unrequested or malformed server tools')
    d=u.get('cost_details',{})
    _require(type(d) is dict and set(d)<= {'upstream_inference_cost','upstream_inference_prompt_cost',
        'upstream_inference_completions_cost','server_tool_cost'},'closed actual cost details required')
    if d.get('server_tool_cost') is not None:
        _require(_money(d['server_tool_cost'])==0,'unrequested server tool cost')
    for key in ('upstream_inference_prompt_cost','upstream_inference_completions_cost'):
        if key in d:_money(d[key])
    upstream=d.get('upstream_inference_cost')
    if q.is_byok:
        observed=_money(upstream)
        # Compare against all originally admitted input/output/complete-view
        # bounds. Financial settlement retains any observed overrun unchanged.
        bound=(Decimal(job.input_tokens_upper_bound)*q.upstream_input_per_million_usd/Decimal(1000000)
            +Decimal(q.max_output_tokens)*q.upstream_output_per_million_usd/Decimal(1000000)
            +Decimal(q.view_count)*q.upstream_per_image_fee_usd+q.upstream_per_request_fee_usd)
        _require(observed<=bound,'actual upstream cost exceeds prospective admitted bounds')
        if {'upstream_inference_prompt_cost','upstream_inference_completions_cost'}<=set(d):
            _require(observed==_money(d['upstream_inference_prompt_cost'])+_money(d['upstream_inference_completions_cost']),
                'actual upstream cost components differ')
    else:_require(upstream is None or _money(upstream)==0,'unexpected upstream liability on shared-only route')


def _content(wire,job):
    if (type(wire) is not dict or 'error' in wire or wire.get('model')!=job.pricing.model or wire.get('object')!='chat.completion'
            or type(wire.get('id')) is not str or not wire['id'] or len(wire['id'])>1000
            or type(wire.get('created')) is not int or wire['created']<0
            or type(wire.get('choices')) is not list or len(wire['choices'])!=1):
        raise ValueError('exact actual chat/model identity required')
    c=wire['choices'][0]
    if (type(c) is not dict or c.get('finish_reason')!='stop'
            or set(c)-{'index','finish_reason','native_finish_reason','message','logprobs'}
            or ('index' in c and (type(c['index']) is not int or c['index']!=0))):
        raise ValueError('one complete stopped assistant response required')
    m=c.get('message')
    if (type(m) is not dict or m.get('role')!='assistant' or type(m.get('content')) is not str
            or not m['content'] or set(m)-{'role','content','reasoning','reasoning_details','refusal'}
            or m.get('refusal') is not None):
        raise ValueError('exact non-refused assistant text required')
    return m['content'].encode('utf-8')


@dataclass(frozen=True)
class ObservedRawOriginalPaidResponseV1:
    """Actual factory output; direct construction authenticates no operation."""
    content_utf8:bytes
    commit_bytes:bytes
    evidence_manifest_bytes:bytes

    @property
    def commit(self):return RawOriginalPaidResponseCommitV1.model_validate_json(self.commit_bytes)

    def __post_init__(self):
        _require(all(type(v) is bytes and v for v in (self.content_utf8,self.commit_bytes,self.evidence_manifest_bytes)),
            'immutable actual paid output required')
        c=self.commit
        _require(canonical_bytes(c.model_dump(mode='json'))==self.commit_bytes
            and hashlib.sha256(self.content_utf8).hexdigest()==c.model_content_hash,
            'actual paid output content differs')
        body=_json(self.evidence_manifest_bytes)
        _require(body['paid_commit_sha256']==hashlib.sha256(self.commit_bytes).hexdigest(),
            'actual evidence manifest differs')


class ProtectedRawOriginalFactoryV1:
    def __init__(self,settings,broker):
        _require(type(settings) is RawOriginalProviderSettingsV1 and type(broker) is NativeBrokerEgress,
            'exact existing protected raw settings and broker required')
        self.settings=settings;self.broker=broker

    def _job(self):
        s=self.settings;b=self.broker;s._current_settings_pins()
        x=s.context;j=RawOriginalDispatchJobV1.model_validate_json(x.job.model_dump_json())
        current=b._resolve(j.dispatch_id)
        _require(type(current) is RawOriginalDispatchJobV1
            and canonical_bytes(current.model_dump(mode='json'))==canonical_bytes(j.model_dump(mode='json')),
            'actual canonical registered raw job differs')
        seal=digest(j.model_dump(mode='json'))
        _require(b._authorize(j) is True and digest(j.model_dump(mode='json'))==seal,'current immutable raw job authority denied')
        authorize(j.processing_request,list(j.approvals))
        q=j.pricing;r=j.processing_request;a=b._allocation
        _require(type(a) is AdmittedAllocationLimitV2 and a.batch_id==j.batch_id
            and a.allocation_hash==x.original_allocation_hash and a.expires_at<=x.original_horizon
            and datetime.now(timezone.utc)<a.expires_at
            and hashlib.sha256(b._key.encode()).hexdigest()==b._key_fingerprint==q.key_fingerprint
            and q.account==r.account=='key-sha256:'+b._key_fingerprint
            and q.ledger_registry_hash==b._registry_hash and q.terms_hash==r.terms_hash
            and r.provider=='openrouter' and r.endpoint=='https://openrouter.ai/api/v1'
            and r.purpose==j.purpose and r.fallback is False,
            'actual existing billing/key/allocation/processing binding differs')
        if b._registry.transport=='owned-synthetic-loopback':
            _require(r.data_classes<=frozenset({'synthetic'}),'synthetic billing cannot process company data')
        return j

    def _path(self,job,suffix):return self.broker._receipts/(str(job.dispatch_id)+suffix)

    def _persist(self,job,suffix,raw):
        root=self.broker._receipts
        _require(type(raw) is bytes and len(raw)<=32*1024*1024
            and root.is_absolute() and root.resolve()==root and root.is_dir()
            and root.stat().st_uid==os.getuid() and not root.stat().st_mode&0o077,
            'existing private native receipt owner required')
        path=self._path(job,suffix)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        _require(_worker_file(path,hashlib.sha256(raw).hexdigest(),limit=32*1024*1024)==raw,'actual private evidence readback differs')
        return hashlib.sha256(raw).hexdigest()

    def _compare(self,job,native,models,endpoints):
        current=self._job();_require(current==job,'actual registered raw job changed')
        billing=self.settings.read_billing_bounds()
        return compare_raw_endpoint_quote_v1(models.wire,endpoints.wire,quote=job.pricing,
            expected_quote_sha256=self.settings.context.pricing_quote_hash,billing_bounds=billing.bounds,
            expected_billing_evidence_sha256=billing.canonical_record_sha256,
            current_account='key-sha256:'+native.key_fingerprint,current_key_fingerprint=native.key_fingerprint,
            current_ledger_registry_hash=self.broker._registry_hash,current_terms_hash=job.processing_request.terms_hash,
            current_register_hash=current.register_hash,models_observed_at=models.observed_at,
            endpoints_observed_at=endpoints.observed_at,now=datetime.now(timezone.utc))

    def _settlement(self,job,rid,content,actual):
        # Existing ledger only, own short read after actual Budget.finish commit.
        import psycopg
        with psycopg.connect(self.broker._url,connect_timeout=5) as c:
            c.execute('SET TRANSACTION READ ONLY')
            row=c.execute('''SELECT r.workspace_id,r.artifact_id,r.batch_id,r.purpose,r.attempt,r.pricing_hash,
                s.actual_usd,s.status,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r
                JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.reservation_id=%s''',(rid,)).fetchone()
        _require(row==(job.workspace_id,job.artifact_id,job.batch_id,job.purpose,job.attempt,
            digest(job.pricing.model_dump(mode='json')),actual,'completed',hashlib.sha256(content).hexdigest(),None),
            'actual committed central settlement unavailable or differs')

    def execute(self):
        job=self._job();s=self.settings;b=self.broker
        _require(not any(self._path(job,suffix).exists() for suffix in ('.wire','.wire.json','.json','.raw-paid.json','.raw-evidence.json')),
            'existing dispatch custody forbids replay')
        billing=s.read_billing_bounds()  # Missing pointer refuses before metadata/reserve.
        rendered=s.read_pdf_views()
        if job.purpose=='source-original-reading':prompt=originals._prompt(rendered.views)
        else:prompt=s.read_review_prompt(rendered)  # Own current reviewer SQL + protected body, never caller input.
        validate_raw_original_request_v1(job,rendered,prompt,expected_quote_sha256=s.context.pricing_quote_hash,
            now=datetime.now(timezone.utc))
        identity=verify_ledger(b._url,b._registry,trusted_registry_hash=b._registry_hash,
            key_fingerprint=b._key_fingerprint,now=datetime.now(timezone.utc))
        provider=None;actual_wire=None;validation_failed=False
        def before_post():
            _require(self._job()==job,'raw job changed before private POST')
            s.observed_window();self._compare(job,native,models,endpoints)
            current_prompt=(originals._prompt(rendered.views) if job.purpose=='source-original-reading'
                else s.read_review_prompt(rendered))
            validate_raw_original_request_v1(job,rendered,current_prompt,expected_quote_sha256=s.context.pricing_quote_hash,
                now=datetime.now(timezone.utc))
        def capture(raw,*,complete):
            nonlocal actual_wire
            # Must precede JSON/currentness or any post-paid refusal.
            b._capture_wire(job,raw,provider.last_reservation_id,complete=complete)
            actual_wire=raw
            if complete:_json(raw)  # Duplicate/nonfinite JSON must not be silently normalized.
        native=_AuthorizedNative(b._key,coverage_receipt=b._coverage,trusted_coverage_hash=b._coverage_hash,
            ledger_identity_hash=identity,paid_wire_receiver=capture,before_private_dispatch=before_post)
        models=native.metadata_wire_v1('/models')
        endpoints=native.metadata_wire_v1('/models/'+job.pricing.model+'/endpoints')
        comparison=self._compare(job,native,models,endpoints)
        # Retained under SAME native receipt directory; original metadata bytes,
        # not decoded substitutions. These create no registry or grant.
        for suffix,raw in (('.raw-models.wire',models.wire),('.raw-endpoints.wire',endpoints.wire),
                ('.raw-billing.json',billing.raw_bytes),('.raw-comparison.json',comparison)):
            self._persist(job,suffix,raw)
        budget=Budget(b._url,ledger_identity_hash=identity,admitted_allocation=b._allocation)
        provider=open_raw_original_native_v1(quote=job.pricing,expected_quote_sha256=s.context.pricing_quote_hash,
            budget=budget,sender=native.send,remaining_daily_allowance=native.allowance,admitted_register_hash=job.register_hash,
            processing_request=job.processing_request,vision_policy=s.vision_policy,
            expected_vision_policy_sha256=s.context.vision_token_policy_hash)
        def validate(content):
            nonlocal validation_failed
            try:
                _usage(_json(actual_wire),job)
                s.observed_window();_require(self._job()==job,'raw validation authority changed')
                s.read_billing_bounds()
            except Exception:
                # Currentness/route parse failures are authority uncertainty,
                # even when their underlying exception happens to be ValueError.
                validation_failed=True
                raise PermissionError('actual raw route or authority validation unavailable') from None
            try:
                observed=_content(_json(actual_wire),job)
                if type(content) is not str or content.encode()!=observed:raise ValueError('actual returned content differs')
                b._validate_response(job,content)
            except Exception:
                validation_failed=True
                raise
        try:
            response,actual,_=provider.extract_raw(workspace_id=job.workspace_id,artifact_id=job.artifact_id,
                batch_id=job.batch_id,purpose=job.purpose,attempt=job.attempt,messages=job.request['messages'],
                input_tokens_upper_bound=job.input_tokens_upper_bound,now=datetime.now(timezone.utc),
                response_validator=validate,view_dimensions=tuple((v.width,v.height,len(v.png)) for v in rendered.views))
            b._record(job,getattr(native,'last_response_text',None),provider.last_reservation_id,failed=validation_failed)
            if validation_failed:raise ValueError('trusted raw output rejected; retained receipt requires diagnosis')
            content=response.encode();rid=provider.last_reservation_id
            self._settlement(job,rid,content,actual)
            wire=_worker_file(self._path(job,'.wire'),limit=16*1024*1024)
            meta=_json(_worker_file(self._path(job,'.wire.json')))
            receipt_raw=_worker_file(self._path(job,'.json'));receipt=_json(receipt_raw)
            _require(wire==actual_wire and meta==receipt['wire_custody'] and meta['complete'] is True
                and meta['truncated'] is False and receipt['failed'] is False
                and meta['reservation_id']==receipt['reservation_id']==str(rid)
                and meta['job_hash']==receipt['job_hash']==digest(job.model_dump(mode='json'))
                and meta['request_hash']==receipt['request_hash']==job.request_hash
                and meta['permission_hash']==receipt['permission_hash']==job.permission_hash
                and meta['key_fingerprint']==receipt['key_fingerprint']==b._key_fingerprint
                and meta['ledger_identity_hash']==receipt['ledger_identity_hash']==identity
                and receipt['pricing_hash']==s.context.pricing_quote_hash
                and hashlib.sha256(wire).hexdigest()==meta['raw_sha256']
                and len(wire)==meta['captured_bytes'] and _content(_json(wire),job)==content,
                'actual native wire/receipt custody differs')
            _usage(_json(wire),job)
            current=s.observed_window();_require(type(current) is RawOriginalObservedAuthorityWindowV1,'actual signed window required')
            _require(self._job()==job,'raw paid result authority changed')
            self._compare(job,native,models,endpoints)
            if job.purpose=='source-original-review':
                _require(s.read_review_prompt(rendered)==prompt,'actual current review input changed after settlement')
            observed=current.observer_evidence
            evidence={}
            for suffix,raw in (('.raw-before-sql.json',current.before_snapshot_bytes),
                    ('.raw-after-sql.json',current.after_snapshot_bytes),('.raw-observer-envelope',observed.raw_envelope),
                    ('.raw-observer-witness.json',observed.witness_bytes)):
                evidence[suffix]=self._persist(job,suffix,raw)
            now=datetime.now(timezone.utc);x=s.context;p=x.population;q=job.pricing
            _require(now<current.window.current_until,'actual paid evidence expired before commit')
            commit=RawOriginalPaidResponseCommitV1(purpose=job.purpose,dispatch_id=job.dispatch_id,raw_ref=job.raw_ref,
                native_job_hash=digest(job.model_dump(mode='json')),context_hash=digest(x.model_dump(mode='json')),
                request_hash=job.request_hash,permission_hash=job.permission_hash,population_id=p.population_id,
                operation_registry_hash=p.operation_registry_hash,original_root_hash=p.original_root_hash,
                population_digest=p.population_digest,source_registry_hash=p.source_registry_hash,
                allocation_hash=x.original_allocation_hash,view_manifest_hash=job.view_manifest_hash,
                locator_map_hash=job.locator_map_hash,pricing_quote_hash=x.pricing_quote_hash,reservation_id=rid,
                native_custody_receipt_hash=hashlib.sha256(receipt_raw).hexdigest(),raw_wire_hash=hashlib.sha256(wire).hexdigest(),
                model_content_hash=hashlib.sha256(content).hexdigest(),model_id=q.model,
                current_sql_receipt_hash=current.window.sql_receipt_hash,observer_witness_hash=current.window.observer_witness_hash,
                native_failed=False,wire_complete=True,committed_at=now,original_horizon=x.original_horizon)
            commit_raw=canonical_bytes(commit.model_dump(mode='json'))
            manifest=canonical_bytes({'schema_version':1,'purpose':'actual-raw-original-evidence-v1',
                'dispatch_id':str(job.dispatch_id),'paid_commit_sha256':hashlib.sha256(commit_raw).hexdigest(),
                'files':evidence,'observer_admission':observed.admission.model_dump(mode='json'),
                'observer_admission_hash':observed.trusted_admission_hash,'challenge':observed.challenge,
                'previous_sequence':observed.previous_sequence,'started_at':observed.started_at.isoformat(),
                'observed_at':observed.observed_at.isoformat(),'elapsed_seconds':observed.elapsed_seconds,
                'current_until':current.window.current_until.isoformat(),
                'models_wire_sha256':models.wire_sha256,'endpoints_wire_sha256':endpoints.wire_sha256,
                'models_observation':{'path':models.path,'started_at':models.started_at.isoformat(),
                    'observed_at':models.observed_at.isoformat(),'elapsed_seconds':models.elapsed_seconds},
                'endpoints_observation':{'path':endpoints.path,'started_at':endpoints.started_at.isoformat(),
                    'observed_at':endpoints.observed_at.isoformat(),'elapsed_seconds':endpoints.elapsed_seconds},
                'billing_original_file_sha256':billing.original_file_sha256,
                'billing_canonical_record_sha256':billing.canonical_record_sha256})
            self._persist(job,'.raw-paid.json',commit_raw);self._persist(job,'.raw-evidence.json',manifest)
            # Durable bytes may exist even if final authority/acknowledgement is
            # lost. Recheck actual original/job rights after filesystem work;
            # never return an expired signed-window packet or redispatch it.
            s.current_window();s.read_billing_bounds()
            _require(self._job()==job and datetime.now(timezone.utc)<current.window.current_until,
                'actual paid authority changed before return')
            return ObservedRawOriginalPaidResponseV1(content,commit_raw,manifest)
        except Exception:
            if type(provider.last_reservation_id) is UUID and not self._path(job,'.json').exists():
                b._record(job,getattr(native,'last_response_text',None),provider.last_reservation_id,failed=True)
            raise RawOriginalOutcomeUnknown('raw paid outcome retained or uncertain; no automatic retry') from None
