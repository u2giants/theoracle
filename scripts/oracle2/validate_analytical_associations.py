"""Bounded nonexecuting association checks; never an admission or downloader."""
import hashlib,importlib.util,json,re
from pathlib import Path
_spec=importlib.util.spec_from_file_location('analytical_packet_validator',Path(__file__).with_name('validate_analytical_packet.py'))
packet_validator=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(packet_validator)
LIMIT=1024*1024
REQUIRED_COMPONENTS={'cvxopt': ['OpenBLAS', 'DSDP', 'GLPK', 'GSL', 'FFTW'], 'scipy': ['fast_matrix_market', 'pystreambuf', 'fast_float', 'ryu', 'L-BFGS-B', 'LAPJVsp', 'SuperLU', 'ARPACK', 'Qhull', 'xsf', 'pyduccfft', 'ducc0', 'uarray', 'ampgo', 'pybind11', 'HiGHS', 'Boost', 'Biasedurn', 'UNU.RAN', 'NumPy', 'array-api-compat', 'array-api-extra', 'Tempita', 'Chebfun', 'getLebedevSphere', 'prima', 'packaging.version']}
SCIPY_DOCUMENT_SHA256='45b1a2cf4eb57277812fcbca2b6af7d84e98c942a5e4dcc360610f49de16c63f'
FIELDS={'schema_version','scope','target','source_manifest_sha256','primary_sources','packages','cbc_binaries','preserved_notice_sha256','source_qualified','delivery_admitted','product_admission','runtime_qualified'}
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
def decode(raw):
    require(type(raw) is bytes and len(raw)<=LIMIT,'bounded public metadata required')
    def unique(rows):
        out={}
        for k,v in rows:require(k not in out,'duplicate association metadata field');out[k]=v
        return out
    try:return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite association metadata')))
    except (RecursionError,UnicodeDecodeError):raise ValueError('bounded well-formed public metadata required') from None
def lock_records(raw):
    require(type(raw) is bytes and len(raw)<=LIMIT,'bounded exact lock required')
    records={};current=None
    for line in raw.decode('ascii').splitlines():
        match=re.match(r'^([a-z0-9-]+)==(\S+)',line)
        if match:
            current=match[1];require(current not in records,'duplicate locked package');records[current]={'version':match[2],'hashes':set()}
        elif current:
            records[current]['hashes'].update(re.findall(r'--hash=sha256:([a-f0-9]{64})',line))
    return records

def inspect_associations(matrix_bytes,manifest_bytes,lock_bytes,recipe_bytes,context_bytes):
    require(all(type(x) is bytes and len(x)<=LIMIT for x in (recipe_bytes,context_bytes)),'bounded recipe/context required')
    matrix=decode(matrix_bytes);packet=decode(manifest_bytes)
    require(type(packet) is dict,'exact source packet object required')
    # Reuse fixed37/6/7 source packet bounds and immutable code/lock identities.
    base=packet_validator.inspect_packet(packet,lock_bytes,recipe_bytes,context_bytes)
    require(type(matrix) is dict and set(matrix)==FIELDS and type(matrix['schema_version']) is int and matrix['schema_version']==1 and matrix['scope']=='analytical-candidate-source-associations-only','exact inert association schema required')
    require(all(matrix[k] is False for k in ('source_qualified','delivery_admitted','product_admission','runtime_qualified')),'metadata cannot grant qualification or delivery')
    require(matrix['target']=={'python':'CPython3.12','os':'linux','architecture':'amd64'} and matrix['source_manifest_sha256']==sha(manifest_bytes),'target/whole source packet differs')
    require(matrix['primary_sources']=={'cvxopt_linux_wheels':'https://cvxopt.org/install/','scipy_bundled_url':'https://raw.githubusercontent.com/scipy/scipy/v1.18.1/LICENSES_bundled.txt','scipy_bundled_document_sha256':SCIPY_DOCUMENT_SHA256},'fixed primary source evidence differs')
    source={a['id']:a for a in packet['artifacts']};packages=[a for a in packet['artifacts'] if a['url'].startswith('https://files.pythonhosted.org/')]
    require(len(source)==37 and len(packages)==33,'complete unchanged supplier population required')
    rows=matrix['packages'];require(type(rows) is list and [r['package'] for r in rows]==[a['id'] for a in packages],'complete fixed package order required')
    locked=lock_records(lock_bytes);missing_wheels=[];missing_components=[];declared_wheels=0;declared_components=0
    for row,a in zip(rows,packages):
        require(type(row) is dict and set(row)=={'package','version','sdist_sha256','pypi_metadata_url','pypi_metadata_sha256','actual_wheel','components'},'exact package association record required')
        name=a['id'];require(row['version']==a['version']==locked[name]['version'] and row['sdist_sha256']==a['sha256'],'sdist/locked version association differs')
        require(row['pypi_metadata_url']=='https://pypi.org/pypi/'+name+'/'+a['version']+'/json' and digest(row['pypi_metadata_sha256']),'fixed publisher metadata identity required')
        wheel=row['actual_wheel']
        if wheel is None:missing_wheels.append(name)
        else:
            require(type(wheel) is dict and set(wheel)=={'filename','sha256','bytes'} and type(wheel['bytes']) is int and 0<wheel['bytes']<=packet_validator.LIMIT,'bounded candidate wheel identity required')
            require(isinstance(wheel['filename'],str) and re.fullmatch(r'[A-Za-z0-9_.+-]{1,220}\.whl',wheel['filename']) and wheel['filename'].startswith(name.replace('-','_')+'-'+a['version']+'-'),'fixed wheel package/version filename required')
            require(digest(wheel['sha256']) and wheel['sha256'] in locked[name]['hashes'],'candidate wheel hash outside package lock')
            declared_wheels+=1
        components=row['components'];require(type(components) is list and [c['component'] for c in components]==REQUIRED_COMPONENTS.get(name,[]),'complete fixed supplier component inventory required')
        for component in components:
            require(type(component) is dict and set(component)=={'component','association'},'exact component record required')
            association=component['association']
            if association is None:missing_components.append(name+':'+component['component']);continue
            require(type(association) is dict and set(association)=={'version','source_artifact_id','source_sha256','notice_paths','build_association_sha256'},'complete candidate source/notice/build fields required')
            require(isinstance(association['version'],str) and re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}',association['version']),'candidate component version required')
            parent=source.get(association['source_artifact_id']);require(parent is not None and association['source_sha256']==parent['sha256'],'candidate component source outside unchanged37 artifacts')
            notices=association['notice_paths'];require(type(notices) is list and notices and len(notices)==len(set(notices)) and set(notices)<=set(parent['notices']) and digest(association['build_association_sha256']),'complete candidate notice/build association required')
            declared_components+=1
    pulp=source['pulp'];binaries=matrix['cbc_binaries']
    require(type(binaries) is list and len(binaries)==6 and all(type(b) is dict and set(b)=={'path','sha256','actual_build_association'} for b in binaries),'complete six-binary association population required')
    require([(b['path'],b['sha256']) for b in binaries]==[(b['path'],b['sha256']) for b in pulp['binary_inventory']],'distributed CBC binary inventory differs')
    require(matrix['preserved_notice_sha256']=={name:n['sha256'] for name,n in pulp['notices'].items()} and len(matrix['preserved_notice_sha256'])==7,'all seven intact notice identities required')
    missing_cbc=[]
    for b in binaries:
        claim=b['actual_build_association']
        if claim is None:missing_cbc.append(b['path'])
        else:
            require(type(claim) is dict and set(claim)=={'source_artifact_id','source_sha256','build_association_sha256'} and claim['source_artifact_id'] in source and claim['source_sha256']==source[claim['source_artifact_id']]['sha256'] and digest(claim['build_association_sha256']),'candidate CBC association outside source packet')
    # Non-null candidate fields/hashes are declarations, NEVER authentic receipts.
    return {'scope':'source-association-preparation-only','artifact_count':37,'package_count':33,'cbc_binaries':6,'preserved_notices':7,'missing_wheel_identity_fields':missing_wheels,'actual_wheel_selection_authenticated':False,'actual_build_associations_authenticated':False,'missing_component_associations':missing_components,'missing_cbc_build_associations':missing_cbc,'declared_candidate_wheels':declared_wheels,'declared_candidate_components':declared_components,'source_qualified':False,'delivery_admitted':False,'product_admission':False,'runtime_qualified':False,'independent_receipts_unavailable':True,'packet_blockers':base['blockers']}

def deny_unqualified_delivery(matrix_bytes,manifest_bytes,lock_bytes,recipe_bytes,context_bytes):
    inspect_associations(matrix_bytes,manifest_bytes,lock_bytes,recipe_bytes,context_bytes)
    raise PermissionError('source-only declarations cannot authorize analytical delivery; independent actual wheel/source/notice/product qualification required')
