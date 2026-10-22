/** Controlled owned filesystem ABA; no installed authority or provider calls. */
import assert from 'node:assert/strict';import {test} from 'node:test';
import fs from 'node:fs';import {syncBuiltinESMExports} from 'node:module';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {beginWorkerReceiptV1} from '../../../packages/shared/src/_worker-receipt';
import {canonicalJson,sha256,type MeetingWorkerBinding} from '@oracle/shared/protected-server-binding';
import type {MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
const id='11111111-1111-4111-8111-111111111111',hash='a'.repeat(64);
function fixture(){
 const directory=fs.mkdtempSync(join(tmpdir(),'oracle-worker-aba-'));fs.chmodSync(directory,0o700);const root=join(directory,'receipts');fs.mkdirSync(root,{mode:0o700});const stat=fs.lstatSync(root),initial=join(root,'initialization.json');
 const profile={receipt_root:root,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,receipt_initialization_file:initial,worker_id:id,principal_id:id,workspace_id:id,meeting_id:id,provider_account:'invented',effect_purpose:'capture-create',issuer_actor:'independent-issuer',reviewer_actor:'independent-reviewer'} as unknown as MeetingWorkerBinding;
 const init=Buffer.from(canonicalJson({schema_version:1,purpose:'meeting-worker-receipt-root-v1',worker_id:id,receipt_root:root,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,issuer_actor:profile.issuer_actor,reviewer_actor:profile.reviewer_actor}));fs.writeFileSync(initial,init,{mode:0o600});Object.assign(profile,{receipt_initialization_sha256:sha256(init)});
 const claim={state:'claimed',executable:true,operation_id:id,claim_event_id:id,request_sha256:hash,body_base64:Buffer.from('{}').toString('base64'),valid_until:'2099-01-01T00:00:00Z'} as MeetingWorkerPacketV1;
 return {directory,root,initial,profile,claim,path:join(root,id+'.execution.json')};
}
test('ordinary exclusive receipt binds newly created inode and refuses repeat',()=>{
 const f=fixture();try{const receipt=beginWorkerReceiptV1(f.profile,f.claim);assert.ok(receipt.identity.includes(String(fs.lstatSync(f.path).ino)));assert.throws(()=>beginWorkerReceiptV1(f.profile,f.claim));}finally{fs.rmSync(f.directory,{recursive:true,force:true});}
});
test('root ABA cannot reinterpret preexisting same-operation receipt as fresh execution',()=>{
 const f=fixture(),original=fs.openSync;let attacked=false;
 try{
  const prior=beginWorkerReceiptV1(f.profile,f.claim),priorBytes=fs.readFileSync(f.path),backup=join(f.directory,'original'),wrong=join(f.directory,'wrong-root');
  Object.defineProperty(fs,'openSync',{configurable:true,writable:true,value:(...args:Parameters<typeof fs.openSync>)=>{
   if(args[0]===f.path&&!attacked){attacked=true;fs.renameSync(f.root,backup);fs.mkdirSync(f.root,{mode:0o700});fs.copyFileSync(join(backup,'initialization.json'),f.initial);fs.chmodSync(f.initial,0o600);const fd=Reflect.apply(original,fs,args);fs.renameSync(f.root,wrong);fs.renameSync(backup,f.root);return fd;}
   return Reflect.apply(original,fs,args);
  }});syncBuiltinESMExports();
  assert.throws(()=>beginWorkerReceiptV1(f.profile,f.claim),/unavailable/);assert.equal(attacked,true);assert.deepEqual(fs.readFileSync(f.path),priorBytes);assert.equal(fs.lstatSync(f.path).ino,Number(prior.identity.split('|').at(-1)!.split(':')[1]));assert.ok(fs.existsSync(join(wrong,id+'.execution.json')));
 }finally{Object.defineProperty(fs,'openSync',{value:original});syncBuiltinESMExports();fs.rmSync(f.directory,{recursive:true,force:true});}
});
