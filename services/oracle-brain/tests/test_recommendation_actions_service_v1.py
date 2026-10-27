"""Closed public selector commands only; no SQL/employee/provider authority."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.recommendation_actions_v1 import parse_recommendation_request_v1


def request(operation='inspect'):
 body=dict(schema_version=1,operation=operation,selector=dict(schema_version=1,artifact_id=str(uuid4()),artifact_version=1,artifact_sha256='a'*64,recommendation_id=str(uuid4())),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat().replace('+00:00','Z'))
 if operation.startswith('reconcile-'):body['command_id']=str(uuid4())
 elif operation=='feedback':body.update(expected_head=0,command_id=str(uuid4()),decision='defer',option_id=None,reason='Personal preference, not company policy')
 elif operation=='measurement':body.update(expected_head=0,command_id=str(uuid4()),experiment_id=str(uuid4()),phase='baseline',assertion_id=str(uuid4()),assertion_revision=1)
 return body

@pytest.mark.parametrize('operation',['inspect','feedback','measurement','reconcile-feedback','reconcile-measurement'])
def test_exact_closed_operations_preserve_original_deadline(operation):
 raw=canonical_bytes(request(operation));parsed=parse_recommendation_request_v1(raw)
 assert canonical_bytes(parsed.model_dump(mode='json'))==raw

@pytest.mark.parametrize('field',['actor_id','workspace_id','role','config','profile','provider','amount','currency','source_path','sql','callback','approval'])
def test_no_authority_or_number_selectors(field):
 body=request('measurement');body[field]='invented'
 with pytest.raises((ValueError,PermissionError)):parse_recommendation_request_v1(canonical_bytes(body))

@pytest.mark.parametrize('fault',['duplicate','whitespace','selector','bool-head','missing-head','bad-enum','long-reason','callback-operation','bad-uuid','null-selector','utc-alias'])
def test_malformed_or_noncanonical_refuses_before_any_boundary(fault):
 body=request('feedback')
 if fault=='duplicate':raw=canonical_bytes(body).replace(b'"operation":"feedback"',b'"operation":"feedback","operation":"feedback"')
 elif fault=='whitespace':raw=json.dumps(body).encode()
 else:
  if fault=='selector':body['selector']['actor_id']=str(uuid4())
  elif fault=='bool-head':body['expected_head']=True
  elif fault=='missing-head':del body['expected_head']
  elif fault=='bad-enum':body['decision']='confirm-model'
  elif fault=='long-reason':body['reason']='x'*1601
  elif fault=='callback-operation':body['operation']='register'
  elif fault=='bad-uuid':body['command_id']='not-a-uuid'
  elif fault=='null-selector':body['selector']=None
  elif fault=='utc-alias':body['caller_deadline']=body['caller_deadline'].replace('Z','+00:00')
  raw=canonical_bytes(body)
 with pytest.raises((ValueError,PermissionError)):parse_recommendation_request_v1(raw)

@pytest.mark.parametrize('operation',['reconcile-feedback','reconcile-measurement'])
def test_reconcile_is_exact_command_identity_without_body_history_or_newdecision(operation):
 body=request(operation)
 for field,value in [('expected_head',0),('reason','retry'),('decision','accept'),('number','12')]:
  with pytest.raises((ValueError,PermissionError)):parse_recommendation_request_v1(canonical_bytes(body|{field:value}))


@pytest.fixture
def private_lease_case(tmp_path,monkeypatch):
 """Actual immutable local files; SQL result seam is NOT installed authority."""
 import hashlib,os
 from types import SimpleNamespace
 from oracle_brain.hosting import recommendation_actions_v1 as service
 from oracle_brain.operating_model import request_deadline_v1 as fence
 from oracle_brain.operating_model.contracts import ArtifactManifest
 tick=[100.];wall=[datetime.now(timezone.utc)]
 class Clock:
  now=staticmethod(lambda tz=None:wall[0])
  fromisoformat=staticmethod(datetime.fromisoformat)
 monkeypatch.setattr(service,'datetime',Clock)
 monkeypatch.setattr(service.time,'monotonic',lambda:tick[0])
 body=request();deadline=wall[0]+timedelta(seconds=20)
 body['caller_deadline']=deadline.isoformat().replace('+00:00','Z')
 selected=service.parse_recommendation_request_v1(canonical_bytes(body)).selector
 workspace=uuid4();root=tmp_path/'private';root.mkdir(mode=0o700)
 directory=root/'operating-model'/str(workspace);directory.mkdir(parents=True,mode=0o700)
 (root/'operating-model').chmod(0o700)
 manifests=[]
 for index,payload in enumerate(({'recommendations':[]},{'consolidation_core':{}})):
  raw=canonical_bytes(payload);sha=hashlib.sha256(raw).hexdigest();path=directory/(sha+'.json');path.write_bytes(raw);path.chmod(0o600)
  manifests.append(ArtifactManifest(workspace_id=workspace,artifact_id=selected.artifact_id,version=1,kind='processing_recommendation_v1' if index==0 else 'processing_qualified_model_v1',input_digest='a'*64,source_digest='b'*64,permission_digest='c'*64,compiler_digest='d'*64,dependency_digest='e'*64,content_hash=sha,private_object_key=f'operating-model/{workspace}/{sha}.json',state='ready'))
 status={'redacted':False,'valid_until':(wall[0]+timedelta(seconds=2)).isoformat(),'context':dict(manifest=manifests[0].model_dump(mode='json'),parentManifest=manifests[1].model_dump(mode='json'))}
 class Reader:
  calls=0
  def read_v1(self,*args,**kwargs):self.calls+=1;return dict(status)
 reader=Reader();factory=object.__new__(service.RecommendationFactoryV1)
 info=root.stat();factory.settings=SimpleNamespace(current=lambda:deadline,consumers=lambda:(reader,None,None),config=SimpleNamespace(workspace_id=workspace,storage_root=str(root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid))
 item=SimpleNamespace(recommendation_id=selected.recommendation_id,problem='Invented problem',advice={'lens':'operations'})
 monkeypatch.setattr(service,'validate_recommendation_parent',lambda *args:SimpleNamespace(recommendations=(item,)))
 monkeypatch.setattr(service,'ConsolidationCoreV1',SimpleNamespace(model_validate_json=lambda raw:object()))
 monkeypatch.setattr(service,'readable_recommendation_evidence_v1',lambda *a,**kw:{})
 monkeypatch.setattr(factory,'_public',lambda *a:{'invented':True})
 return SimpleNamespace(service=service,fence=fence,tick=tick,wall=wall,deadline=deadline,raw=canonical_bytes(body),selector=selected,status=status,reader=reader,factory=factory,root=root)


@pytest.mark.parametrize('lease',[None,True,'not-time','2026-10-22T12:00:00'])
def test_actual_read_lease_invalid_before_any_private_open(private_lease_case,monkeypatch,lease):
 c=private_lease_case;c.status['valid_until']=lease;opened=[]
 monkeypatch.setattr(c.service,'_parent_fd',lambda *a,**kw:opened.append(a))
 with c.fence._request_fence_v1(130.),pytest.raises(PermissionError,match='aware'):
  c.factory.execute_v1(c.raw)
 assert opened==[] and c.reader.calls==1


def test_source_read_lease_expired_at_sql_return_opens_no_private_bytes(private_lease_case,monkeypatch):
 c=private_lease_case;opened=[];c.status['valid_until']=(c.wall[0]-timedelta(seconds=1)).isoformat()
 monkeypatch.setattr(c.service,'_parent_fd',lambda *a,**kw:opened.append(a))
 with c.fence._request_fence_v1(130.),pytest.raises(PermissionError):c.factory.execute_v1(c.raw)
 assert opened==[]


def test_first_private_body_expiry_blocks_second_body(private_lease_case,monkeypatch):
 c=private_lease_case;original=c.factory._body;read=[]
 def body(manifest):
  result=original(manifest);read.append(manifest.content_hash);c.tick[0]=103.;return result
 monkeypatch.setattr(c.factory,'_body',body)
 with c.fence._request_fence_v1(130.),pytest.raises(PermissionError):c.factory.execute_v1(c.raw)
 assert len(read)==1 and c.reader.calls==1


def test_actual_shorter_lease_survives_read_until_final_encode_even_wall_rollback(private_lease_case,monkeypatch):
 c=private_lease_case
 def public(*args):
  c.tick[0]=103.;c.wall[0]-=timedelta(hours=1)
  return {'invented':True}
 monkeypatch.setattr(c.factory,'_public',public)
 with c.fence._request_fence_v1(130.):
  with pytest.raises(PermissionError,match='fence elapsed'):c.factory.execute_v1(c.raw)
  # ExitStack releases only this execute's restrictions, never the listener's.
  assert c.fence.request_remaining_v1()==27.
 assert c.reader.calls==2


def test_index_cannot_renew_first_items_shorter_lease(private_lease_case,monkeypatch):
 c=private_lease_case;raw=canonical_bytes(dict(schema_version=1,operation='list',caller_deadline=c.deadline.isoformat().replace('+00:00','Z')))
 value=c.selector.model_dump(mode='json');count=[0]
 def listing(**kwargs):return {'selectors':[value,value],'valid_until':c.deadline.isoformat()}
 c.reader.list_v1=listing;original=c.factory._read
 def read(*args):
  result=original(*args);count[0]+=1
  if count[0]==1:
   c.status['valid_until']=c.deadline.isoformat();c.tick[0]=103.;c.wall[0]-=timedelta(hours=1)
  return result
 monkeypatch.setattr(c.factory,'_read',read)
 with c.fence._request_fence_v1(130.),pytest.raises(PermissionError,match='fence elapsed'):c.factory.execute_v1(raw)
 assert count==[1] and c.reader.calls==2


def test_current_actual_local_bodies_and_legacy_outer_fence_work(private_lease_case):
 c=private_lease_case
 with c.fence._request_fence_v1(130.):assert c.factory.execute_v1(c.raw)==b'{"invented":true}'
 assert c.reader.calls==2


def test_postwrite_actual_lease_loss_remains_unknown_without_resend(private_lease_case):
 from types import SimpleNamespace
 from oracle_brain.operating_model.consultant.recommendation_authority_v1 import RecommendationOutcomeUnknown
 c=private_lease_case;body=request('feedback');body['selector']=c.selector.model_dump(mode='json');body['caller_deadline']=c.deadline.isoformat().replace('+00:00','Z');writes=[]
 def feedback(*args,**kwargs):
  writes.append(args);c.tick[0]=103.
  return {'event_id':str(uuid4())}
 c.factory.settings.consumers=lambda:(c.reader,SimpleNamespace(feedback_v1=feedback),None)
 with c.fence._request_fence_v1(130.),pytest.raises(RecommendationOutcomeUnknown,match='never resend'):
  c.factory.execute_v1(canonical_bytes(body))
 assert len(writes)==1 and c.reader.calls==2
