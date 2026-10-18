import os
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).parents[2]
GENERATOR = ROOT / 'scripts/licensing/build_source_offer.mjs'
MANDATORY = ('dev/oracle2/browser/Dockerfile','dev/oracle2/browser/Dockerfile.dockerignore','LICENSE','SOURCE_OFFER.md','THIRD_PARTY_NOTICES.md','README.md','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','turbo.json','vercel.json','dev/oracle2/hosting/Dockerfile','.dockerignore','dev/oracle2/analytics/Dockerfile','dev/oracle2/analytics/Dockerfile.dockerignore','dev/oracle2/analytics/requirements.lock')

def repo(tmp_path):
    (tmp_path/'.gitignore').write_text('apps/web/.source-offer/\n')
    for name in MANDATORY:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('{}\n' if name.endswith('.json') else 'fixture\n')
    (tmp_path/'scripts/licensing').mkdir(parents=True); (tmp_path/'scripts/licensing/build_source_offer.mjs').write_text(GENERATOR.read_text())
    (tmp_path/'services/oracle-brain').mkdir(parents=True); (tmp_path/'services/oracle-brain/uv.lock').write_text('fixture lock\n')
    (tmp_path/'apps/web').mkdir(parents=True); (tmp_path/'apps/web/app.ts').write_text('export const fixture = true;\n'); (tmp_path/'apps/web/proof.d.mts').write_text('export const publicType: string;\n'); (tmp_path/'Dockerfile').write_text('FROM scratch\n'); (tmp_path/'uv.lock').write_text('private fixture\n')
    (tmp_path/'.env.local').write_text('secret\n'); (tmp_path/'uploads').mkdir(); (tmp_path/'uploads/private.txt').write_text('secret\n')
    def git(*args): return subprocess.run(['git',*args],cwd=tmp_path,check=True,capture_output=True,text=True)
    git('init','-q'); git('config','user.email','test@example.com'); git('config','user.name','Test'); git('add','-A'); git('commit','-qm','fixture'); return tmp_path, git

def run(root): return subprocess.run(['node','scripts/licensing/build_source_offer.mjs'],cwd=root,text=True,capture_output=True)

def test_real_archive_is_deterministic_and_excludes_private_data(tmp_path):
    root, _ = repo(tmp_path); first=run(root); assert first.returncode==0, first.stderr; first_bytes=(root/'apps/web/.source-offer/oracle-source.tar.gz').read_bytes(); second=run(root); second_bytes=(root/'apps/web/.source-offer/oracle-source.tar.gz').read_bytes(); assert second.returncode==0, second.stderr; assert first_bytes==second_bytes
    archive=root/'apps/web/.source-offer/oracle-source.tar.gz'; data=json.loads((root/'apps/web/.source-offer/manifest.json').read_text()); assert data['private_data_included'] is False and data['archive_sha256']==hashlib.sha256(second_bytes).hexdigest()
    with tarfile.open(archive,'r:gz') as tar:
        names=tar.getnames(); assert names[-1]=='SOURCE_ARCHIVE_MANIFEST.json' and names[:-1]==sorted(names[:-1]) and '.env.local' not in names and 'uploads/private.txt' not in names; extracted={n:tar.extractfile(n).read() for n in names if n!='SOURCE_ARCHIVE_MANIFEST.json'}
    assert data['files']=={name:hashlib.sha256(value).hexdigest() for name,value in extracted.items()}
    assert 'services/oracle-brain/uv.lock' in extracted
    assert extracted['dev/oracle2/hosting/Dockerfile']==(root/'dev/oracle2/hosting/Dockerfile').read_bytes()
    assert extracted['.dockerignore']==(root/'.dockerignore').read_bytes()
    for name in ('Dockerfile','Dockerfile.dockerignore','requirements.lock'):
        path='dev/oracle2/analytics/'+name
        assert extracted[path]==(root/path).read_bytes()
    assert extracted['apps/web/proof.d.mts']==(root/'apps/web/proof.d.mts').read_bytes()
    for name in ('Dockerfile','Dockerfile.dockerignore'):
        path='dev/oracle2/browser/'+name
        assert extracted[path]==(root/path).read_bytes()
    assert 'Dockerfile' not in extracted  # Unrelated root file remains outside the offer.
    assert data['revision']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    assert data['source_hash']==hashlib.sha256(json.dumps(data['files'],separators=(',',':')).encode()).hexdigest()

def test_dirty_tracked_revision_is_denied(tmp_path):
    root, _=repo(tmp_path); (root/'apps/web/app.ts').write_text('changed\n'); result=run(root); assert result.returncode!=0 and 'Commit source changes before building' in result.stderr

def test_tracked_symlink_is_denied(tmp_path):
    root, git=repo(tmp_path); (root/'apps/web/link.ts').symlink_to('app.ts'); git('add','apps/web/link.ts'); git('commit','-qm','symlink'); result=run(root); assert result.returncode!=0 and 'not a regular project file' in result.stderr

def test_native_build_input_symlink_cannot_publish_external_bytes(tmp_path):
    root,git=repo(tmp_path)
    recipe=root/'dev/oracle2/hosting/Dockerfile'
    recipe.unlink();recipe.symlink_to('../../../uploads/private.txt')
    git('add','dev/oracle2/hosting/Dockerfile');git('commit','-qm','invalid recipe')
    result=run(root)
    assert result.returncode!=0 and 'not a regular project file' in result.stderr
    assert not (root/'apps/web/.source-offer/oracle-source.tar.gz').exists()

def test_exact_dependency_source_payload_and_tamper_denial(tmp_path):
    root,git=repo(tmp_path)
    payload=b'invented dependency source bytes'
    directory=root/'apps/web/.source-offer';directory.mkdir();(directory/'pm4py-2.7.22.tar.gz').write_bytes(payload)
    descriptor={'version':'2.7.22','filename':'pm4py-2.7.22.tar.gz','url':'https://files.pythonhosted.org/invented-source-only','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    (root/'scripts/licensing/pm4py_source.json').write_text(json.dumps(descriptor));git('add','scripts/licensing/pm4py_source.json');git('commit','-qm','descriptor')
    result=run(root);assert result.returncode==0,result.stderr
    with tarfile.open(directory/'oracle-source.tar.gz','r:gz') as tar:
        assert tar.extractfile('third-party/pm4py-2.7.22.tar.gz').read()==payload
        manifest=json.load(tar.extractfile('SOURCE_ARCHIVE_MANIFEST.json'))
        assert manifest['files']['third-party/pm4py-2.7.22.tar.gz']==descriptor['sha256']
    (directory/'pm4py-2.7.22.tar.gz').write_bytes(b'tampered')
    result=run(root);assert result.returncode!=0 and 'Dependency source integrity mismatch' in result.stderr


def test_platform_formatting_recovery_keeps_exact_committed_source(tmp_path):
    root,git=repo(tmp_path)
    config={'framework':'nextjs','buildCommand':'pnpm run build:vercel'}
    original=(json.dumps(config,indent=2)+'\n').encode()
    (root/'vercel.json').write_bytes(original);git('add','vercel.json');git('commit','-qm','config')
    (root/'vercel.json').write_text(json.dumps(dict(reversed(list(config.items()))),separators=(',',':')))
    result=subprocess.run(['node','scripts/licensing/build_source_offer.mjs'],cwd=root,env={**os.environ,'VERCEL':'1'},text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert (root/'vercel.json').read_bytes()==original
    assert not git('status','--porcelain').stdout.strip()
    with tarfile.open(root/'apps/web/.source-offer/oracle-source.tar.gz','r:gz') as tar:
        assert tar.extractfile('vercel.json').read()==original


def test_platform_semantic_change_is_not_recovered(tmp_path):
    root,_=repo(tmp_path);changed=b'{"buildCommand":"unreviewed"}\n';(root/'vercel.json').write_bytes(changed)
    result=subprocess.run(['node','scripts/licensing/build_source_offer.mjs'],cwd=root,env={**os.environ,'VERCEL':'1'},text=True,capture_output=True)
    assert result.returncode!=0 and 'changed keys: buildCommand' in result.stderr
    assert (root/'vercel.json').read_bytes()==changed


def test_platform_recovery_cannot_admit_changed_application_code(tmp_path):
    root,_=repo(tmp_path);(root/'vercel.json').write_text(' { } ');(root/'apps/web/app.ts').write_text('unreviewed application code\n')
    result=subprocess.run(['node','scripts/licensing/build_source_offer.mjs'],cwd=root,env={**os.environ,'VERCEL':'1'},text=True,capture_output=True)
    assert result.returncode!=0 and 'Commit source changes before building' in result.stderr


def test_native_v2_offer_contains_actual_executable_sources_and_fixed_scope(tmp_path):
    # A browser must receive the exact independently reproducible v2 sources,
    # including its JSON dependency and the retained v1 source rather than a
    # generated/minified substitute or an invented fixture with matching names.
    required = (
        'dev/oracle2/native-v2-fixed-identities.json',
        'services/oracle-brain/oracle_brain/operating_model/native_proof_v2_identity.py',
        'services/oracle-brain/oracle_brain/hosting/synthetic_fixture.py',
        'services/oracle-brain/oracle_brain/hosting/native_trigger_v2.py',
        'services/oracle-brain/oracle_brain/hosting/native_trigger_v2_sql.py',
        'services/oracle-brain/oracle_brain/operating_model/sdk_projection.py',
        'services/oracle-brain/sql/016_native_trigger_proof_v2.sql',
        'dev/oracle2/hosting/prepare_native_trigger_v2.py',
        'dev/oracle2/hosting/install_native_trigger_v2.py',
        'dev/oracle2/hosting/project_native_trigger_v2.py',
        'dev/oracle2/hosting/falkor_native_proof_acl_v2.py',
        'apps/web/lib/native-trigger-v2.ts',
        'apps/workers/src/trigger/oracle2-native-invented-v2.ts',
        'apps/workers/trigger.oracle2-native-invented-v2.config.ts',
        'apps/workers/oracle2-requirements.txt',
        'services/oracle-brain/oracle_brain/hosting/native_trigger_v1.py',
        'services/oracle-brain/sql/015_native_trigger_proof.sql',
        'apps/workers/src/trigger/oracle2-native-invented.ts',
    )
    root, git = repo(tmp_path)
    expected = {}
    for name in required:
        original = ROOT / name
        assert original.is_file() and not original.is_symlink(), name
        expected[name] = original.read_bytes()
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected[name])
    git('add', '--', *required)
    git('commit', '-qm', 'actual native v2 and retained v1 source')
    result = run(root)
    assert result.returncode == 0, result.stderr
    with tarfile.open(root / 'apps/web/.source-offer/oracle-source.tar.gz', 'r:gz') as archive:
        manifest = json.load(archive.extractfile('SOURCE_ARCHIVE_MANIFEST.json'))
        for name, original in expected.items():
            delivered = archive.extractfile(name).read()
            assert delivered == original
            assert manifest['files'][name] == hashlib.sha256(original).hexdigest()
        identity = json.load(archive.extractfile('dev/oracle2/native-v2-fixed-identities.json'))
    assert identity['run'] == '6714d4ed-51df-4c38-9155-c456edf7b727'
    assert identity['purpose'] == 'public-invented-trigger-v2'
    assert manifest['revision'] == git('rev-parse', 'HEAD').stdout.strip()
    assert manifest['private_data_included'] is False
