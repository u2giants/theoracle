/** Owned synthetic child. Production constructors remain unchanged. */
import assert from 'node:assert/strict';
import {registerHooks,syncBuiltinESMExports} from 'node:module';
import dns from 'node:dns';import tls from 'node:tls';
const lookup=dns.lookup,connect=tls.connect;
Object.defineProperty(dns,'lookup',{configurable:true,writable:true,value:(...args:unknown[])=>{if(!['localhost.localdomain','127.0.0.1','::1'].includes(String(args[0])))throw new Error('fixture refused external DNS');return Reflect.apply(lookup,dns,args);}});
Object.defineProperty(tls,'connect',{configurable:true,writable:true,value:(...args:unknown[])=>{const v=args[0];if(!v||typeof v!=='object'||!['localhost.localdomain','127.0.0.1','::1'].includes(String(Reflect.get(v,'host')))||Reflect.get(v,'servername')!=='localhost.localdomain')throw new Error('fixture refused external TLS');return Reflect.apply(connect,tls,args);}});syncBuiltinESMExports();
const url=new URL('../../../../packages/shared/src/protected-node-https.ts',import.meta.url).href,port=Number(process.env.ORACLE2_INVENTED_PROVIDER_PORT);
if(!Number.isSafeInteger(port)||port<1||port>65535)throw new Error('invented provider absent');
registerHooks({resolve(s,c,next){if(c.parentURL?.includes('protected-meeting-worker.ts')&&s==='./protected-node-https')return {url:'oracle-test:unattended-provider',shortCircuit:true};return next(s,c);},load(u,c,next){if(u==='oracle-test:unattended-provider')return {format:'module',shortCircuit:true,source:`import {inventedLoopbackRecallHTTPSV1} from ${JSON.stringify(url)};export function installedRecallHTTPSV1(target){const client=inventedLoopbackRecallHTTPSV1({...target,hostname:'localhost.localdomain'},${port},'::1');(globalThis.__ownedUnattendedProviders??=[]).push(client);return client}`};return next(u,c);}});
// Preload mode is used by the SAME actual local STOP service. It installs only
// the explicit fixture target/tripwire; no effect, profile or clock is issued.
if(process.env.ORACLE2_INVENTED_CYCLE_DIAGNOSTIC==='1'){
 const {installedLocalMeetingStopCycleV1}=await import('../../../../packages/shared/src/protected-meeting-worker');
 try{const cycle=installedLocalMeetingStopCycleV1();const value=await cycle.current_queue_v1();process.stdout.write(JSON.stringify({ok:true,value})+'\n');}catch(error){process.stderr.write(String((error as Error).stack)+'\n');process.exitCode=4;}
}else if(process.env.ORACLE2_INVENTED_QUEUE_DIAGNOSTIC==='1'){
 const {installedLocalMeetingStopSupervisionV1}=await import('../../../../packages/shared/src/protected-meeting-worker');
 try{const value=await installedLocalMeetingStopSupervisionV1().current_queue_v1();process.stdout.write(JSON.stringify({ok:true,value})+'\n');}catch(error){process.stderr.write(String((error as Error).stack)+'\n');process.exitCode=3;}
}else if(process.env.ORACLE2_INVENTED_DRIVER_PRELOAD!=='1'){
 const {installedMeetingCaptureCreateWorkerV1}=await import('../../../../packages/shared/src/protected-meeting-worker');
 const {canonicalJson}=await import('../../../../packages/shared/src/protected-server-binding');
 const w=installedMeetingCaptureCreateWorkerV1();assert.equal(w.effect_purpose,'capture-create');
 const provider=Reflect.get(w,'provider');assert.ok((globalThis as unknown as {__ownedUnattendedProviders:unknown[]}).__ownedUnattendedProviders.includes(provider));assert.equal(Reflect.get(provider,'fixture'),true);assert.equal(Reflect.get(provider,'port'),port);
 // The fixture releases only the first prepare after actual readonly process
 // preflight. This consumes the already captured worker window; no renewal.
 if(process.env.ORACLE2_INVENTED_READY_FILE){
  const {writeFileSync}=await import('node:fs');
  writeFileSync(process.env.ORACLE2_INVENTED_READY_FILE,'ready',{mode:0o600});
  await new Promise<void>((resolve,reject)=>{
   let input='';const timer=setTimeout(()=>{process.stdin.destroy();reject(new Error('fixture readiness expired'));},Math.min(10000,Math.max(1,Date.parse(w.original_deadline_v1)-Date.now())));
   process.stdin.setEncoding('utf8');process.stdin.on('data',(part:string)=>{input+=part;if(input.length>3||!('go\n').startsWith(input)){clearTimeout(timer);reject(new Error('fixture readiness refused'));}else if(input==='go\n'){clearTimeout(timer);process.stdin.destroy();resolve();}});process.stdin.on('end',()=>{if(input!=='go\n'){clearTimeout(timer);reject(new Error('fixture readiness absent'));}});
  });
 }
 let stage='prepare';
 try{const prepared=await w.prepare_v1();if(prepared.state!=='prepared')throw new Error('not prepared');assert.equal(prepared.executable,false);assert.equal(prepared.body_base64,null);stage='claim';const claim=await w.claim_v1();if(!claim.executable)throw new Error('not executable');assert.equal(claim.state,'claimed');assert.ok(claim.body_base64);stage='current';const current=await w.current_v1(claim);assert.equal(current.executable,false);assert.equal(current.state,'inflight');stage='exchange';const raw=await w.exchange_provider_v1(claim);stage='observe';const receipt=await w.observe_v1(claim,raw.wire);process.stdout.write(canonicalJson({state:receipt.state,qualification:receipt.qualification,remote_stop_proven:receipt.remote_stop_proven,resend_authorized:receipt.resend_authorized,operation_id:claim.operation_id,claim_event_id:claim.claim_event_id,request_sha256:claim.request_sha256,deadline:w.original_deadline_v1})+'\n');}
 catch(error){const error_type=error instanceof Error?error.constructor.name:typeof error;process.stdout.write(canonicalJson({state:'UNKNOWN',remote_stop_proven:false,stage,error_type})+'\n');process.exitCode=2;}
}
