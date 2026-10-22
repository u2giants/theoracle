/** Private exclusive execution receipt. Not an admission or remote-stop proof. */
import {constants,openSync,closeSync,writeSync,fsyncSync,fstatSync,lstatSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {protectedRead,sha256,type PinnedFile} from './_protected-file';
import {canonicalJson,parseClosedJson,type MeetingWorkerBinding} from './protected-server-binding';
import type {MeetingWorkerPacketV1} from './protected-worker-contract';
const fail=():never=>{throw new Error('Meeting worker unavailable');};
function root(profile:Readonly<MeetingWorkerBinding>):void{
 const stat=lstatSync(profile.receipt_root);
 if(!stat.isDirectory()||stat.isSymbolicLink()||(stat.mode&0o077)!==0||stat.uid!==process.getuid?.()||stat.dev!==profile.receipt_device||stat.ino!==profile.receipt_inode||stat.uid!==profile.receipt_uid||dirname(profile.receipt_initialization_file)!==profile.receipt_root)return fail();
 const file=protectedRead(profile.receipt_initialization_file,profile.receipt_initialization_sha256);
 const value=parseClosedJson(file.bytes,4096),expected={schema_version:1,purpose:'meeting-worker-receipt-root-v1',worker_id:profile.worker_id,receipt_root:profile.receipt_root,receipt_device:profile.receipt_device,receipt_inode:profile.receipt_inode,receipt_uid:profile.receipt_uid,issuer_actor:profile.issuer_actor,reviewer_actor:profile.reviewer_actor};
 if(canonicalJson(value)!==canonicalJson(expected)||file.bytes.toString('utf8')!==canonicalJson(expected))return fail();
}
export function beginWorkerReceiptV1(profile:Readonly<MeetingWorkerBinding>,claim:Readonly<MeetingWorkerPacketV1>):PinnedFile{
 root(profile);
 if(claim.state!=='claimed'||!claim.executable||!claim.claim_event_id||!claim.operation_id||!claim.request_sha256)return fail();
 const bytes=Buffer.from(canonicalJson({schema_version:1,purpose:'meeting-worker-exclusive-execution-v1',worker_id:profile.worker_id,principal_id:profile.principal_id,workspace_id:profile.workspace_id,meeting_id:profile.meeting_id,provider_account:profile.provider_account,effect_purpose:profile.effect_purpose,operation_id:claim.operation_id,claim_event_id:claim.claim_event_id,request_sha256:claim.request_sha256,body_sha256:sha256(Buffer.from(claim.body_base64!,'base64')),valid_until:claim.valid_until}));
 const path=join(profile.receipt_root,claim.operation_id+'.execution.json');let fd:number|undefined,dir:number|undefined;
 try{
  // Never overwrite/reopen a prior execution as dispatch permission. Partial
  // creation or process loss stays uncertain; no automatic POST retry.
  dir=openSync(profile.receipt_root,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);
  const stat=fstatSync(dir);if(stat.dev!==profile.receipt_device||stat.ino!==profile.receipt_inode||stat.uid!==profile.receipt_uid)return fail();
  fd=openSync(path,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);
  let offset=0;while(offset<bytes.length){const count=writeSync(fd,bytes,offset,bytes.length-offset);if(count<=0)return fail();offset+=count;}
  fsyncSync(fd);fsyncSync(dir);root(profile);
 }finally{if(fd!==undefined)closeSync(fd);if(dir!==undefined)closeSync(dir);}
 return protectedRead(path,sha256(bytes));
}
export function currentWorkerReceiptV1(profile:Readonly<MeetingWorkerBinding>,receipt:PinnedFile):void{
 root(profile);const current=protectedRead(receipt.path,receipt.digest);
 if(current.identity!==receipt.identity||current.path!==receipt.path)return fail();
}
