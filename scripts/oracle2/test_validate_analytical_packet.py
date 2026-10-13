import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/oracle2/validate_analytical_packet.py'
spec=importlib.util.spec_from_file_location('analytical_packet',SCRIPT)
validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
FOLDER=ROOT/'dev/oracle2/analytics'

def packet():return json.loads((FOLDER/'source-manifest.json').read_text())
def inspect(value):return validator.inspect_packet(value,(FOLDER/'requirements.lock').read_bytes(),(FOLDER/'Dockerfile').read_bytes(),(FOLDER/'Dockerfile.dockerignore').read_bytes())

def test_complete_public_inventory_never_confers_delivery_or_product_admission():
    result=inspect(packet())
    assert result['artifact_count']==37 and result['total_source_bytes']==267363376
    assert result['chunks']==280 and result['single_artifact_fit'] is False
    assert result['delivery_admitted'] is False and result['product_admission'] is False
    assert any('Windows32' in text for text in result['blockers'])
    assert any('receipt unavailable' in text for text in result['blockers'])

@pytest.mark.parametrize('change',['prune_binary','prune_notice','missing_source','oversized','alias','notice_tamper','recipe_tamper','grant'])
def test_incomplete_or_changed_packet_is_denied(change):
    value=packet();pulp=next(a for a in value['artifacts'] if a['id']=='pulp')
    if change=='prune_binary':pulp['binary_inventory'].pop()
    elif change=='prune_notice':pulp['notices'].pop(next(iter(pulp['notices'])))
    elif change=='missing_source':value['artifacts']=[a for a in value['artifacts'] if a['id']!='pillow']
    elif change=='oversized':value['artifacts'][0]['bytes']=validator.LIMIT+1
    elif change=='alias':value['artifacts'][0]['filename']='../escape.tar.gz'
    elif change=='notice_tamper':next(iter(pulp['notices'].values()))['text']+='changed'
    elif change=='recipe_tamper':value['recipe_sha256']='a'*64
    else:value['rights']['delivery']=True
    with pytest.raises(ValueError):inspect(value)

def test_opaque_receipt_hashes_cannot_self_admit_runtime():
    value=packet();value['required_receipts']={name:'a'*64 for name in value['required_receipts']}
    assert inspect(value)['product_admission'] is False
    value['product_admission']='APPROVE'
    with pytest.raises(ValueError,match='cannot confer'):inspect(value)

def test_default_cli_refuses_delivery_while_inventory_mode_checks_descriptors():
    denied=subprocess.run([sys.executable,str(SCRIPT)],capture_output=True,text=True)
    checked=subprocess.run([sys.executable,str(SCRIPT),'--inventory-only'],capture_output=True,text=True)
    assert denied.returncode==3 and checked.returncode==0
    assert json.loads(denied.stdout)['delivery_admitted'] is False
    assert json.loads(checked.stdout)['delivery_admitted'] is False
