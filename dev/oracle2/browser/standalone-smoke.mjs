// Pure public-invented source rehearsal, never startup admission or live proof.
// No volumes, published ports, real credentials, or network membership.
import {execFileSync,spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {compileIngress} from './compile-ingress.mjs';
const image='oracle-native-browser:source-candidate';
const read=script=>JSON.parse(execFileSync('docker',['run','--rm','--network','none','--read-only','--cap-drop','ALL','--entrypoint','node',image,'-e',script],{encoding:'utf8',timeout:15000}));
const identity=read("const fs=require('fs');const m=JSON.parse(fs.readFileSync('/app/native-browser-static.json'));const s=JSON.parse(fs.readFileSync('/app/apps/web/.source-offer/manifest.json'));console.log(JSON.stringify({revision:m.source_revision,sourceRevision:s.revision,asset:m.assets[0].path,sourceHash:s.archive_sha256,privateData:s.private_data_included,staticBytes:fs.readFileSync('/app/native-browser-static.json').toString('base64'),sourceBytes:fs.readFileSync('/app/apps/web/.source-offer/manifest.json').toString('base64')}));");
const repoDigests=JSON.parse(execFileSync('docker',['image','inspect',image,'--format','{{json .RepoDigests}}'],{encoding:'utf8',timeout:15000}));
const imageDigest=repoDigests.length===1?repoDigests[0].split('@')[1]:process.env.ORACLE_NATIVE_BROWSER_REHEARSAL_DIGEST;
assert.match(imageDigest??'',/^sha256:[a-f0-9]{64}$/);
assert.match(identity.revision,/^[a-f0-9]{40}$/);assert.equal(identity.sourceRevision,identity.revision);assert.equal(identity.privateData,false);
for(const [extra,status] of [[[],78],[['--env','ORACLE2_NATIVE_BROWSER_ONLY=1'],1],[['--env','ORACLE2_NATIVE_BROWSER_ONLY=1','--env','NODE_OPTIONS=--inspect'],78]]){
  const result=spawnSync('docker',['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',...extra,image],{encoding:'utf8',timeout:15000});
  assert.equal(result.status,status);if(status===1)assert.equal(result.stderr.trim(),'Native invented browser startup denied.');
}
// Override only for this deliberately unadmitted fixture so actual Next request
// interception can be proved separately from sealed startup/PG admission.
const host='invented-native.example.invalid';
const staticBytes=Buffer.from(identity.staticBytes,'base64'),sourceBytes=Buffer.from(identity.sourceBytes,'base64');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const ingress=compileIngress({staticBytes,sourceBytes,association:{schema_version:1,source_revision:identity.revision,image_digest:imageDigest,static_manifest_sha256:sha(staticBytes),source_offer_manifest_sha256:sha(sourceBytes),source_archive_sha256:identity.sourceHash,public_artifact_only:true},publicHost:host,expectedRevision:identity.revision,expectedImageDigest:imageDigest,composeTemplate:readFileSync(new URL('./coolify-companion.yaml',import.meta.url),'utf8')});
assert.equal(ingress.authorizes_runtime,false);assert.equal(ingress.exact_static_assets.length,11);
const environment={ORACLE2_NATIVE_BROWSER_ONLY:'1',ORACLE2_NATIVE_BROWSER_PUBLIC_HOST:host,
  ORACLE2_NATIVE_BROWSER_SOURCE_REVISION:identity.revision,ORACLE2_PILOT_TOKEN:'public-invented-local-fixture',
  ORACLE2_PILOT_ACTOR:'public-invented-actor',ORACLE2_PILOT_WORKSPACE_ID:'public-invented-workspace',
  ORACLE2_NATIVE_ACCEPTANCE_SETTINGS:'/run/oracle-native-browser/settings.json',ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256:'a'.repeat(64)};
const args=['run','--detach','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true'];
for(const [key,value] of Object.entries(environment))args.push('--env',`${key}=${value}`);
args.push('--entrypoint','node',image,'/app/apps/web/server.js');
const container=execFileSync('docker',args,{encoding:'utf8',timeout:15000}).trim();assert.match(container,/^[a-f0-9]{64}$/);
const deadline=Date.now()+45000;
const fetchFixture=async(path,headers={},method='GET')=>{
  // Node 24 fetch strips caller Host. A real browser/ingress supplies Host;
  // use the raw local HTTP client to model that received header exactly.
  const source=`const http=require('http');const req=http.request({hostname:'127.0.0.1',port:3000,path:${JSON.stringify(path)},method:${JSON.stringify(method)},headers:${JSON.stringify({host,'x-forwarded-host':host,'x-forwarded-proto':'https',...headers})}},r=>{let bytes=0;const chunks=[];r.on('data',b=>{bytes+=b.length;if(bytes>4194304)req.destroy();else chunks.push(b)});r.on('end',()=>console.log(JSON.stringify({status:r.statusCode,revision:r.headers['x-oracle-source-revision'],etag:r.headers.etag,bytes,nativePage:Buffer.concat(chunks).includes(Buffer.from('Hosted invented-data test'))})));});req.on('error',()=>process.exit(2));req.setTimeout(2000,()=>req.destroy());req.end();`;
  for(let retry=0;retry<20&&Date.now()<deadline;retry++){
    const result=spawnSync('docker',['exec',container,'node','-e',source],{encoding:'utf8',timeout:5000});
    if(result.status===0)return JSON.parse(result.stdout);
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw Error('Public fixture server unavailable');
};
try{
  const page=await fetchFixture('/consultant/native-acceptance');assert.equal(page.status,200);assert.equal(page.nativePage,true);
  assert.equal((await fetchFixture(identity.asset)).status,200);
  const etag='"'+identity.sourceHash+'"';
  const source=await fetchFixture('/api/consultant/native-acceptance/source',{'if-match':etag,range:'bytes=0-15'});assert.equal(source.status,206);
  assert.equal(source.revision,identity.revision);assert.equal(source.etag,etag);assert.equal(source.bytes,16);
  assert.equal((await fetchFixture('/api/consultant/native-acceptance/source',{range:'bytes=0-15'})).status,416);
  assert.equal((await fetchFixture('/api/consultant/native-acceptance/source?metadata=1')).status,404);
  for(const path of ['/api/consultant/session','/api/consultant/source','/admin','/api/chat','/_next/static/not-in-native-manifest.js'])assert.equal((await fetchFixture(path)).status,404);
  for(const headers of [{'x-forwarded-proto':'http'},{'x-forwarded-proto':'https, https'},{'x-forwarded-host':'company.invalid'},{'x-forwarded-host':host+', '+host},{forwarded:'host=company.invalid;proto=https'},{'x-middleware-subrequest':'proxy'},{'x-invoke-path':'/admin'}]){
    assert.equal((await fetchFixture('/consultant/native-acceptance',headers)).status,404,JSON.stringify(headers));
    assert.equal((await fetchFixture('/api/chat',headers)).status,404,JSON.stringify(headers));
  }
  // Pinned Next consumes its data header before proxy. It still serves only
  // this exact invented page; it cannot reach a company path.
  const dataPage=await fetchFixture('/consultant/native-acceptance',{'x-nextjs-data':'1'});assert.equal(dataPage.status,200);assert.equal(dataPage.nativePage,true);
  assert.equal((await fetchFixture('/api/chat',{'x-nextjs-data':'1'})).status,404);
  assert.equal((await fetchFixture('/api/consultant/native-acceptance/source',{},'POST')).status,404);
  console.log(JSON.stringify({sourceRevision:identity.revision,sourceHash:identity.sourceHash,actualStandaloneBoundary:'PASS',exactOuterRuleCompilation:'PASS',outerRuleHash:ingress.platform_route_sha256,actualTraefikProof:false,admission:false,liveAcceptance:false}));
}finally{execFileSync('docker',['rm','--force',container],{stdio:'ignore',timeout:15000});}
