/** Private exclusive execution receipt. Not an admission or remote-stop proof. */
import {constants,openSync,closeSync,writeSync,fsyncSync,fstatSync,lstatSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {protectedRead,sha256,type PinnedFile} from './_protected-file';
import {canonicalJson,parseClosedJson,type MeetingWorkerBinding,type MeetingQueueBinding} from './protected-server-binding';
import type {MeetingQueuePacketV1} from './protected-meeting-queue-contract';
import type {MeetingWorkerPacketV1} from './protected-worker-contract';
const fail=():never=>{throw new Error('Meeting worker unavailable');};
type ReceiptProfileV1=MeetingWorkerBinding|MeetingQueueBinding;
function root(profile:Readonly<ReceiptProfileV1>):void{
 const stat=lstatSync(profile.receipt_root);
 if(!stat.isDirectory()||stat.isSymbolicLink()||(stat.mode&0o077)!==0||stat.uid!==process.getuid?.()||stat.dev!==profile.receipt_device||stat.ino!==profile.receipt_inode||stat.uid!==profile.receipt_uid||dirname(profile.receipt_initialization_file)!==profile.receipt_root)return fail();
 const file=protectedRead(profile.receipt_initialization_file,profile.receipt_initialization_sha256);
 const value=parseClosedJson(file.bytes,4096),expected={schema_version:1,purpose:profile.purpose==='meeting-ingress-queue-worker-v1'?'meeting-queue-receipt-root-v1':'meeting-worker-receipt-root-v1',worker_id:profile.worker_id,receipt_root:profile.receipt_root,receipt_device:profile.receipt_device,receipt_inode:profile.receipt_inode,receipt_uid:profile.receipt_uid,issuer_actor:profile.issuer_actor,reviewer_actor:profile.reviewer_actor};
 if(canonicalJson(value)!==canonicalJson(expected)||file.bytes.toString('utf8')!==canonicalJson(expected))return fail();
}
export function beginWorkerReceiptV1(profile:Readonly<MeetingWorkerBinding>,claim:Readonly<MeetingWorkerPacketV1>):PinnedFile{
 root(profile);
 if(claim.state!=='claimed'||!claim.executable||!claim.claim_event_id||!claim.operation_id||!claim.request_sha256)return fail();
 const bytes=Buffer.from(canonicalJson({schema_version:1,purpose:'meeting-worker-exclusive-execution-v1',worker_id:profile.worker_id,principal_id:profile.principal_id,workspace_id:profile.workspace_id,meeting_id:profile.meeting_id,provider_account:profile.provider_account,effect_purpose:profile.effect_purpose,operation_id:claim.operation_id,claim_event_id:claim.claim_event_id,request_sha256:claim.request_sha256,body_sha256:sha256(Buffer.from(claim.body_base64!,'base64')),valid_until:claim.valid_until}));
 return createReceiptV1(profile,bytes,claim.operation_id+'.execution.json');
}
function createReceiptV1(profile:Readonly<ReceiptProfileV1>,bytes:Buffer,filename:string):PinnedFile{
 const path=join(profile.receipt_root,filename);let fd:number|undefined,dir:number|undefined;
 try{
  // Never overwrite/reopen a prior execution as dispatch permission. Partial
  // creation or process loss stays uncertain; no automatic POST retry.
  dir=openSync(profile.receipt_root,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);
  const stat=fstatSync(dir);if(stat.dev!==profile.receipt_device||stat.ino!==profile.receipt_inode||stat.uid!==profile.receipt_uid)return fail();
  fd=openSync(path,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);
  let offset=0;while(offset<bytes.length){const count=writeSync(fd,bytes,offset,bytes.length-offset);if(count<=0)return fail();offset+=count;}
  fsyncSync(fd);fsyncSync(dir);root(profile);
  // The path may have undergone ABA while O_EXCL created a different file.
  // Keep the newly created descriptor open until the final path read proves
  // this SAME inode/stat, never a preexisting same-digest execution receipt.
  const created=fstatSync(fd),identity=(s:typeof created)=>[s.dev,s.ino,s.mode,s.uid,s.nlink,s.size,s.ctimeMs,s.mtimeMs].join(':');
  const receipt=protectedRead(path,sha256(bytes)),after=fstatSync(fd),named=lstatSync(path);
  if(identity(created)!==identity(after)||identity(created)!==identity(named)||created.gid!==after.gid||created.gid!==named.gid||!receipt.identity.endsWith('|'+identity(created)))return fail();
  return receipt;
 }finally{if(fd!==undefined)closeSync(fd);if(dir!==undefined)closeSync(dir);}
}
function currentReceiptV1(profile:Readonly<ReceiptProfileV1>,receipt:PinnedFile):void{
 root(profile);const current=protectedRead(receipt.path,receipt.digest);
 if(current.identity!==receipt.identity||current.path!==receipt.path)return fail();
}

export function currentWorkerReceiptV1(profile:Readonly<MeetingWorkerBinding>,receipt:PinnedFile):void{currentReceiptV1(profile,receipt);}
/** Typed queue branch preserves all original capture bytes and ABA checks. */
export function beginQueueReceiptV1(profile:Readonly<MeetingQueueBinding>,claim:Readonly<MeetingQueuePacketV1>):PinnedFile{
 root(profile);
 if(profile.purpose!=='meeting-ingress-queue-worker-v1'||claim.state!=='claimed'||!claim.fresh_claim||!claim.claim_id||!claim.ingress_event_id||!claim.request_sha256||!claim.body||sha256(Buffer.from(canonicalJson(claim.body)))!==claim.request_sha256)return fail();
 const bytes=Buffer.from(canonicalJson({schema_version:1,purpose:'meeting-queue-exclusive-execution-v1',worker_id:profile.worker_id,principal_id:profile.principal_id,workspace_id:profile.workspace_id,meeting_id:profile.meeting_id,ingress_event_id:claim.ingress_event_id,claim_id:claim.claim_id,request_sha256:claim.request_sha256,queue_installation_receipt_sha256:profile.queue_installation_receipt_sha256,queue_target_descriptor_sha256:profile.queue_target_descriptor_sha256,valid_until:claim.valid_until}));
 return createReceiptV1(profile,bytes,claim.claim_id+'.queue-execution.json');
}
export function currentQueueReceiptV1(profile:Readonly<MeetingQueueBinding>,receipt:PinnedFile):void{currentReceiptV1(profile,receipt);}
