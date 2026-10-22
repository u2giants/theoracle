"""Current independent read grant + exact retained external reference bytes.

Reading an external reference does not qualify its assertions, create company
policy or mark publication/effective/scope metadata known. HTML remains data.
"""
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import hashlib,json,os
from pydantic import AwareDatetime,Field,model_validator
from ..operating_model.contracts import StrictRecord,canonical_bytes
from ..operating_model.protected_inputs_v1 import _parse,_pinned
from ..operating_model.artifact_storage import _parent_fd,_read_private_at
from .durable_authority_v1 import ResearchAuthorityV1

class ResearchReadProfileV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['retained-industry-reference-read-v1']
    workspace_id:UUID;source_id:UUID
    source_revision:int=Field(strict=True,ge=1)
    storage_root:str
    storage_dev:int=Field(strict=True,ge=0)
    storage_ino:int=Field(strict=True,ge=1)
    storage_uid:int=Field(strict=True,ge=0)
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def finite_private(self):
        if (type(self.schema_version) is not int or self.expires_at>self.original_horizon
                or not Path(self.storage_root).is_absolute() or str(Path(self.storage_root))!=self.storage_root):
            raise ValueError('exact finite independent reference reader required')
        return self

class MaintainedResearchReaderV1:
    def __init__(self,authority):
        if type(authority) is not ResearchAuthorityV1 or authority.settings.config.operation!='read':
            raise TypeError('exact independently installed reference read owner required')
        c=authority.settings.config
        if c.read_profile is None:raise PermissionError('independent retained reference read profile required')
        p=_parse(ResearchReadProfileV1,_pinned(c.read_profile.path,c.read_profile.sha256))
        if (p.workspace_id,p.source_id,p.source_revision)!=(c.workspace_id,c.source_id,c.source_revision):
            raise PermissionError('reference reader belongs to another source')
        self._authority,self._profile=authority,p

    def _profile_current(self,deadline):
        a=self._authority;c=a.settings.config;p=self._profile;a.settings.current(deadline)
        if (_parse(ResearchReadProfileV1,_pinned(c.read_profile.path,c.read_profile.sha256))!=p
                or not datetime.now(timezone.utc)<deadline<=min(p.original_horizon,p.expires_at)):
            raise PermissionError('original reference read profile expired or changed')
        fd=_parent_fd(p.storage_root,(),create=False,expected_root=(p.storage_dev,p.storage_ino,p.storage_uid));os.close(fd)

    def _current(self,initial,deadline):
        self._profile_current(deadline)
        now=self._authority.latest_reference_v1(deadline=deadline)
        fields=('state','workspace_id','source_id','source_revision','definition','definition_sha256','run_id','claim_id','receipt_event_id','original_deadline','recorded_at','observation')
        if any(now[k]!=initial[k] for k in fields):raise PermissionError('current reference receipt or permission changed')
        self._profile_current(deadline)

    def _read(self,key,limit,initial,deadline):
        self._current(initial,deadline);p=self._profile
        parts=key.split('/');parent=_parent_fd(p.storage_root,parts[:-1],create=False,
            expected_root=(p.storage_dev,p.storage_ino,p.storage_uid))
        try:data=_read_private_at(parent,parts[-1],limit)
        finally:os.close(parent)
        self._current(initial,deadline)
        return data

    def latest_v1(self,*,deadline):
        self._profile_current(deadline)
        initial=self._authority.latest_reference_v1(deadline=deadline)
        status=self._authority.status_v1(deadline=deadline)
        self._current(initial,deadline)
        output=dict(schema_version=1,workspace_id=str(self._profile.workspace_id),source_id=str(self._profile.source_id),
            source_revision=self._profile.source_revision,state=initial['state'],registration=initial['definition'],refresh={k:status[k] for k in ('state','last_success','next_due','attempts','exhausted')},
            reference=None,original_text=None,company_policy=False,semantically_reviewed=False)
        if initial['state']=='unavailable':return output
        run,claim=UUID(initial['run_id']),UUID(initial['claim_id']);p=self._profile
        prefix=f'research/{p.workspace_id}/{p.source_id}/{run}/{claim}';o=initial['observation']
        fields={'schema_version','state','http_status','wire_sha256','wire_byte_count','body_sha256','body_byte_count','private_key','trace_sha256','trace_byte_count','trace_private_key','retrieved_at'}
        if (type(o) is not dict or set(o)!=fields or type(o['schema_version']) is not int or o['schema_version']!=1
                or o['state']!='observed' or type(o['http_status']) is not int or o['http_status']!=200
                or o['private_key']!=prefix+'.wire' or o['trace_private_key']!=prefix+'.trace.json'):
            raise PermissionError('closed actual retained reference receipt required')
        def checked(key,seal,count,limit):
            if type(count) is not int or not 0<=count<=limit:raise PermissionError('bounded actual retained byte count required')
            value=self._read(key,limit,initial,deadline)
            if len(value)!=count or hashlib.sha256(value).hexdigest()!=seal:raise PermissionError('retained reference seal changed')
            return value
        raw=checked(o['trace_private_key'],o['trace_sha256'],o['trace_byte_count'],65536);trace=json.loads(raw)
        expected={'schema_version','purpose','workspace_id','source_id','source_revision','run_id','claim_id','registered_url',
            'started_at','observed_at','original_deadline','hops','semantically_reviewed','company_policy'}
        if (type(trace) is not dict or set(trace)!=expected or canonical_bytes(trace)!=raw
                or type(trace['schema_version']) is not int or trace['schema_version']!=1
                or trace['purpose']!='actual-research-http-custody-v1' or trace['workspace_id']!=str(p.workspace_id)
                or trace['source_id']!=str(p.source_id) or type(trace['source_revision']) is not int or trace['source_revision']!=p.source_revision
                or trace['run_id']!=str(run) or trace['claim_id']!=str(claim) or trace['registered_url']!=initial['definition']['url']
                or type(trace['hops']) is not list or not 1<=len(trace['hops'])<=6
                or trace['company_policy'] is not False or trace['semantically_reviewed'] is not False):
            raise PermissionError('exact original source trace required')
        start,observed,original=(datetime.fromisoformat(trace[k]) for k in ('started_at','observed_at','original_deadline'))
        if (any(d.tzinfo is None for d in (start,observed,original)) or not start<=observed<=original
                or original!=datetime.fromisoformat(initial['original_deadline']) or observed>datetime.now(timezone.utc)
                or trace['observed_at']!=o['retrieved_at']):
            raise PermissionError('source retrieval time cannot be invented or renewed')
        last=trace['hops'][-1];body_key=prefix+f'.body-{len(trace["hops"])-1}.bin'
        if (type(last) is not dict or last.get('body_private_key')!=body_key
                or last.get('body_sha256')!=o['body_sha256'] or last.get('body_byte_count')!=o['body_byte_count']
                or last.get('wire_private_key')!=o['private_key'] or last.get('wire_sha256')!=o['wire_sha256']
                or last.get('wire_byte_count')!=o['wire_byte_count'] or last.get('http_status')!=200):
            raise PermissionError('retained final source does not match actual receipt')
        checked(o['private_key'],o['wire_sha256'],o['wire_byte_count'],1064960)
        body=checked(body_key,o['body_sha256'],o['body_byte_count'],1048576)
        # Binary originals stay retained. They are never decoded into invented
        # text; an independently qualified binary viewer is a separate owner.
        try:
            text=body.decode('utf-8',errors='strict')
            if '\x00' in text:text=None
        except UnicodeDecodeError:text=None
        output['original_text']=text
        output['reference']=dict(receipt_event_id=initial['receipt_event_id'],content_sha256=o['body_sha256'],
            publisher=initial['definition']['publisher'],original_url=initial['definition']['url'],final_url=last['url'],retrieved_at=observed.isoformat(),
            jurisdiction=initial['definition']['jurisdiction'],product_scope=initial['definition']['scope'],channel_scope=None,
            access=initial['definition']['access'],rights_confirmed=initial['definition']['rights_confirmed'],source_version=None,
            publication_date=None,effective_date=None,reviewed_at=None,refresh_due=status['next_due'],review_due=None,
            applicability='UNKNOWN',reason='independent_reference_review_required')
        self._current(initial,deadline)
        return output
