import assert from 'node:assert/strict';
import { mkdtemp,writeFile,symlink,rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { deliverPublicSource } from '../public-source-offer';
const hash=(v:string|Buffer)=>createHash('sha256').update(v).digest('hex');
async function main(){const dir=await mkdtemp(join(tmpdir(),'public-source-'));try{
 const archive=Buffer.from('public invented source test');const files={'README.md':hash('public source')};
 const manifest={schema_version:1,revision:'a'.repeat(40),private_data_included:false,files,source_hash:hash(JSON.stringify(files)),archive_sha256:hash(archive)};
 const save=()=>writeFile(join(dir,'manifest.json'),JSON.stringify(manifest));await save();await writeFile(join(dir,'oracle-source.tar.gz'),archive);
 const request=(query='',headers={})=>new Request('https://native.test/api/consultant/native-acceptance/source'+query,{headers});
 assert.equal((await deliverPublicSource(request(),dir)).status,200);
 assert.equal((await deliverPublicSource(request('?path=../../secret'),dir)).status,400);
 assert.equal((await deliverPublicSource(request('',{'range':'bytes=0-3','if-match':`"${hash(archive)}"`}),dir)).status,206);
 assert.equal((await deliverPublicSource(request('',{'if-match':'"wrong"'}),dir)).status,412);
 await writeFile(join(dir,'oracle-source.tar.gz'),'tampered');assert.equal((await deliverPublicSource(request(),dir)).status,503);
 await rm(join(dir,'oracle-source.tar.gz'));await symlink('/etc/passwd',join(dir,'oracle-source.tar.gz'));assert.equal((await deliverPublicSource(request(),dir)).status,503);
 await rm(join(dir,'oracle-source.tar.gz'));await writeFile(join(dir,'oracle-source.tar.gz'),archive);manifest.private_data_included=true;await save();assert.equal((await deliverPublicSource(request(),dir)).status,503);
 console.log('public source offer: 7 checks passed');
 }finally{await rm(dir,{recursive:true});}}
main().catch(e=>{console.error(e);process.exitCode=1;});
