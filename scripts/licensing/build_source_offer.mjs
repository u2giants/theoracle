// Deterministic corresponding-source archive; secrets and business data are excluded.
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync, writeFileSync, lstatSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const destination = resolve(root, 'apps/web/.source-offer');
const mandatory = ['LICENSE','SOURCE_OFFER.md','THIRD_PARTY_NOTICES.md','README.md','package.json','pnpm-lock.yaml','pnpm-workspace.yaml','turbo.json','vercel.json','services/oracle-brain/uv.lock'];
const codeRoots = ['apps/','packages/','services/','scripts/','migrations/','.github/','dev/oracle2/','evals/oracle2/workflow/'];
const special = ['docs/deployment.md','docs/configuration.md','docs/development.md'];
// Recover only Vercel's formatting-only rewrite of the tracked configuration.
// Every setting must remain identical; custom source changes still fail below.
if (process.env.VERCEL === '1') {
  const configPath=resolve(root,'vercel.json');
  if (!lstatSync(configPath).isFile() || lstatSync(configPath).isSymbolicLink()) throw new Error('Platform config must be a regular project file');
  const committed=execFileSync('git',['show','HEAD:vercel.json'],{cwd:root});
  const actual=readFileSync(configPath);
  if (!actual.equals(committed)) {
    const canonical=value=>Array.isArray(value)?value.map(canonical):value && typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
    const expected=JSON.parse(committed.toString('utf8')),observed=JSON.parse(actual.toString('utf8'));
    if (JSON.stringify(canonical(expected)) !== JSON.stringify(canonical(observed))) {
      const changed=Array.from(new Set([...Object.keys(expected),...Object.keys(observed)])).filter(key=>JSON.stringify(canonical(expected[key]))!==JSON.stringify(canonical(observed[key])));
      throw new Error('Platform config settings differ from reviewed source; changed keys: '+changed.slice(0,20).join(', '));
    }
    writeFileSync(configPath,committed);
  }
}
// Release archives must correspond to a clean committed source tree.
const dirty = execFileSync('git',['status','--porcelain','--untracked-files=all'],{cwd:root,encoding:'utf8'}).trim();
if (dirty) {
  const trackedChanges = execFileSync('git',['diff','--name-only','HEAD'],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(Boolean);
  throw new Error('Commit source changes before building the source offer; tracked changes: '+trackedChanges.slice(0,10).join(', ')+'; untracked count: '+dirty.split('\n').filter(line=>line.startsWith('?? ')).length);
}
const tracked = execFileSync('git',['ls-files','-z'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean);
const source = tracked.filter(path => !path.split('/').some(part => ['node_modules','.source-offer','.ai','test-results','uploads','uploaded-files','.env.local','.env','coverage','.next','.trigger','.vercel','dist','out','build'].includes(part)) && (mandatory.includes(path)||special.includes(path)||codeRoots.some(prefix=>path.startsWith(prefix))) && /\.(ts|tsx|js|jsx|mjs|cjs|py|json|toml|yaml|yml|sql|sh|css|md|txt|svg|lock|ps1)$/.test(path));
for(const path of mandatory)if(!source.includes(path))source.push(path);
source.sort();
const entries=[];const hashes={};
for(const path of source){const absolute=resolve(root,path);if(!absolute.startsWith(root+'/')||!lstatSync(absolute).isFile()||lstatSync(absolute).isSymbolicLink())throw new Error('Source archive path is not a regular project file');const bytes=readFileSync(absolute);hashes[path]=createHash('sha256').update(bytes).digest('hex');entries.push([path,bytes]);}
const revision=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
// Corresponding dependency source is offered even while product analytics remains disabled.
const descriptorPath='scripts/licensing/pm4py_source.json';
if(tracked.includes(descriptorPath)){
  const spec=JSON.parse(readFileSync(resolve(root,descriptorPath),'utf8'));
  if(spec.version!=='2.7.22'||!/^https:\/\/files\.pythonhosted\.org\//.test(spec.url)||!/^pm4py-2\.7\.22\.tar\.gz$/.test(spec.filename)||!/^[0-9a-f]{64}$/.test(spec.sha256)||spec.bytes>20000000)throw new Error('Dependency source descriptor not admitted');
  mkdirSync(destination,{recursive:true});let bytes;
  try{bytes=readFileSync(resolve(destination,spec.filename));}catch(error){if(error.code!=='ENOENT')throw error;const response=await fetch(spec.url,{signal:AbortSignal.timeout(30000),redirect:'error'});if(!response.ok)throw new Error('Dependency source unavailable');bytes=Buffer.from(await response.arrayBuffer());}
  if(bytes.length!==spec.bytes||createHash('sha256').update(bytes).digest('hex')!==spec.sha256)throw new Error('Dependency source integrity mismatch');
  writeFileSync(resolve(destination,spec.filename),bytes);
  const dependencyPath='third-party/'+spec.filename;hashes[dependencyPath]=spec.sha256;entries.push([dependencyPath,bytes]);
}
const manifest={schema_version:1,revision,files:hashes,source_hash:createHash('sha256').update(JSON.stringify(hashes)).digest('hex'),private_data_included:false};
entries.push(['SOURCE_ARCHIVE_MANIFEST.json',Buffer.from(JSON.stringify(manifest,null,2)+'\n')]);
function tarEntry(path,bytes){
  const header=Buffer.alloc(512);let name=path,prefix='';
  if(Buffer.byteLength(name)>100){const at=name.lastIndexOf('/');prefix=name.slice(0,at);name=name.slice(at+1);if(Buffer.byteLength(name)>100||Buffer.byteLength(prefix)>155)throw new Error('Source path exceeds archive format bounds');}
  header.write(name,0,100);header.write('0000644\0',100,8);header.write('0000000\0',108,8);header.write('0000000\0',116,8);header.write(bytes.length.toString(8).padStart(11,'0')+'\0',124,12);header.write('00000000000\0',136,12);header.fill(32,148,156);header.write('0',156);header.write('ustar\0',257,6);header.write('00',263,2);header.write(prefix,345,155);
  const checksum=header.reduce((sum,value)=>sum+value,0);header.write(checksum.toString(8).padStart(6,'0')+'\0 ',148,8);
  return [header,bytes,Buffer.alloc((512-bytes.length%512)%512)];
}
const archive=gzipSync(Buffer.concat([...entries.flatMap(([path,bytes])=>tarEntry(path,bytes)),Buffer.alloc(1024)]),{mtime:0});
mkdirSync(destination,{recursive:true});writeFileSync(resolve(destination,'oracle-source.tar.gz'),archive);writeFileSync(resolve(destination,'manifest.json'),JSON.stringify({...manifest,archive_sha256:createHash('sha256').update(archive).digest('hex')})+'\n');
console.log(JSON.stringify({source_files:source.length,archive_bytes:archive.length,revision,private_data_included:false}));
