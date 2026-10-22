"""Actual invented PDFs/PNG, TLS signatures, native wire and central Budget API.

Recording tests are explicit local SQL seams, not authenticated SQL authority.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import copy,hashlib,json
import pytest
from oracle_brain.hosting import protected_raw_original_factory_v1 as m
from oracle_brain.hosting import raw_original_settings_v1 as settings_module
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import LedgerRegistry,NativeBrokerEgress,RawOriginalDispatchJobV1
from oracle_brain.operating_model.provider_adapter import Budget,AdmittedAllocationLimitV2
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import raw_endpoint_safety_inventory_v1,raw_worst_case_policy_hash_v1
from oracle_brain.hosting.raw_original_views_v1 import render_raw_pdf_views_v1,raw_pdf_view_policy_hash_v1,raw_pdf_multimodal_messages_v1
from test_raw_original_observer_v1 import observed_exchange,bound_tls,certificates
from test_raw_original_settings_v1 import configured_window_settings,write,appointment
from test_raw_endpoint_inventory_v1 import catalogue
from test_raw_original_views_v1 import pdf_fixture

REAL_RESERVE=Budget.reserve;REAL_FINISH=Budget.finish
REAL_SETTLEMENT=m.ProtectedRawOriginalFactoryV1._settlement;REAL_VERIFY_LEDGER=m.verify_ledger

KEY='invented-protected-raw-key';FP=hashlib.sha256(KEY.encode()).hexdigest();COVERAGE='e'*64

@pytest.fixture
def factory_case(bound_tls,tmp_path,monkeypatch):
    # Cache actual original bytes BEFORE the retained observer fixture constructs
    # its complete population, so physical views and signed population agree.
    import test_raw_original_views_v1
    data,ref=pdf_fixture();monkeypatch.setattr(test_raw_original_views_v1,'pdf_fixture',lambda:(data,ref))
    generator=observed_exchange.__wrapped__(bound_tls,tmp_path)
    consumer,observer_state,_=next(generator)
    try:
        s,sql_reads=configured_window_settings(consumer,tmp_path,monkeypatch)
        rendered=render_raw_pdf_views_v1(data,s.context.population.raw_refs[0],expected_view_policy_hash=raw_pdf_view_policy_hash_v1())
        models,endpoints=catalogue();mw=canonical_bytes(models);ew=canonical_bytes(endpoints)
        inv=raw_endpoint_safety_inventory_v1(mw,ew,model=s.context.job.pricing.model)
        now=datetime.now(timezone.utc)
        registry=LedgerRegistry(key_fingerprint=FP,host='localhost',port=5432,database='oracle_operating_model_test_'+'a'*32,
            role='invented_billing',cluster_identifier='123',namespace_hash='f'*64,transport='owned-synthetic-loopback',
            transport_receipt_hash='d'*64,dedicated_single_key=True,issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=s.config.expires_at)
        ledger_hash=digest(registry.model_dump(mode='json'))
        policy=s.vision_policy.model_copy(update={'max_image_bytes':max(len(v.png) for v in rendered.views)+1,
            'max_total_image_bytes':sum(len(v.png) for v in rendered.views)+1,'max_width':10000,'max_height':10000})
        ph=write(Path(s.config.vision_policy.path),policy)
        prompt=m.originals._prompt(rendered.views);j=s.context.job
        request=copy.deepcopy(j.request);request['messages']=raw_pdf_multimodal_messages_v1(rendered,prompt)
        rh=digest(request)
        processing=j.processing_request.model_copy(update={'account':'key-sha256:'+FP})
        approvals=tuple(a.model_copy(update={'account':processing.account}) for a in j.approvals)
        q=j.pricing.model_copy(update={'account':processing.account,'key_fingerprint':FP,'ledger_registry_hash':ledger_hash,
            'terms_hash':processing.terms_hash,'pricing_policy_sha256':raw_worst_case_policy_hash_v1(),
            'catalogue_sha256':inv.catalogue_sha256,'model_capability_sha256':inv.model_capability_sha256,
            'input_per_million_usd':Decimal(4),'input_cache_write_per_million_usd':Decimal(3),
            'output_per_million_usd':Decimal(2),'text_input_tokens_upper_bound':20000,
            'vision_input_tokens_upper_bound':len(rendered.views)*policy.tokens_per_complete_view_upper_bound,
            'request_hash':rh,'view_manifest_hash':rendered.view_manifest_hash,'vision_token_policy_sha256':ph,
            'view_count':len(rendered.views),'total_image_bytes':sum(len(v.png) for v in rendered.views),
            'largest_image_bytes':max(len(v.png) for v in rendered.views),
            'model_max_image_bytes':policy.max_image_bytes,'model_max_images':policy.max_images})
        j=RawOriginalDispatchJobV1.model_validate(j.model_dump(mode='python')|{'raw_ref':rendered.raw_ref,
            'request':request,'request_hash':rh,'pricing':q,'processing_request':processing,'approvals':approvals,
            'view_manifest_hash':rendered.view_manifest_hash,'locator_map_hash':rendered.locator_map_hash,
            'input_tokens_upper_bound':q.text_input_tokens_upper_bound+q.vision_input_tokens_upper_bound})
        x=type(s.context).model_validate(s.context.model_dump(mode='python')|{'job':j,'pricing_quote_hash':digest(q.model_dump(mode='json')),
            'vision_token_policy_hash':ph,'view_policy_hash':rendered.view_policy_hash})
        xh=write(Path(s.config.context.path),x)
        bounds=settings_module.RawBillingBoundsV1
        b=bounds(model=q.model,route='byok',account=q.account,key_fingerprint=FP,ledger_registry_hash=ledger_hash,
            terms_hash=q.terms_hash,provider_evidence_sha256='7'*64,valid_from=q.valid_from,expires_at=q.expires_at,
            **{k:getattr(q,k) for k in ('upstream_input_per_million_usd','upstream_output_per_million_usd',
                'upstream_per_image_fee_usd','upstream_per_request_fee_usd')})
        bp=tmp_path/'factory-billing.json';bh=write(bp,b)
        c=type(s.config).model_validate(s.config.model_dump(mode='python')|{'context':{'path':str(s.config.context.path),'sha256':xh},
            'vision_policy':{'path':str(s.config.vision_policy.path),'sha256':ph},'billing_bounds':{'path':str(bp),'sha256':bh}})
        ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
        s=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah,context=x,vision_policy=policy)
        monkeypatch.setattr(settings_module.RawOriginalProviderSettingsV1,'read_pdf_views',lambda self:rendered)
        receipts=tmp_path/'factory-native-receipts';receipts.mkdir(mode=0o700)
        state={'paid':0,'requests':[],'reservations':[],'finishes':[],'job':j,'authorized':True,
            'wire':{'id':'invented-completion','created':1,'object':'chat.completion','model':q.model,
                'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{"actual":"reader bytes"}'}}],
                'usage':{'prompt_tokens':100,'completion_tokens':5,'total_tokens':105,'is_byok':True,
                    'cost':0.001,'cost_details':{'upstream_inference_cost':0.002}}},'wire_hook':lambda:None}
        allocation=AdmittedAllocationLimitV2(batch_id=j.batch_id,allocation_hash=x.original_allocation_hash,
            original_receipt_hash='3'*64,ceiling_usd=Decimal(5),expires_at=s.config.expires_at)
        def coverage():
            at=datetime.now(timezone.utc)-timedelta(seconds=1)
            return VerifiedKeyCoverage(admission_hash=COVERAGE,key_fingerprint=FP,ledger_identity_hash=ledger_hash,
                observed_at=at,expires_at=at+timedelta(seconds=10))
        broker=NativeBrokerEgress(api_key=KEY,ledger_url='invented-no-connection',registry=registry,
            trusted_registry_hash=ledger_hash,coverage_receipt=coverage,trusted_coverage_hash=COVERAGE,
            resolve_job=lambda _:state['job'],authorize_current_job=lambda _:state['authorized'],
            validate_response=lambda job,content:None,private_receipts=receipts,admitted_allocation=allocation)
        monkeypatch.setattr(m,'verify_ledger',lambda *args,**kwargs:ledger_hash)
        def reserve(self,**kwargs):
            assert type(self) is Budget and self.url==broker._url and self.admitted_allocation is allocation
            assert not state['reservations'];rid=uuid4();state['reservations'].append((rid,kwargs));return rid
        def finish(self,rid,**kwargs):state['finishes'].append((rid,kwargs))
        monkeypatch.setattr(Budget,'reserve',reserve);monkeypatch.setattr(Budget,'finish',finish)
        def settlement(self,job,rid,content,actual):
            assert state['finishes']==[(rid,dict(actual_usd=actual,failed=False,response_hash=hashlib.sha256(content).hexdigest(),failure_kind=None))]
        monkeypatch.setattr(m.ProtectedRawOriginalFactoryV1,'_settlement',settlement)
        class Response:
            status=200
            def __init__(self,path,raw):self.path=path;self.raw=raw
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return 'https://openrouter.ai/api/v1'+self.path
            def getheader(self,k):return str(len(self.raw)) if k=='Content-Length' else None
            def read(self,n):return self.raw[:n]
        class Opener:
            def open(self,request,timeout):
                path=request.full_url.removeprefix('https://openrouter.ai/api/v1');state['requests'].append(path)
                assert request.get_header('Authorization')=='Bearer '+KEY
                if path=='/models':return Response(path,state.get('models_wire',mw))
                if path.endswith('/endpoints'):return Response(path,state.get('endpoints_wire',ew))
                if path=='/key':return Response(path,canonical_bytes({'data':{'is_free_tier':False,'usage_daily':0,
                    'byok_usage_daily':0,'usage_monthly':0,'byok_usage_monthly':0,'limit':None}}))
                assert path=='/chat/completions';state['paid']+=1;state['wire_hook']()
                raw=state.get('raw_wire',canonical_bytes(state['wire']))
                if state.get('http_error'):
                    import io,urllib.error
                    raise urllib.error.HTTPError(request.full_url,402,'invented quota',{},io.BytesIO(raw))
                if state.get('partial'):
                    import http.client
                    class Partial(Response):
                        def read(self,n):raise http.client.IncompleteRead(self.raw[:20],len(self.raw))
                    return Partial(path,raw)
                return Response(path,raw)
        from oracle_brain.operating_model import native_provider
        monkeypatch.setattr(native_provider.urllib.request,'build_opener',lambda *args:Opener())
        yield m.ProtectedRawOriginalFactoryV1(s,broker),state,observer_state,rendered
    finally:
        try:next(generator)
        except StopIteration:pass


def test_factory_actual_wire_settles_once_and_preserves_signed_window_evidence(factory_case):
    factory,state,observer,_=factory_case
    result=factory.execute();j=factory.settings.context.job
    assert result.content_utf8==b'{"actual":"reader bytes"}' and result.commit.model_content_hash==hashlib.sha256(result.content_utf8).hexdigest()
    assert state['paid']==len(state['reservations'])==len(state['finishes'])==1
    # Native sender adds BYOK upstream ONCE: .001+.002, never .005.
    assert state['finishes'][0][1]['actual_usd']==Decimal('.003')
    root=factory.broker._receipts;prefix=str(j.dispatch_id)
    assert (root/(prefix+'.wire')).read_bytes()==canonical_bytes(state['wire'])
    assert (root/(prefix+'.raw-observer-envelope')).read_bytes()==observer['raw'][-2]  # Durable packet, followed by final current-only check.
    assert hashlib.sha256((root/(prefix+'.raw-observer-witness.json')).read_bytes()).hexdigest()==result.commit.observer_witness_hash
    assert json.loads((root/(prefix+'.raw-evidence.json')).read_bytes())['paid_commit_sha256']==hashlib.sha256(result.commit_bytes).hexdigest()
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==1


@pytest.mark.parametrize('damage',['route_missing','route_bool','route_changed','upstream_missing','upstream_excess','token_bool','token_sum','server_tool','length','assistant','model','duplicate','nonfinite','authority','string_cost','bool_fee'])
def test_paid_refusals_preserve_wire_settlement_and_never_emit_commit_or_retry(factory_case,damage):
    factory,state,_,_=factory_case;w=state['wire'];u=w['usage']
    if damage=='route_missing':del u['is_byok']
    elif damage=='route_bool':u['is_byok']=1
    elif damage=='route_changed':u['is_byok']=False
    elif damage=='upstream_missing':u['cost_details']={}
    elif damage=='upstream_excess':u['cost_details']['upstream_inference_cost']=2
    elif damage=='string_cost':u['cost']='0.001'
    elif damage=='bool_fee':u['cost_details']['server_tool_cost']=False
    elif damage=='token_bool':u['prompt_tokens']=True
    elif damage=='token_sum':u['total_tokens']+=1
    elif damage=='server_tool':u['server_tool_use']={'web_search_requests':1}
    elif damage=='length':w['choices'][0]['finish_reason']='length'
    elif damage=='assistant':w['choices'][0]['message']['role']='tool'
    elif damage=='model':w['model']='openai/gpt-6-astra'
    elif damage=='duplicate':state['raw_wire']=canonical_bytes(w)[:-1]+b',"usage":{}}'
    elif damage=='nonfinite':state['raw_wire']=b'{"usage":NaN}'
    else:state['wire_hook']=lambda:state.update(authorized=False)
    with pytest.raises(m.RawOriginalOutcomeUnknown):factory.execute()
    assert state['paid']==len(state['reservations'])==len(state['finishes'])==1
    assert factory._path(factory.settings.context.job,'.wire').exists()
    assert factory._path(factory.settings.context.job,'.json').exists()
    assert not factory._path(factory.settings.context.job,'.raw-paid.json').exists()
    finish=state['finishes'][0][1]
    if damage in {'length','assistant'}:
        assert finish['failure_kind']=='invalid_output' and finish['actual_usd']==Decimal('.003')
    else:
        assert finish['failure_kind']=='transport_failure' and finish['response_hash'] is None
        assert finish['actual_usd']>=state['reservations'][0][1]['maximum']
    if damage=='upstream_excess':assert finish['actual_usd']==Decimal('2.001')
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==1


@pytest.mark.parametrize('damage',['missing_billing','job_changed','authority','allocation','quote_key'])
def test_preflight_denials_have_zero_reservations_and_paid_calls(factory_case,damage):
    factory,state,_,_=factory_case
    if damage=='missing_billing':
        s=factory.settings;c=s.config.model_copy(update={'billing_bounds':None})
        ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
        factory.settings=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah)
    elif damage=='job_changed':state['job']=state['job'].model_copy(update={'permission_hash':'0'*64})
    elif damage=='authority':state['authorized']=False
    elif damage=='allocation':factory.broker._allocation=None
    else:factory.broker._key_fingerprint='0'*64
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==0 and state['reservations']==[] and state['finishes']==[]


@pytest.fixture
def review_factory_case(factory_case,tmp_path,monkeypatch):
    """Protected canonical packet + explicit typed historical SQL getter seam.

    Actual SQL018 admission/readback has its own owned-DB tests. This fixture
    cannot authenticate a production reader or grant a reviewer appointment.
    """
    from oracle_brain.operating_model.original_qualification_v1 import OriginalReadingCommitV1
    from oracle_brain.operating_model.original_source_authority_v1 import OriginalReviewReadingInputV1
    from test_raw_original_settings_v1 import snapshot_for
    factory,state,observer,rendered=factory_case;s=factory.settings
    initial_bounds=s.read_billing_bounds().bounds
    reader=uuid4();reader_population=s.context.population.model_copy(update={'population_id':uuid4()})
    response=canonical_bytes({'pages':[{'page_number':1,'text':'Order -> Check -> Ship'}],'complete':True})
    parsed=m.originals.parse_original_reading_response_v1(response,rendered=rendered,population=reader_population,
        principal=reader,model='openai/gpt-6.1-sol')
    at=datetime.now(timezone.utc)
    rc=OriginalReadingCommitV1(raw_ref=rendered.raw_ref,population_id=reader_population.population_id,
        operation_registry_hash=reader_population.operation_registry_hash,original_root_hash=reader_population.original_root_hash,
        allocation_hash=s.context.original_allocation_hash,population_hash=reader_population.population_digest,
        source_registry_hash=reader_population.source_registry_hash,context_hash='1'*64,
        view_manifest_hash=rendered.view_manifest_hash,locator_map_hash=rendered.locator_map_hash,
        reading_sha256=parsed.reading_sha256,parser_id='2'*64,committed_at=at,original_horizon=s.context.original_horizon,
        native_dispatch_id=uuid4(),native_job_hash='3'*64,request_hash='4'*64,raw_wire_hash='5'*64,
        model_content_hash=hashlib.sha256(response).hexdigest(),native_custody_receipt_hash='6'*64,
        authorized_phase_commit_hash='7'*64,reading_body_hash=parsed.body_hash)
    rcbytes=canonical_bytes(rc.model_dump(mode='json'));rch=hashlib.sha256(rcbytes).hexdigest()
    policy=s.vision_policy.model_copy(update={'model':'openai/gpt-6-astra'})
    ph=write(Path(s.config.vision_policy.path),policy)
    models,endpoints=catalogue()
    mw=canonical_bytes(models).replace(b'openai/gpt-6.1-sol',b'openai/gpt-6-astra')
    ew=canonical_bytes(endpoints).replace(b'openai/gpt-6.1-sol',b'openai/gpt-6-astra')
    inv=raw_endpoint_safety_inventory_v1(mw,ew,model='openai/gpt-6-astra')
    prompt=m.originals.original_review_prompt_v1(parsed,rendered=rendered,population=s.context.population,
        principal=s.context.actor_id,model='openai/gpt-6-astra')
    j=s.context.job;request=copy.deepcopy(j.request);request.update(model='openai/gpt-6-astra',
        messages=raw_pdf_multimodal_messages_v1(rendered,prompt));rh=digest(request)
    processing=j.processing_request.model_copy(update={'purpose':'source-original-review'})
    q=j.pricing.model_copy(update={'model':'openai/gpt-6-astra','request_hash':rh,'vision_token_policy_sha256':ph,
        'catalogue_sha256':inv.catalogue_sha256,'model_capability_sha256':inv.model_capability_sha256})
    j=type(j).model_validate(j.model_dump(mode='python')|{'purpose':'source-original-review','reading_commit_hash':rch,
        'request':request,'request_hash':rh,'pricing':q,'processing_request':processing,
        'approvals':tuple(a.model_copy(update={'purpose':'source-original-review'}) for a in j.approvals)})
    x=type(s.context).model_validate(s.context.model_dump(mode='python')|{'job':j,
        'pricing_quote_hash':digest(q.model_dump(mode='json')),'vision_token_policy_hash':ph})
    bounds=initial_bounds.model_copy(update={'model':'openai/gpt-6-astra'})
    bh=write(Path(s.config.billing_bounds.path),bounds)
    xh=write(Path(s.config.context.path),x)
    pp=tmp_path/'actual-protected-reader-packet.json';pp.write_bytes(parsed.body);pp.chmod(0o600)
    c=type(s.config).model_validate(s.config.model_dump(mode='python')|{'phase_purpose':'source-original-review',
        'reading_packet':{'path':str(pp),'sha256':parsed.body_hash},
        'context':{'path':s.config.context.path,'sha256':xh},
        'vision_policy':{'path':s.config.vision_policy.path,'sha256':ph},
        'billing_bounds':{'path':s.config.billing_bounds.path,'sha256':bh}})
    ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
    s.resolver.binding=replace(s.resolver.binding,purpose='source-original-review')
    factory.settings=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah,context=x,vision_policy=policy)
    state.update(job=j,models_wire=mw,endpoints_wire=ew);state['wire']['model']='openai/gpt-6-astra'
    history={'calls':[],'damage':None,'parsed':parsed,'record':rc}
    def retained(commit_hash):
        assert commit_hash==rch;history['calls'].append(commit_hash)
        snapshot=snapshot_for(c);at=datetime.now(timezone.utc)
        fields=dict(schema_version=1,purpose='original-review-reading-input-v1',reading_commit_sha256=rch,
            reading_commit_canonical_utf8_hex=rcbytes.hex(),reader_principal_id=reader,
            reader_session_role='old_original_reader',reader_model_id='openai/gpt-6.1-sol',
            reader_runtime_hash=reader_population.runtime_hash,reader_population_id=reader_population.population_id,
            reader_operation_registry_hash=reader_population.operation_registry_hash,
            reader_model_identity_sha256=digest({'model_id':'openai/gpt-6.1-sol','purpose':'source-original-reading',
                'session_role':'old_original_reader','runtime_hash':reader_population.runtime_hash,
                'population_id':str(reader_population.population_id),'response_sha256':rch}),
            reviewer_snapshot=snapshot,checked_at=at,valid_until=snapshot.valid_until)
        result=OriginalReviewReadingInputV1.model_validate(fields)
        if history['damage']=='metadata':result=result.model_copy(update={'reader_principal_id':uuid4()})
        if history['damage']=='revoked':raise PermissionError('actual current reviewer revoked')
        return result
    monkeypatch.setattr(s.resolver,'original_review_reading_input_v1',retained)
    return factory,state,observer,rendered,history


def test_factory_reviewer_rebuilds_exact_protected_reading_after_separate_commit(review_factory_case):
    factory,state,observer,rendered,history=review_factory_case
    prompt=factory.settings.read_review_prompt(rendered)
    assert json.loads(prompt)['reading_body_hash']==history['parsed'].body_hash
    result=factory.execute()
    assert result.commit.purpose=='source-original-review' and result.commit.model_id=='openai/gpt-6-astra'
    assert len(history['calls'])>=4 and state['paid']==1


@pytest.mark.parametrize('damage',['body_bytes','missing','metadata','revoked','wrong_prompt','missing_commit','second_read'])
def test_review_input_drift_or_unbound_prompt_refuses_before_paid_call(review_factory_case,monkeypatch,damage):
    factory,state,_,rendered,history=review_factory_case;s=factory.settings
    if damage=='body_bytes':Path(s.config.reading_packet.path).write_bytes(history['parsed'].body+b' ')
    elif damage=='missing':
        c=s.config.model_copy(update={'reading_packet':None});ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
        factory.settings=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah)
    elif damage in {'metadata','revoked'}:history['damage']=damage
    elif damage=='second_read':
        prior=s.resolver.original_review_reading_input_v1
        def changed(h):
            if history['calls']:raise PermissionError('reviewer revoked after protected read')
            return prior(h)
        monkeypatch.setattr(s.resolver,'original_review_reading_input_v1',changed)
    else:
        # A changed appointed job must still satisfy the canonical prompt and
        # actual committed metadata checks; matching opaque hashes are not enough.
        j=s.context.job;request=copy.deepcopy(j.request)
        if damage=='wrong_prompt':request['messages']=raw_pdf_multimodal_messages_v1(rendered,'Spoofed independently approved prompt')
        rh=digest(request);q=j.pricing.model_copy(update={'request_hash':rh})
        j=j.model_copy(update={'request':request,'request_hash':rh,'pricing':q,
            **({'reading_commit_hash':'0'*64} if damage=='missing_commit' else {})})
        x=s.context.model_copy(update={'job':j,'pricing_quote_hash':digest(q.model_dump(mode='json'))})
        xh=write(Path(s.config.context.path),x);c=s.config.model_copy(update={'context':s.config.context.model_copy(update={'sha256':xh})})
        ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
        factory.settings=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah,context=x);state['job']=j
    with pytest.raises((PermissionError,ValueError,AssertionError)):factory.execute()
    assert state['paid']==0 and state['reservations']==[]


@pytest.mark.parametrize('damage',['partial','http402','capture_ack','record_ack','settlement_ack',
    'after_settlement_revoke','wire_tamper','receipt_tamper','validator_authority','currentness_value'])
def test_post_paid_loss_or_custody_tampering_retains_one_attempt_no_commit(factory_case,monkeypatch,damage):
    factory,state,_,_=factory_case;j=factory.settings.context.job
    if damage=='partial':state['partial']=True
    elif damage=='http402':state['http_error']=True
    elif damage=='capture_ack':
        original=factory.broker._capture_wire
        def capture(*args,**kwargs):original(*args,**kwargs);raise OSError('invented wire acknowledgement lost')
        monkeypatch.setattr(factory.broker,'_capture_wire',capture)
    elif damage=='record_ack':
        original=factory.broker._record
        def record(*args,**kwargs):original(*args,**kwargs);raise OSError('invented native acknowledgement lost')
        monkeypatch.setattr(factory.broker,'_record',record)
    elif damage=='currentness_value':
        original=settings_module.RawOriginalProviderSettingsV1.observed_window;calls=[]
        def expired(self):
            calls.append(1)
            if len(calls)==2:raise ValueError('actual currentness parse refused')
            return original(self)
        monkeypatch.setattr(settings_module.RawOriginalProviderSettingsV1,'observed_window',expired)
    elif damage=='validator_authority':
        def denied(*args):raise PermissionError('existing validator authority denied')
        monkeypatch.setattr(factory.broker,'_validate_response',denied)
    else:
        original=factory._settlement
        def settlement(*args):
            original(*args)
            if damage=='settlement_ack':raise OSError('invented committed settlement acknowledgement lost')
            if damage=='after_settlement_revoke':state['authorized']=False
            elif damage=='wire_tamper':factory._path(j,'.wire').write_bytes(b'altered-original-wire')
            elif damage=='receipt_tamper':
                path=factory._path(j,'.json');body=json.loads(path.read_bytes());body['job_hash']='0'*64;path.write_bytes(canonical_bytes(body))
        monkeypatch.setattr(factory,'_settlement',settlement)
    with pytest.raises(m.RawOriginalOutcomeUnknown):factory.execute()
    assert state['paid']==len(state['reservations'])==len(state['finishes'])==1
    assert factory._path(j,'.wire').exists() and factory._path(j,'.json').exists()
    assert not factory._path(j,'.raw-paid.json').exists()
    if damage in {'validator_authority','currentness_value'}:
        assert state['finishes'][0][1]['failure_kind']=='transport_failure'
        assert state['finishes'][0][1]['actual_usd']>=state['reservations'][0][1]['maximum']
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==1



def test_review_pointer_is_optional_in_genuine_older_protected_config_bytes(factory_case):
    factory,state,_,_=factory_case;s=factory.settings
    body=s.config.model_dump(mode='json');del body['reading_packet']
    raw=canonical_bytes(body);s.config_path.write_bytes(raw);ch=hashlib.sha256(raw).hexdigest()
    a=appointment(s.config,ch);ah=write(s.appointment_path,a)
    s=replace(s,config_sha256=ch,appointment=a,appointment_sha256=ah)
    assert s.config.reading_packet is None
    assert type(s.current_window()) is settings_module.RawOriginalAuthorityWindowV1
    assert state['paid']==0


def test_final_authority_loss_after_durable_paid_commit_returns_unknown_without_redispatch(factory_case,monkeypatch):
    factory,state,_,_=factory_case;original=factory._persist;j=factory.settings.context.job
    def persist(job,suffix,raw):
        result=original(job,suffix,raw)
        if suffix=='.raw-evidence.json':state['authorized']=False
        return result
    monkeypatch.setattr(factory,'_persist',persist)
    with pytest.raises(m.RawOriginalOutcomeUnknown):factory.execute()
    assert factory._path(j,'.raw-paid.json').exists() and factory._path(j,'.raw-evidence.json').exists()
    assert state['paid']==len(state['finishes'])==1
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==1


@pytest.mark.parametrize('suffix', ['.raw-models.wire', '.raw-endpoints.wire', '.raw-billing.json', '.raw-comparison.json', '.raw-before-sql.json', '.raw-after-sql.json', '.raw-observer-envelope', '.raw-observer-witness.json'])
def test_prior_partial_private_evidence_refuses_before_any_network(factory_case, suffix):
    factory, state, _, _ = factory_case
    factory._path(state['job'], suffix).write_bytes(b'invented retained partial evidence')
    with pytest.raises(PermissionError, match='forbids replay'):
        factory.execute()
    assert state['requests'] == [] and state['paid'] == 0 and state['reservations'] == []


def test_receipt_recovery_write_failure_keeps_typed_unknown_and_paid_wire(factory_case, monkeypatch):
    factory, state, _, _ = factory_case
    def fail_record(*args, **kwargs):
        raise OSError('invented receipt fsync unavailable')
    monkeypatch.setattr(factory.broker, '_record', fail_record)
    with pytest.raises(m.RawOriginalOutcomeUnknown, match='no automatic retry'):
        factory.execute()
    assert state['paid'] == 1 and len(state['finishes']) == 1
    assert factory._path(state['job'], '.wire').read_bytes()
    with pytest.raises(PermissionError, match='forbids replay'):
        factory.execute()
    assert state['paid'] == 1


def test_concurrent_factory_calls_have_one_prepaid_private_evidence_owner(factory_case, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    factory, state, _, _ = factory_case
    original = factory._persist
    barrier = Barrier(2)
    def persist(job, suffix, raw):
        if suffix == '.raw-models.wire':
            barrier.wait(timeout=5)
        return original(job, suffix, raw)
    monkeypatch.setattr(factory, '_persist', persist)
    def execute():
        try:
            return factory.execute()
        except FileExistsError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: execute(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert state['paid'] == 1 and len(state['reservations']) == len(state['finishes']) == 1
