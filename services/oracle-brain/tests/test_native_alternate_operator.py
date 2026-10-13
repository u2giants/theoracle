"""Invented byte streams only; no native authority or private capture issued."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from oracle_brain.operating_model.native_alternate import serialize_docling

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('operator',ROOT/'scripts/oracle2/native_alternate_operator.py')
operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)


def case():
    box=dict(l=0,r=10,t=10,b=0,coord_origin='BOTTOMLEFT')
    document=dict(schema_name='DoclingDocument',version='1.10.0',pages={'1':{'page_no':1}},
        texts=[dict(self_ref='#/texts/0',text='Invented Ω approval',prov=[dict(page_no=1,bbox=box,charspan=[0,99])])])
    inputs=[json.dumps(document).encode(),b'{"original_hashes":["invented"]}']
    control=dict(profile='oracle-native-alternate-serialization-v1',purpose='native-alternate-serialization',expires_at=200,
        capture_count=1,runtime_bytes=1,census={'native_pages':1,'native_groups':1},inputs=[dict(sha256=hashlib.sha256(raw).hexdigest(),original_hash='a'*64,
            stat={'size':len(raw)}) for raw in inputs])
    reads=[];writes={}
    def reader(index,maximum):reads.append(index);return inputs[index][:maximum]
    return control,inputs,reads,writes,reader


def test_byte_exact_one_pass_unqualified_output():
    control,inputs,reads,writes,reader=case()
    result=operator.serialize_inputs(control,reader,lambda i,b:writes.update({i:b}),serialize_docling,clock=lambda:100)
    assert reads==[0,1] and result['artifact_count']==1
    assert not result['source_qualified'] and not result['ledger_adopted']
    alternate=json.loads(writes[0]);assert alternate['text']=='Invented Ω approval'
    assert alternate['segments'][0]['native_provenance'][0]['charspan']==[0,99]


@pytest.mark.parametrize('damage',['purpose','expired','hash','size','input_bound','schema'])
def test_guarded_transformation_refuses_and_never_qualifies(damage):
    control,inputs,reads,writes,reader=case()
    if damage=='purpose':control['purpose']='source-extraction'
    elif damage=='expired':control['expires_at']=100
    elif damage=='hash':control['inputs'][0]['sha256']='b'*64
    elif damage=='size':control['inputs'][0]['stat']['size']+=1
    elif damage=='input_bound':control['runtime_bytes']=operator.LIMIT
    else:
        value=json.loads(inputs[0]);value['version']='unknown';inputs[0]=json.dumps(value).encode()
        control['inputs'][0].update(sha256=hashlib.sha256(inputs[0]).hexdigest(),stat={'size':len(inputs[0])})
    with pytest.raises(ValueError):operator.serialize_inputs(control,reader,lambda i,b:writes.update({i:b}),serialize_docling,clock=lambda:100)
    assert not writes


def test_standalone_worker_refuses_before_private_paths_or_input_reads():
    result=subprocess.run([sys.executable,str(ROOT/'scripts/oracle2/native_alternate_operator.py')],input=b'',capture_output=True)
    assert result.returncode!=0 and b'Invented' not in result.stderr


def test_output_bound_and_expiry_during_decoding():
    control,inputs,reads,writes,reader=case()
    def overlarge(*a,**kw):return {'status':'unqualified-native-alternate-v1','source_qualified':False,'ledger_adopted':False,'pages':{'1':{}},'text':'x'*1000}
    before=operator.LIMIT
    try:
        operator.LIMIT=500
        with pytest.raises(ValueError):operator.serialize_inputs(control,reader,lambda i,b:writes.update({i:b}),overlarge,clock=lambda:100)
    finally:operator.LIMIT=before
    assert not writes
