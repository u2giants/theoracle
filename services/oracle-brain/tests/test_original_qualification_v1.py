"""Invented pure metadata only, no original custody or provider authority."""
from datetime import datetime,timedelta,timezone
import hashlib,json
from uuid import uuid4
import pytest
from oracle_brain.operating_model.original_qualification_v1 import parse_original_response_commit_v1


def row(*,paid=False,review=False):
    now=datetime.now(timezone.utc);h=hashlib.sha256(b'original invented correction').hexdigest()
    r={'schema_version':1,'raw_ref':{'schema_version':1,'workspace_id':str(uuid4()),'source_id':str(uuid4()),
        'revision':1,'original_sha256':h,'byte_count':28,'media_type':'application/pdf' if paid else 'text/plain',
        'filename':'invented.pdf' if paid else 'correction.txt','custody_locator_seal_sha256':'1'*64},
        'transport':'paid-native-v1' if paid else 'native-utf8-byte-roundtrip-v1',
        'purpose':'observed-authorized-original-review-response-v1' if review else 'observed-authorized-original-reading-response-v1',
        'original_root_hash':'2'*64,'allocation_hash':'3'*64,'population_hash':'4'*64,
        'source_registry_hash':'5'*64,'context_hash':'6'*64,'view_manifest_hash':'7'*64,'locator_map_hash':'8'*64,
        'reading_sha256':h,'parser_id':'9'*64,'committed_at':now.isoformat(),
        'original_horizon':(now+timedelta(seconds=40)).isoformat(),'reading_body_hash':'a'*64}
    if paid:
        r.update(native_dispatch_id=str(uuid4()),native_job_hash='b'*64,request_hash='c'*64,raw_wire_hash='d'*64,
            model_content_hash='e'*64,native_custody_receipt_hash='f'*64,authorized_phase_commit_hash='0'*64)
    if review:r.update(reading_commit_hash='a'*64,review_body_hash='b'*64,qualification_pass=True)
    return r

@pytest.mark.parametrize('paid',[False,True])
@pytest.mark.parametrize('review',[False,True])
def test_closed_original_transport_and_phase(paid,review):
    r=row(paid=paid,review=review);v=parse_original_response_commit_v1(json.dumps(r).encode(),phase='review' if review else 'reading')
    assert v.reading_sha256!=v.reading_body_hash
    assert not hasattr(v,'actor_id') and not hasattr(v,'reading_hash')

@pytest.mark.parametrize('field',['native_dispatch_id','native_job_hash','request_hash','raw_wire_hash','model_content_hash','native_custody_receipt_hash','authorized_phase_commit_hash','actor_id','login','reading_hash'])
def test_native_text_forbids_paid_or_authority_fields(field):
    r=row();r[field]=str(uuid4()) if field.endswith('_id') else 'c'*64
    with pytest.raises(ValueError):parse_original_response_commit_v1(json.dumps(r).encode(),phase='reading')

@pytest.mark.parametrize('change',['hash','parser','expiry','filename','media','future_ref','disagree'])
def test_invalid_hash_shape_provenance_scope_and_disagreement_deny(change):
    r=row(review=True)
    if change=='hash':r['reading_sha256']='a'*64
    elif change=='parser':r['parser_id']='unqualified'
    elif change=='expiry':r['original_horizon']=r['committed_at']
    elif change=='filename':r['raw_ref']['filename']='../private'
    elif change=='media':r['raw_ref']['media_type']='image/png'
    elif change=='future_ref':r['raw_ref']['reading_sha256']='a'*64
    else:r['qualification_pass']=False
    with pytest.raises(ValueError):parse_original_response_commit_v1(json.dumps(r).encode(),phase='review')


def test_duplicate_and_unknown_transport_refuse():
    r=row();r['transport']='caller-selected'
    with pytest.raises(ValueError):parse_original_response_commit_v1(json.dumps(r).encode(),phase='reading')
    raw=json.dumps(row());raw=raw[:-1]+',"schema_version":1}'
    with pytest.raises(ValueError):parse_original_response_commit_v1(raw.encode(),phase='reading')
