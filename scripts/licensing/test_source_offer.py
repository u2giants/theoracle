import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).parents[2]
GENERATOR = ROOT / 'scripts/licensing/build_source_offer.mjs'
MANDATORY = ('LICENSE','SOURCE_OFFER.md','THIRD_PARTY_NOTICES.md','README.md','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','turbo.json','vercel.json')

def repo(tmp_path):
    for name in MANDATORY: (tmp_path/name).write_text('{}\n' if name.endswith('.json') else 'fixture\n')
    (tmp_path/'scripts/licensing').mkdir(parents=True); (tmp_path/'scripts/licensing/build_source_offer.mjs').write_text(GENERATOR.read_text())
    (tmp_path/'services/oracle-brain').mkdir(parents=True); (tmp_path/'services/oracle-brain/uv.lock').write_text('fixture lock\n')
    (tmp_path/'apps/web').mkdir(parents=True); (tmp_path/'apps/web/app.ts').write_text('export const fixture = true;\n'); (tmp_path/'Dockerfile').write_text('FROM scratch\n'); (tmp_path/'uv.lock').write_text('private fixture\n')
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
    assert data['revision']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    assert data['source_hash']==hashlib.sha256(json.dumps(data['files'],separators=(',',':')).encode()).hexdigest()

def test_dirty_tracked_revision_is_denied(tmp_path):
    root, _=repo(tmp_path); (root/'apps/web/app.ts').write_text('changed\n'); result=run(root); assert result.returncode!=0 and 'Commit source changes before building' in result.stderr

def test_tracked_symlink_is_denied(tmp_path):
    root, git=repo(tmp_path); (root/'apps/web/link.ts').symlink_to('app.ts'); git('add','apps/web/link.ts'); git('commit','-qm','symlink'); result=run(root); assert result.returncode!=0 and 'not a regular project file' in result.stderr
