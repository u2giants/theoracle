#!/usr/bin/env python3
"""Isolated synthetic qualification only. Does not enable any product adapter."""
import argparse,json,os,time,resource,subprocess,sys
from pathlib import Path
from uuid import UUID
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MPLBACKEND']='Agg'
from importlib.metadata import version
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.workflows.process_model import WorkflowModel,Step,Gateway,Transition,Support
from oracle_brain.operating_model.process_analysis.compiler import compile_contract
from oracle_brain.operating_model.process_analysis.pm4py_adapter import build_net

def fixture(kind):
 support=Support(observation_ids=('invented-support',));ref=SourceRef(workspace_id=UUID(int=1),source_id=UUID(int=2),revision=1,original_sha256='a'*64,reading_sha256='b'*64,parser_id='invented')
 def step(identifier,kind='activity'):return Step(step_id=identifier,label='Repeated label',kind=kind,support=support)
 def gateway(identifier,kind):return Gateway(gateway_id=identifier,kind=kind,support=support)
 def edge(a,b,i):return Transition(transition_id='edge'+str(i),from_id=a,to_id=b,support=support,rework=b=='merge')
 steps=[step('start','start'),step('end','end')];gates=[];pairs=[]
 if kind in ('xor','and','deadlock'):
  steps.extend((step('x'),step('y')));gates=[gateway('split','exclusive_split' if kind=='xor' else 'parallel_split'),gateway('join','parallel_join' if kind=='and' else 'exclusive_join')]
  pairs=[('start','split'),('split','x'),('split','y'),('x','join'),('y','join'),('join','end')]
 elif kind=='loop':
  steps.extend((step('a'),step('redo')));gates=[gateway('merge','exclusive_join'),gateway('choice','exclusive_split')]
  pairs=[('start','merge'),('merge','a'),('a','choice'),('choice','redo'),('redo','merge'),('choice','end')]
 elif kind=='bounds':
  previous='start'
  for i in range(25):
   split,join,x,y=(f'split{i}',f'join{i}',f'x{i}',f'y{i}');steps.extend((step(x),step(y)));gates.extend((gateway(split,'parallel_split'),gateway(join,'parallel_join')))
   pairs.extend(((previous,split),(split,x),(split,y),(x,join),(y,join)));previous=join
  for i in range(198):
   name=f'linear{i}';steps.append(step(name));pairs.append((previous,name));previous=name
  pairs.append((previous,'end'))
 return WorkflowModel(workflow_id=kind,version=1,workspace_id=ref.workspace_id,process_id='invented',scope='invented',source_refs=(ref,),completeness='complete',coverage_digest='c'*64,steps=tuple(steps),gateways=tuple(gates),transitions=tuple(edge(a,b,i) for i,(a,b) in enumerate(pairs)))

def replay(net,initial,final,traces):
 import pandas as pd,pm4py
 frame=pd.DataFrame([{'case:concept:name':str(case),'concept:name':activity,'time:timestamp':pd.Timestamp('2026-10-11',tz='UTC')+pd.Timedelta(seconds=i)} for case,trace in enumerate(traces) for i,activity in enumerate(trace)])
 rows=pm4py.conformance_diagnostics_token_based_replay(frame,net,initial,final,return_diagnostics_dataframe=False)
 return [bool(row['trace_is_fit']) for row in rows]

def measure():
 resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(30,30))
 start=time.monotonic();import pm4py
 assert version('pm4py')=='2.7.22'
 results={}
 for kind in ('xor','and','loop','deadlock','bounds'):
  print('Measuring '+kind,file=sys.stderr,flush=True)
  model=fixture(kind);contract=compile_contract(model);assert contract['state']=='compiled';assert set(contract['step_map'])=={s.step_id for s in model.steps};assert set(contract['transition_map'])=={e.transition_id for e in model.transitions}
  net,initial,final=build_net(contract,kind)
  try:sound,_=pm4py.check_soundness(net,initial,final)
  except MemoryError:
   results[kind]={'state':'incomplete','reason':'memory_exhaustion','original_map_retained':contract['model']==model.model_dump(mode='json'),'steps':len(model.steps),'gateways':len(model.gateways),'edges':len(model.transitions)}
   continue
  assert bool(sound)==(kind!='deadlock')
  if kind=='xor':assert replay(net,initial,final,[['start','x','end'],['start','y','end'],['start','x','y','end']])==[True,True,False]
  if kind=='and':assert replay(net,initial,final,[['start','x','y','end'],['start','y','x','end'],['start','x','end']])==[True,True,False]
  if kind=='loop':assert replay(net,initial,final,[['start','a','end'],['start','a','redo','a','end'],['start','redo','end']])==[True,True,False]
  results[kind]={'sound':bool(sound),'steps':len(model.steps),'gateways':len(model.gateways),'edges':len(model.transitions)}
 # Discovery is observed execution, never a documented policy replacement.
 import pandas as pd
 frame=pd.DataFrame([{'case:concept:name':str(c),'concept:name':a,'time:timestamp':pd.Timestamp('2026-10-11',tz='UTC')+pd.Timedelta(seconds=i)} for c,trace in enumerate((('start','x','end'),('start','y','end'))) for i,a in enumerate(trace)])
 net,initial,final=pm4py.discover_petri_net_inductive(frame,noise_threshold=0.0,multi_processing=False)
 assert {t.label for t in net.transitions if t.label}=={'start','x','y','end'}
 return {'version':version('pm4py'),'synthetic':True,'company_truth_accepted':False,'product_enabled':False,'fixtures':results,'discovery_activity_ids':['end','start','x','y'],'elapsed_seconds':time.monotonic()-start,'cpu_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'limits':{'as_bytes':512*1024*1024,'cpu_seconds':30}}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--measurement-only',action='store_true',required=True);parser.parse_args();print(json.dumps(measure(),sort_keys=True))
