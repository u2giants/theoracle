// Only resources referenced by this exact built page are admitted to ingress.
import { readFileSync, writeFileSync, existsSync, realpathSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const root=resolve(import.meta.dirname,'../../..');
const web=resolve(root,'apps/web');
const revision=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
const html=readFileSync(resolve(web,'.next/server/app/consultant/native-acceptance.html'),'utf8');
const pending=new Set([...html.matchAll(/(?:src|href)="(\/_next\/static\/[^"?#]+)(?:\?[^"#]*)?"/g)].map(match=>match[1]));
if(!pending.size)throw Error('Native page emitted no admitted resources');
const assets=[];
for(const asset of pending){
  if(!/^\/_next\/static\/[a-zA-Z0-9_./~-]+$/.test(asset)||asset.includes('..'))throw Error('Invalid built resource: '+asset);
  const path=resolve(web,'.next/static',asset.slice('/_next/static/'.length));
  if(!path.startsWith(resolve(web,'.next/static')+'/')||realpathSync(path)!==path)throw Error('Invalid built resource: '+asset);
  const bytes=readFileSync(path);
  assets.push({path:asset,sha256:createHash('sha256').update(bytes).digest('hex')});
  if(asset.endsWith('.css'))for(const match of bytes.toString('utf8').matchAll(/url\(["']?([^)'"?#]+)(?:\?[^)'"#]*)?["']?\)/g)){
    const target=new URL(match[1],'https://native.invalid'+asset).pathname;
    if(target.startsWith('/_next/static/'))pending.add(target);
    else throw Error('Native stylesheet requires an unadmitted resource');
  }
}
assets.sort((a,b)=>a.path.localeCompare(b.path));
writeFileSync(resolve(web,'.next/native-browser-static.json'),JSON.stringify({schema_version:1,source_revision:revision,assets})+'\n');
const out=resolve(web,'.next/native-browser-bootstrap');
if(!existsSync(out))throw Error('Bootstrap missing');
// Native ESM uses the same postgres import branch traced by Next. Add only
// these two fixed local output suffixes; no caller-selected module rewriting.
for(const [file,before,after] of [['native-browser-boot.js',"from './native-acceptance'","from './native-acceptance.js'"],['native-acceptance.js',"from './oracle2-postgres'","from './oracle2-postgres.js'"]]){
  const path=resolve(out,file),source=readFileSync(path,'utf8');
  if(source.split(before).length!==2)throw Error('Native bootstrap import shape changed');
  writeFileSync(path,source.replace(before,after));
}
writeFileSync(resolve(out,'package.json'),'{"type":"module"}\n');
console.log(JSON.stringify({revision,admitted_static_assets:assets.length}));
