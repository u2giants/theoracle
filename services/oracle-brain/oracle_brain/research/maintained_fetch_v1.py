"""One independently installed research source, once-claimed actual public GET.

The queue supplies only an opaque run identity. SQL owns current source rights;
this owner retains exact HTTP wire/body bytes before recording observation.
No source approval, semantic review, company fact or replacement retry is issued.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import UUID
import hashlib,json,os
from pydantic import AwareDatetime,Field,model_validator
from ..operating_model.contracts import StrictRecord,canonical_bytes
from ..operating_model.protected_inputs_v1 import _pinned,_parse
from ..operating_model.artifact_storage import _write_private_at,_parent_fd,_read_private_at
from .durable_authority_v1 import ResearchAuthorityV1,ResearchOutcomeUnknown
from .fetch import _InstalledResearchGET,VerifiedResearchResponseV1,ResearchTransportUnknown
from .registry import Source

class ResearchNetworkProfileV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['registered-public-research-get-v1']
    workspace_id:UUID;source_id:UUID
    source_revision:int=Field(strict=True,ge=1)
    registered_url:str=Field(min_length=1,max_length=2048)
    ca_path:str;ca_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    storage_root:str
    storage_dev:int=Field(strict=True,ge=0)
    storage_ino:int=Field(strict=True,ge=1)
    storage_uid:int=Field(strict=True,ge=0)
    original_horizon:AwareDatetime;expires_at:AwareDatetime

    @model_validator(mode='after')
    def exact_descriptor(self):
        if type(self.schema_version) is not int or self.expires_at>self.original_horizon:
            raise ValueError('exact finite research profile required')
        Source('profile','profile',self.registered_url,'unknown','unknown','public','weekly')
        for path in (self.ca_path,self.storage_root):
            if not Path(path).is_absolute() or str(Path(path))!=path:raise ValueError('absolute installed paths required')
        return self

class MaintainedResearchFetcherV1:
    """Persistent fixed source transport; never instantiate per caller URL."""
    def __init__(self,authority):
        if type(authority) is not ResearchAuthorityV1 or authority.settings.config.operation!='fetch':
            raise TypeError('exact separately installed research fetch owner required')
        self._authority=authority;c=authority.settings.config
        if c.fetch_profile is None:raise PermissionError('independent fixed research network/storage profile required')
        self._profile=_parse(ResearchNetworkProfileV1,_pinned(c.fetch_profile.path,c.fetch_profile.sha256))
        p=self._profile
        if (p.workspace_id,p.source_id,p.source_revision)!=(c.workspace_id,c.source_id,c.source_revision):
            raise PermissionError('network profile belongs to another source')
        self._lock=Lock();self._active=None
        self._transport=_InstalledResearchGET(url=p.registered_url,ca_file=p.ca_path,ca_sha256=p.ca_sha256,current=self._current)

    def _profile_current(self,deadline):
        a=self._authority;p=self._profile;c=a.settings.config
        a.settings.current(deadline)
        if _parse(ResearchNetworkProfileV1,_pinned(c.fetch_profile.path,c.fetch_profile.sha256))!=p:
            raise PermissionError('installed research profile changed')
        now=datetime.now(timezone.utc)
        if not now<deadline<=min(p.expires_at,p.original_horizon):raise PermissionError('original research profile window expired')
        _pinned(p.ca_path,p.ca_sha256,1000000)
        fd=_parent_fd(p.storage_root,(),create=False,expected_root=(p.storage_dev,p.storage_ino,p.storage_uid))
        os.close(fd)

    def _current(self):
        if self._active is None:raise PermissionError('no locally owned once-claimed research operation')
        run,claim,deadline=self._active
        self._profile_current(deadline)
        self._authority.current_fetch_v1(run,claim,deadline=deadline)
        self._profile_current(deadline)

    def _store(self,key,data):
        self._current();p=self._profile
        _write_private_at(p.storage_root,key.split('/'),data,expected_root=(p.storage_dev,p.storage_ino,p.storage_uid))
        self._current()

    def _retained_read(self,key,maximum,deadline):
        self._profile_current(deadline);p=self._profile
        parent=_parent_fd(p.storage_root,key.split('/')[:-1],create=False,
            expected_root=(p.storage_dev,p.storage_ino,p.storage_uid))
        try:data=_read_private_at(parent,key.split('/')[-1],maximum)
        finally:os.close(parent)
        self._profile_current(deadline)
        return data

    @staticmethod
    def _observation(trace,raw,trace_key):
        last=trace['hops'][-1]
        return canonical_bytes(dict(schema_version=1,state='observed' if last['http_status']==200 else 'known_failure',
            http_status=last['http_status'],wire_sha256=last['wire_sha256'],wire_byte_count=last['wire_byte_count'],
            body_sha256=last['body_sha256'],body_byte_count=last['body_byte_count'],private_key=last['wire_private_key'],
            trace_sha256=hashlib.sha256(raw).hexdigest(),trace_byte_count=len(raw),trace_private_key=trace_key,retrieved_at=trace['observed_at']))

    def reconcile_retained_v1(self,run_id,*,deadline):
        """Reads already retained bytes only; no transport call or renewed fetch."""
        if type(run_id) is not UUID:raise PermissionError('exact retained run required')
        if not self._lock.acquire(blocking=False):raise PermissionError('one active research operation required')
        try:
            self._profile_current(deadline)
            receipt=self._authority.retained_fetch_v1(run_id,deadline=deadline)
            claim=UUID(receipt['claim_id']);p=self._profile
            prefix=f'research/{p.workspace_id}/{p.source_id}/{run_id}/{claim}'
            trace_key=prefix+'.trace.json';raw=self._retained_read(trace_key,65536,deadline)
            trace=json.loads(raw)
            expected={'schema_version','purpose','workspace_id','source_id','source_revision','run_id','claim_id','registered_url',
                'started_at','observed_at','original_deadline','hops','semantically_reviewed','company_policy'}
            if (type(trace) is not dict or set(trace)!=expected or canonical_bytes(trace)!=raw
                    or type(trace['schema_version']) is not int or trace['schema_version']!=1
                    or trace['purpose']!='actual-research-http-custody-v1'
                    or trace['workspace_id']!=str(p.workspace_id) or trace['source_id']!=str(p.source_id)
                    or type(trace['source_revision']) is not int or trace['source_revision']!=p.source_revision
                    or trace['run_id']!=str(run_id) or trace['claim_id']!=str(claim)
                    or trace['registered_url']!=p.registered_url or trace['semantically_reviewed'] is not False or trace['company_policy'] is not False
                    or type(trace['hops']) is not list or not 1<=len(trace['hops'])<=6):
                raise PermissionError('exact original immutable research trace required')
            started,observed,original=(datetime.fromisoformat(trace[k]) for k in ('started_at','observed_at','original_deadline'))
            if (any(x.tzinfo is None for x in (started,observed,original))
                    or original!=datetime.fromisoformat(receipt['original_deadline'])
                    or not started<=observed<=original or observed>datetime.now(timezone.utc)):
                raise PermissionError('retained trace cannot renew original retrieval')
            hop_fields={'url','http_status','headers','wire_private_key','wire_sha256','wire_byte_count','body_private_key','body_sha256','body_byte_count'}
            for index,hop in enumerate(trace['hops']):
                if type(hop) is not dict or set(hop)!=hop_fields:raise PermissionError('closed retained hop required')
                Source('retained','retained',hop['url'],'unknown','unknown','public','weekly')
                if (type(hop['http_status']) is not int or not 200<=hop['http_status']<=599
                        or type(hop['headers']) is not list or any(type(x) is not list or len(x)!=2 or any(type(v) is not str for v in x) for x in hop['headers'])):
                    raise PermissionError('exact retained HTTP metadata required')
                expected_wire=prefix+('.wire' if index==len(trace['hops'])-1 else f'.hop-{index}.wire')
                if hop['wire_private_key']!=expected_wire or hop['body_private_key']!=prefix+f'.body-{index}.bin':
                    raise PermissionError('retained private key escaped original claim')
                for kind,limit in (('wire',1064960),('body',1048576)):
                    data=self._retained_read(hop[kind+'_private_key'],limit,deadline)
                    if (type(hop[kind+'_byte_count']) is not int or len(data)!=hop[kind+'_byte_count']
                            or hashlib.sha256(data).hexdigest()!=hop[kind+'_sha256']):
                        raise PermissionError('retained actual response bytes differ')
                self._authority.retained_fetch_v1(run_id,deadline=deadline)
            if trace['hops'][0]['url']!=p.registered_url:raise PermissionError('retained origin differs')
            observation=self._observation(trace,raw,trace_key)
            result=self._authority.observe_fetch_v1(run_id,claim,observation,deadline=deadline)
            self._profile_current(deadline)
            return dict(schema_version=1,state=result['state'],run_id=str(run_id),resend_authorized=False)
        except Exception as exc:
            raise ResearchOutcomeUnknown('retained research reconciliation UNKNOWN; no network replay authorized') from exc
        finally:self._lock.release()

    def _retain_incomplete_v1(self,run,claim,error):
        # Forensic custody only, under the STILL-CURRENT original claim. This
        # format is deliberately not accepted by completed-read/reconcile paths.
        p=self._profile;prefix=f'research/{p.workspace_id}/{p.source_id}/{run}/{claim}'
        prior=error.prior_responses
        if type(prior) is not tuple or len(prior)>6:raise PermissionError('bounded actual completed hop inventory required')
        hops=[]
        for i,(url,response) in enumerate(prior):
            if (type(url) is not str or not 1<=len(url)<=2048 or type(response) is not VerifiedResearchResponseV1
                    or type(response.status) is not int or not 200<=response.status<=599
                    or type(response.body) is not bytes or len(response.body)>1048576
                    or type(response.wire) is not bytes or not 1<=len(response.wire)<=1064960):
                raise PermissionError('bounded original completed response custody required')
            wire=prefix+f'.partial-hop-{i}.wire';body=prefix+f'.partial-body-{i}.bin'
            self._store(wire,response.wire);self._store(body,response.body)
            hops.append(dict(url=url,http_status=response.status,wire_private_key=wire,
                wire_sha256=hashlib.sha256(response.wire).hexdigest(),wire_byte_count=len(response.wire),
                body_private_key=body,body_sha256=hashlib.sha256(response.body).hexdigest(),body_byte_count=len(response.body)))
        wire_key=None
        if error.wire:
            wire_key=prefix+'.partial.wire';self._store(wire_key,error.wire)
        failed=error.failed_url
        if failed is not None and (type(failed) is not str or len(failed)>2048):failed=None
        trace=canonical_bytes(dict(schema_version=1,purpose='incomplete-research-http-custody-v1',
            workspace_id=str(p.workspace_id),source_id=str(p.source_id),source_revision=p.source_revision,
            run_id=str(run),claim_id=str(claim),original_deadline=self._active[2].isoformat(),
            observed_at=datetime.now(timezone.utc).isoformat(),completed_hops=hops,failed_url=failed,
            partial_wire_private_key=wire_key,partial_wire_sha256=hashlib.sha256(error.wire).hexdigest(),
            partial_wire_byte_count=len(error.wire),resend_authorized=False,semantically_reviewed=False,company_policy=False))
        if len(trace)>65536:raise PermissionError('bounded incomplete custody metadata required')
        self._store(prefix+'.partial.trace.json',trace)

    def execute_v1(self,run_id,*,deadline):
        if type(run_id) is not UUID:raise PermissionError('opaque exact research run required')
        if not self._lock.acquire(blocking=False):raise PermissionError('one active installed research fetch required')
        claim=None
        try:
            self._profile_current(deadline)
            claimed=self._authority.claim_fetch_v1(run_id,deadline=deadline)
            if claimed['fetch_authorized'] is not True:
                return dict(schema_version=1,state='UNKNOWN',run_id=str(run_id),resend_authorized=False)
            claim=UUID(claimed['claim_id'])
            original=min(deadline,datetime.fromisoformat(claimed['valid_until']))
            self._active=(run_id,claim,original)
            p=self._profile
            if claimed['definition']['url']!=p.registered_url:raise PermissionError('claimed registration URL differs from installed source')
            self._current();started=datetime.now(timezone.utc)
            responses=self._transport.fetch(caller_deadline=original)
            self._current()
            if type(responses) is not tuple or not 1<=len(responses)<=6:raise PermissionError('bounded actual source response trace required')
            prefix=f'research/{p.workspace_id}/{p.source_id}/{run_id}/{claim}'
            hops=[]
            for index,(url,response) in enumerate(responses):
                if type(url) is not str or type(response) is not VerifiedResearchResponseV1:
                    raise PermissionError('exact installed transport response required')
                if (type(response.status) is not int or not 200<=response.status<=599
                        or type(response.body) is not bytes or len(response.body)>1048576
                        or type(response.wire) is not bytes or not 1<=len(response.wire)<=1064960):
                    raise PermissionError('bounded actual response wire/body required')
                wire_key=prefix+('.wire' if index==len(responses)-1 else f'.hop-{index}.wire')
                body_key=prefix+f'.body-{index}.bin'
                self._store(wire_key,response.wire);self._store(body_key,response.body)
                hops.append(dict(url=url,http_status=response.status,headers=[list(x) for x in response.headers],
                    wire_private_key=wire_key,wire_sha256=hashlib.sha256(response.wire).hexdigest(),wire_byte_count=len(response.wire),
                    body_private_key=body_key,body_sha256=hashlib.sha256(response.body).hexdigest(),body_byte_count=len(response.body)))
            trace=canonical_bytes(dict(schema_version=1,purpose='actual-research-http-custody-v1',workspace_id=str(p.workspace_id),source_id=str(p.source_id),
                source_revision=p.source_revision,run_id=str(run_id),claim_id=str(claim),registered_url=p.registered_url,
                started_at=started.isoformat(),observed_at=datetime.now(timezone.utc).isoformat(),original_deadline=original.isoformat(),
                hops=hops,semantically_reviewed=False,company_policy=False))
            if len(trace)>65536:raise PermissionError('bounded retained research trace required')
            trace_key=prefix+'.trace.json';self._store(trace_key,trace)
            last=hops[-1]
            observation=self._observation(json.loads(trace),trace,trace_key)
            self._current()
            result=self._authority.observe_fetch_v1(run_id,claim,observation,deadline=original)
            self._profile_current(original)
            return dict(schema_version=1,state=result['state'],run_id=str(run_id),resend_authorized=False)
        except Exception as exc:
            # A body-bearing claim may already be committed. An incomplete
            # exchange never becomes a known failure or authorizes retry.
            if claim is not None:
                if type(exc) is ResearchTransportUnknown:
                    try:self._retain_incomplete_v1(run_id,claim,exc)
                    except Exception:pass
                try:
                    self._profile_current(deadline)
                    observation=canonical_bytes(dict(schema_version=1,state='UNKNOWN',http_status=None,wire_sha256=None,wire_byte_count=None,
                        body_sha256=None,body_byte_count=None,private_key=None,trace_sha256=None,trace_byte_count=None,trace_private_key=None,retrieved_at=None))
                    self._authority.observe_fetch_v1(run_id,claim,observation,deadline=deadline)
                except Exception:pass
                raise ResearchOutcomeUnknown('research fetch UNKNOWN; retained run forbids network replay') from exc
            raise
        finally:
            self._active=None;self._lock.release()
