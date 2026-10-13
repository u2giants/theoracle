"""Invented metadata edits only; no supplier bytes, qualification or delivery."""
import copy,importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('association_validator',ROOT/'scripts/oracle2/validate_analytical_associations.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
FOLDER=ROOT/'dev/oracle2/analytics'
def matrix():return json.loads((ROOT/'scripts/oracle2/contracts/analytical_source_associations.json').read_bytes())
def inputs(value):return (json.dumps(value).encode(),(FOLDER/'source-manifest.json').read_bytes(),(FOLDER/'requirements.lock').read_bytes(),(FOLDER/'Dockerfile').read_bytes(),(FOLDER/'Dockerfile.dockerignore').read_bytes())
def test_complete_descriptors_remain_unavailable():
 r=v.inspect_associations(*inputs(matrix()))
 assert (r['artifact_count'],r['package_count'],r['cbc_binaries'],r['preserved_notices'])==(37,33,6,7)
 assert len(r['missing_wheel_identity_fields'])==33 and len(r['missing_component_associations'])==32 and len(r['missing_cbc_build_associations'])==6
 assert all(r[k] is False for k in ('source_qualified','delivery_admitted','product_admission','runtime_qualified'))
 with pytest.raises(PermissionError):v.deny_unqualified_delivery(*inputs(matrix()))
@pytest.mark.parametrize('damage',['flag','scope','sourcehash','omittedpackage','duplicatepackage','packageorder','version','sdist','metadataurl','missingcvxopt','missingscipy','componentorder','partialassociation','unknownsource','binaryomit','binaryhash','noticeomit','noticehash','primarysource','wheelhash','wheelfilename'])
def test_missing_mismatched_partial_matrix_never_reaches_delivery(damage):
 m=matrix();cv=next(r for r in m['packages'] if r['package']=='cvxopt');sc=next(r for r in m['packages'] if r['package']=='scipy')
 if damage=='flag':m['source_qualified']=True
 elif damage=='scope':m['target']['architecture']='arm64'
 elif damage=='sourcehash':m['source_manifest_sha256']='0'*64
 elif damage=='omittedpackage':m['packages'].pop()
 elif damage=='duplicatepackage':m['packages'][1]=copy.deepcopy(m['packages'][0])
 elif damage=='packageorder':m['packages'].reverse()
 elif damage=='version':cv['version']='0.0'
 elif damage=='sdist':cv['sdist_sha256']='0'*64
 elif damage=='metadataurl':cv['pypi_metadata_url']='https://foreign.invalid'
 elif damage=='missingcvxopt':cv['components'].pop()
 elif damage=='missingscipy':sc['components'].pop()
 elif damage=='componentorder':sc['components'].reverse()
 elif damage=='partialassociation':cv['components'][0]['association']={'version':'INVENTED'}
 elif damage=='unknownsource':cv['components'][0]['association']={'version':'INVENTED','source_artifact_id':'unproved-openblas','source_sha256':'a'*64,'notice_paths':['fake'],'build_association_sha256':'a'*64}
 elif damage=='binaryomit':m['cbc_binaries'].pop()
 elif damage=='binaryhash':m['cbc_binaries'][0]['sha256']='0'*64
 elif damage=='noticeomit':m['preserved_notice_sha256'].pop(next(iter(m['preserved_notice_sha256'])))
 elif damage=='noticehash':m['preserved_notice_sha256'][next(iter(m['preserved_notice_sha256']))]='0'*64
 elif damage=='primarysource':m['primary_sources']['scipy_bundled_document_sha256']='0'*64
 elif damage=='wheelhash':cv['actual_wheel']={'filename':'cvxopt-1.3.3-cp312-cp312-manylinux_x86_64.whl','sha256':'0'*64,'bytes':1}
 else:cv['actual_wheel']={'filename':'../cvxopt-1.3.3.whl','sha256':'0'*64,'bytes':1}
 with pytest.raises((ValueError,PermissionError)):v.deny_unqualified_delivery(*inputs(m))

def test_opaque_candidate_hashes_cannot_mint_qualification():
 m=matrix();packet=json.loads((FOLDER/'source-manifest.json').read_bytes());source=next(a for a in packet['artifacts'] if a['id']=='cvxopt');assoc={'version':'INVENTED','source_artifact_id':'cvxopt','source_sha256':source['sha256'],'notice_paths':list(source['notices']),'build_association_sha256':'a'*64}
 for row in m['packages']:
  for c in row['components']:c['association']=copy.deepcopy(assoc)
 for b in m['cbc_binaries']:b['actual_build_association']={'source_artifact_id':'cvxopt','source_sha256':source['sha256'],'build_association_sha256':'b'*64}
 r=v.inspect_associations(*inputs(m));assert r['declared_candidate_components']==32 and r['source_qualified'] is False
 with pytest.raises(PermissionError):v.deny_unqualified_delivery(*inputs(m))

@pytest.mark.parametrize('raw',[b'{}',b'[]',b'{"schema_version":1,"schema_version":1}',b'{"bad":NaN}',b'x'*(v.LIMIT+1)])
def test_bounded_strict_public_json_denial(raw):
 with pytest.raises((ValueError,TypeError)):
  v.inspect_associations(raw,*inputs(matrix())[1:])

def test_declared_lock_hash_never_proves_actual_wheel_or_sources():
 m=matrix();row=next(r for r in m['packages'] if r['package']=='cvxopt');locked=v.lock_records((FOLDER/'requirements.lock').read_bytes())
 row['actual_wheel']={'filename':'cvxopt-1.3.3-cp312-cp312-manylinux_x86_64.whl','sha256':next(iter(locked['cvxopt']['hashes'])),'bytes':1}
 assert v.inspect_associations(*inputs(m))['declared_candidate_wheels']==1
 with pytest.raises(PermissionError):v.deny_unqualified_delivery(*inputs(m))


def test_boolean_schema_cannot_substitute_for_version():
 m=matrix();m['schema_version']=True
 with pytest.raises(ValueError):v.inspect_associations(*inputs(m))


def test_association_suite_is_mandatory_not_silently_omitted():
 import runpy
 required=runpy.run_path(str(ROOT/'scripts/oracle2/verify_workflow_integrity.py'))['required_suites']
 for stage in ('W04','W07','W08','W10','all'):assert 'analytical_associations' in required(stage)
