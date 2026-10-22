"""One actual-opener-shaped metadata exchange; invented key, no network."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import hashlib,http.client,io,urllib.error,urllib.request
import pytest
from oracle_brain.operating_model import native_provider as module
from oracle_brain.operating_model.native_provider import NativeOpenRouter,NativeMetadataWireV1,NoRedirect,ENDPOINT

@pytest.fixture
def exchange(monkeypatch):
    state={'calls':[],'wire':b'{ "data" : [ ] }\n','status':200,'length':None,'url':None,'coverage':[]}
    native=NativeOpenRouter('invented-metadata-key',coverage_receipt=lambda:None,
        trusted_coverage_hash='a'*64,ledger_identity_hash='b'*64)
    monkeypatch.setattr(native,'_coverage',lambda now:state['coverage'].append(now))
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):state['closed']=True
        @property
        def status(self):return state['status']
        def geturl(self):return state['url'] or state['calls'][0][0].full_url
        def getheader(self,key):assert key=='Content-Length';return state['length']
        def read(self,bound):
            assert bound==16*1024*1024+1
            if state.get('partial'):raise http.client.IncompleteRead(state['wire'],1)
            return state['wire']
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=='GET' and request.data is None and timeout==60
            assert request.get_header('Authorization')=='Bearer invented-metadata-key'
            assert request.get_header('Cache-control')=='no-store'
            state['calls'].append((request,timeout))
            if 'error' in state:raise state['error']
            return Response()
    def build(*handlers):
        assert len(handlers)==2 and type(handlers[0]) is urllib.request.ProxyHandler
        assert handlers[0].proxies=={} and type(handlers[1]) is NoRedirect
        return Opener()
    monkeypatch.setattr(urllib.request,'build_opener',build)
    return native,state

@pytest.mark.parametrize('path',['/models','/models/openai/gpt-6.1-sol/endpoints','/models/openai/gpt-6-astra/endpoints'])
def test_exact_metadata_paths_preserve_original_wire_and_observed_time(exchange,path):
    native,state=exchange;state['length']=str(len(state['wire']))
    result=native.metadata_wire_v1(path)
    assert result.wire==state['wire'] and result.wire_sha256==hashlib.sha256(state['wire']).hexdigest()
    assert result.path==path and result.started_at<=result.observed_at
    assert 0<=result.elapsed_seconds<=60 and len(state['calls'])==1 and state['closed']
    assert state['calls'][0][0].full_url==ENDPOINT+path and len(state['coverage'])==2
    assert not hasattr(native,'last_response_text') and not hasattr(native,'last_wire_custody_complete')

@pytest.mark.parametrize('path',['/key','/chat/completions','/embeddings','/models/openai/foreign/endpoints',
    '/models/openai/gpt-6.1-sol/endpoints?extra=1','https://foreign.invalid/models','//foreign.invalid/models',None])
def test_foreign_or_paid_paths_refused_before_any_io(exchange,path):
    native,state=exchange
    with pytest.raises(PermissionError):native.metadata_wire_v1(path)
    assert state['calls']==[] and state['coverage']==[]

@pytest.mark.parametrize('damage',['partial','overlimit','empty','length','length-shape','target','status','http-error','timeout','slow','clock'])
def test_incomplete_bounded_tls_target_or_time_failures_do_not_retry(exchange,monkeypatch,damage):
    native,state=exchange
    if damage=='partial':state['partial']=True
    elif damage=='overlimit':state['wire']=b'x'*(16*1024*1024+1)
    elif damage=='empty':state['wire']=b''
    elif damage=='length':state['length']=str(len(state['wire'])+1)
    elif damage=='length-shape':state['length']='-1'
    elif damage=='target':state['url']='https://foreign.invalid/models'
    elif damage=='status':state['status']=302
    elif damage=='http-error':state['error']=urllib.error.HTTPError(ENDPOINT+'/models',403,'denied',{},io.BytesIO(b'error'))
    elif damage=='timeout':state['error']=TimeoutError('invented timeout')
    elif damage=='slow':
        ticks=iter((0.,61.));monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    else:
        class Clock:
            values=iter((datetime(2026,1,1,tzinfo=timezone.utc),datetime(2025,1,1,tzinfo=timezone.utc)))
            @classmethod
            def now(cls,tz):return next(cls.values)
        monkeypatch.setattr(module,'datetime',Clock)
    with pytest.raises(RuntimeError,match='no retry'):native.metadata_wire_v1('/models')
    assert len(state['calls'])==1 and len(state['coverage'])==1


def test_current_coverage_failure_happens_before_key_transport(exchange,monkeypatch):
    native,state=exchange
    def deny(now):raise PermissionError('coverage unavailable')
    monkeypatch.setattr(native,'_coverage',deny)
    with pytest.raises(PermissionError):native.metadata_wire_v1('/models')
    assert state['calls']==[]


def test_metadata_redirect_handler_and_direct_record_validation_are_fail_closed(exchange):
    with pytest.raises(PermissionError):NoRedirect().redirect_request(None,None,302,None,None,'https://foreign.invalid')
    result=exchange[0].metadata_wire_v1('/models')
    for changes in ({'wire':b''},{'wire':'decoded instead of bytes'},{'elapsed_seconds':float('nan')},
        {'elapsed_seconds':True},{'elapsed_seconds':61.},{'started_at':datetime.now()},
        {'observed_at':result.started_at-timedelta(seconds=1)},{'path':'/key'}):
        with pytest.raises(ValueError):replace(result,**changes)


def test_coverage_revoked_after_actual_metadata_read_does_not_return_a_record(exchange,monkeypatch):
    native,state=exchange;checks=[]
    def coverage(now):
        checks.append(now)
        if len(checks)==2:raise PermissionError('invented current coverage revoked')
    monkeypatch.setattr(native,'_coverage',coverage)
    with pytest.raises(RuntimeError):native.metadata_wire_v1('/models')
    assert len(state['calls'])==1 and state['closed'] and len(checks)==2
