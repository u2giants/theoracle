/** Server-only, fixed installed Recall wire transport. No admission/identity issuer.
 * Closed application owners select all pins/keys/operation bodies. HTTP input
 * never reaches this constructor. Service mTLS transport remains its own owner.
 */
import * as tls from 'node:tls';
import * as https from 'node:https';
import * as dns from 'node:dns';
import {isIP} from 'node:net';
import {createHash} from 'node:crypto';
const hash=(bytes:Uint8Array)=>createHash('sha256').update(bytes).digest('hex');
const sha=/^[a-f0-9]{64}$/;
const bot=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const regions=new Set(['us-west-2.recall.ai','us-east-1.recall.ai','eu-central-1.recall.ai','ap-northeast-1.recall.ai']);
const refused=():never=>{throw new Error('Installed Recall operation unavailable');};
export interface RecallWireTargetV1 {readonly hostname:string;readonly ca:Uint8Array;readonly serverDerSha256:string;readonly authorization:string;}
export interface OriginalWireWindowV1 {readonly wallDeadline:number;readonly monotonicDeadline:bigint;readonly signal:AbortSignal;readonly current:()=>void;}
export type RecallWireOperationV1=Readonly<{kind:'create';body:Uint8Array}>|Readonly<{kind:'leave'|'retrieve';botId:string}>|Readonly<{kind:'send-chat';botId:string;body:Uint8Array}>;
export interface RecallWireObservationV1 {readonly status:number;readonly headers:ReadonlyArray<readonly[string,string]>;readonly body:Buffer;readonly wire:Buffer;readonly wireSha256:string;}
/** Bounded observed RESPONSE bytes on refusal, never request/key material.
 * An incomplete or over-bound wire remains UNKNOWN and is never executable.
 */
export class RecallWireUncertaintyV1 extends Error {
 readonly #retained:Buffer;readonly observedBytes:number;readonly wireTruncated:boolean;
 constructor(wire:Uint8Array,observedBytes:number){super('Installed Recall operation unavailable');this.name='RecallWireUncertaintyV1';this.#retained=Buffer.from(wire);this.observedBytes=observedBytes;this.wireTruncated=observedBytes>wire.length;}
 get wire():Buffer{return Buffer.from(this.#retained);}
}
function ipv6Words(address:string):number[]{
 const parts=address.split('::');if(parts.length>2)return refused();
 const left=parts[0]!.split(':').filter(Boolean),right=parts.length===2?parts[1]!.split(':').filter(Boolean):[];
 const missing=8-left.length-right.length;if(missing<0||parts.length===1&&missing!==0)return refused();
 return [...left,...Array<string>(missing).fill('0'),...right].map(v=>parseInt(v,16));
}
/** Production public-unicast policy; fixture transport cannot replace it. */
export function publicRecallAddressV1(address:string):boolean{
 if(typeof address!=='string'||address.includes('%'))return false;
 if(isIP(address)===4){const p=address.split('.').map(Number),a=p[0]!,b=p[1]!,c=p[2]!;
  return !(a===0||a===10||a===127||a>=224||a===100&&b>=64&&b<=127||a===169&&b===254||a===172&&b>=16&&b<=31||a===192&&(b===0||b===168||b===88&&c===99)||a===198&&(b===18||b===19||b===51&&c===100)||a===203&&b===0&&c===113);
 }
 if(isIP(address)!==6||address.includes('.'))return false;
 const w=ipv6Words(address);return w[0]!>=0x2000&&w[0]!<=0x3fff&&w[0]!==0x2002&&w[0]!==0x3fff&&!(w[0]===0x2001&&(w[1]!<=0x1ff||w[1]===0xdb8))&&!((w[4]===0||w[4]===0x200)&&w[5]===0x5efe);
}
function route(operation:RecallWireOperationV1):{method:'GET'|'POST';path:string;body:Buffer}{
 if(operation.kind==='create'){if(!(operation.body instanceof Uint8Array)||!operation.body.length||operation.body.length>65536)return refused();return {method:'POST',path:'/api/v1/bot/',body:Buffer.from(operation.body)};}
 if(!bot.test(operation.botId))return refused();
 if(operation.kind==='leave')return {method:'POST',path:`/api/v1/bot/${operation.botId}/leave_call/`,body:Buffer.alloc(0)};
 if(operation.kind==='retrieve')return {method:'GET',path:`/api/v1/bot/${operation.botId}/`,body:Buffer.alloc(0)};
 if(operation.kind!=='send-chat'||!(operation.body instanceof Uint8Array)||!operation.body.length||operation.body.length>32768)return refused();
 return {method:'POST',path:`/api/v1/bot/${operation.botId}/send_chat_message/`,body:Buffer.from(operation.body)};
}
class RecallWireClientV1{
 private dnsBusy=false;private busy=false;
 private readonly ca:Buffer;private readonly fixture:boolean;private readonly fixtureAddress:'127.0.0.1'|'::1';private readonly hostname:string;private readonly port:number;private readonly authorization:string;private readonly der:string;
 constructor(target:RecallWireTargetV1,fixture?:Readonly<{purpose:'invented-loopback-recall-transport-v1';port:number;address:'127.0.0.1'|'::1'}>){
  if(typeof window!=='undefined')throw new Error('Installed Recall operation unavailable');
  if(!sha.test(target.serverDerSha256)||!(target.ca instanceof Uint8Array)||!target.ca.length||target.ca.length>131072||typeof target.authorization!=='string'||!target.authorization.length||target.authorization.length>4096||/[^\x21-\x7e]/.test(target.authorization))throw new Error('Installed Recall operation unavailable');
  if(fixture){if(fixture.purpose!=='invented-loopback-recall-transport-v1'||!Number.isSafeInteger(fixture.port)||fixture.port<1||fixture.port>65535||!['127.0.0.1','::1'].includes(fixture.address)||target.hostname!=='localhost.localdomain'||!target.authorization.startsWith('invented-'))throw new Error('Installed Recall operation unavailable');}
  else if(!regions.has(target.hostname))throw new Error('Installed Recall operation unavailable');
  this.fixture=!!fixture;this.fixtureAddress=fixture?.address??'::1';this.hostname=target.hostname;this.port=fixture?.port??443;this.authorization=target.authorization;this.der=target.serverDerSha256;this.ca=Buffer.from(target.ca);
 }
 private remaining(window:OriginalWireWindowV1):number{
  window.current();const value=Math.min(window.wallDeadline-Date.now(),Number(window.monotonicDeadline-process.hrtime.bigint())/1e6);
  if(window.signal.aborted||!Number.isFinite(value)||value<=0||value>30000)return refused();return value;
 }
 private async addresses(window:OriginalWireWindowV1):Promise<dns.LookupAddress[]>{
  const duration=this.remaining(window);if(this.fixture)return [{address:this.fixtureAddress,family:this.fixtureAddress==='::1'?6:4}];if(this.dnsBusy)return refused();this.dnsBusy=true;
  return await new Promise((resolve,reject)=>{
   let completed=false;const finish=(error?:unknown,answers?:dns.LookupAddress[])=>{if(completed)return;completed=true;clearTimeout(timer);window.signal.removeEventListener('abort',abort);if(error)reject(new Error('Installed Recall operation unavailable'));else resolve(answers!);};
   const abort=()=>finish(true);const timer=setTimeout(abort,duration);window.signal.addEventListener('abort',abort,{once:true});
   try{dns.lookup(this.hostname,{all:true,verbatim:true},(error,answers)=>{this.dnsBusy=false;if(completed)return;
    try{this.remaining(window);if(error||!answers.length||answers.some(a=>![4,6].includes(a.family)||isIP(a.address)!==a.family||(this.fixture?!['127.0.0.1','::1'].includes(a.address):!publicRecallAddressV1(a.address))))return finish(true);finish(undefined,answers);}catch{finish(true);}
   });}catch{this.dnsBusy=false;finish(true);}
  });
 }
 private async within<T>(promise:Promise<T>,window:OriginalWireWindowV1):Promise<T>{
  const duration=this.remaining(window);return await new Promise<T>((resolve,reject)=>{let done=false;const finish=(error:unknown,value?:T)=>{if(done)return;done=true;clearTimeout(timer);window.signal.removeEventListener('abort',abort);if(error)reject(new Error('Installed Recall operation unavailable'));else resolve(value!);};const abort=()=>finish(true);const timer=setTimeout(abort,duration);window.signal.addEventListener('abort',abort,{once:true});promise.then(v=>finish(undefined,v),()=>finish(true));});
 }
 async exchange(operation:RecallWireOperationV1,window:OriginalWireWindowV1,beforeWrite:()=>Promise<void>):Promise<Readonly<RecallWireObservationV1>>{
  if(this.busy||typeof beforeWrite!=='function')return refused();this.busy=true;
  let connected:tls.TLSSocket|undefined,request:ReturnType<typeof https.request>|undefined,timer:ReturnType<typeof setTimeout>|undefined;
  const retainedResponse:Buffer[]=[];let observedBytes=0,retainedBytes=0;const maximumRetained=16384+1048576;
  const abort=()=>{request?.destroy();connected?.destroy();};
  try{
   const q=route(operation);this.remaining(window);const answers=await this.addresses(window);this.remaining(window);const selected=answers[0]!;
   window.signal.addEventListener('abort',abort,{once:true});timer=setTimeout(abort,this.remaining(window));
   connected=tls.connect({host:selected.address,port:this.port,servername:this.hostname,ca:this.ca,rejectUnauthorized:true,minVersion:'TLSv1.2',ALPNProtocols:['http/1.1'],checkServerIdentity:(name,certificate)=>tls.checkServerIdentity(name,certificate)??(hash(certificate.raw)===this.der?undefined:new Error('Installed Recall operation unavailable'))});
   connected.on('error',()=>undefined);
   await new Promise<void>((resolve,reject)=>{const socket=connected!;socket.once('secureConnect',()=>{try{this.remaining(window);if(!socket.authorized||tls.checkServerIdentity(this.hostname,socket.getPeerCertificate())||hash(socket.getPeerCertificate().raw)!==this.der||socket.alpnProtocol&&socket.alpnProtocol!=='http/1.1')return reject(new Error('Installed Recall operation unavailable'));resolve();}catch{reject(new Error('Installed Recall operation unavailable'));}});socket.once('error',reject);socket.once('close',()=>reject(new Error('Installed Recall operation unavailable')));});
   // Current original authority is reproved by the fixed application owner
   // AFTER actual verified TLS and immediately BEFORE request bytes exist.
   this.remaining(window);await this.within(beforeWrite(),window);this.remaining(window);
   const socket=connected;socket.destroySoon=()=>socket.end();
   const wireLimit=16384+1048576;let prefix=Buffer.alloc(0),headerLength:number|undefined,wireSize=0,expectedSize:number|undefined,wireBad=false,peerEnd=false,peerClose=false,closedError=false,responseDone=false,status=0,headers:readonly(readonly[string,string])[]=[],body=Buffer.alloc(0);const wire:Buffer[]=[];
   let rejectWire:((error:Error)=>void)|undefined;
   const fail=()=>{wireBad=true;rejectWire?.(new Error('Installed Recall operation unavailable'));abort();};
   const observe=(chunk:Buffer)=>{observedBytes+=chunk.length;const keep=Math.min(chunk.length,maximumRetained-retainedBytes);if(keep>0){retainedResponse.push(Buffer.from(chunk.subarray(0,keep)));retainedBytes+=keep;}try{this.remaining(window);wireSize+=chunk.length;if(wireSize>wireLimit)return fail();wire.push(Buffer.from(chunk));if(headerLength===undefined){prefix=Buffer.concat([prefix,chunk]);const end=prefix.indexOf('\r\n\r\n');if(end>=0){headerLength=end+4;if(headerLength>16384)return fail();prefix=Buffer.alloc(0);}else if(prefix.length>16384)return fail();}if(expectedSize!==undefined&&wireSize>expectedSize)return fail();}catch{fail();}};
   socket.on('data',observe);
   const agent=new https.Agent({keepAlive:false,maxSockets:1});agent.createConnection=()=>socket;
   try{return await new Promise<Readonly<RecallWireObservationV1>>((resolve,reject)=>{
    rejectWire=reject;
    const finish=()=>{if(!responseDone||!peerEnd||!peerClose)return;try{this.remaining(window);if(wireBad||closedError||headerLength===undefined||expectedSize!==wireSize)return fail();const raw=Buffer.concat(wire,wireSize);resolve(Object.freeze({status,headers,body,wire:raw,wireSha256:hash(raw)}));}catch{fail();}};
    socket.once('end',()=>{peerEnd=true;finish();});socket.once('close',hadError=>{peerClose=true;closedError=hadError;if(!peerEnd||!responseDone||hadError)return fail();finish();});
    request=https.request({hostname:this.hostname,port:this.port,method:q.method,path:q.path,agent,headers:{Authorization:this.authorization,Accept:'application/json','Content-Type':'application/json','Content-Length':String(q.body.length),Connection:'close'}},response=>{
     try{this.remaining(window);const raw=response.rawHeaders,seen=new Set<string>(),pairs:Array<readonly[string,string]>=[];
      for(let i=0;i<raw.length;i+=2){const name=raw[i]!.toLowerCase(),value=raw[i+1]!;if(seen.has(name))return fail();seen.add(name);pairs.push(Object.freeze([name,value]as const));}
      const len=response.headers['content-length'];if(typeof len!=='string'||!/^(0|[1-9][0-9]{0,6})$/.test(len)||Number(len)>1048576||response.headers['transfer-encoding']!==undefined||response.headers['content-encoding']!==undefined||headerLength===undefined)return fail();
      expectedSize=headerLength+Number(len);if(wireSize>expectedSize)return fail();status=response.statusCode??0;headers=Object.freeze(pairs);if(!Number.isInteger(status)||status<200||status>599)return fail();const chunks:Buffer[]=[];let size=0;
      response.on('data',(chunk:Buffer)=>{try{this.remaining(window);size+=chunk.length;if(size>Number(len))return fail();chunks.push(Buffer.from(chunk));}catch{fail();}});
      response.once('aborted',fail);response.once('error',fail);response.once('end',()=>{try{this.remaining(window);if(!response.complete||size!==Number(len)||Object.keys(response.trailers).length)return fail();body=Buffer.concat(chunks,size);responseDone=true;finish();}catch{fail();}});
     }catch{fail();}
    });request.once('error',()=>{reject(new Error('Installed Recall operation unavailable'));abort();});request.end(q.body);
   });}finally{socket.removeListener('data',observe);agent.destroy();}
  }catch{throw new RecallWireUncertaintyV1(Buffer.concat(retainedResponse,retainedBytes),observedBytes);}finally{if(timer)clearTimeout(timer);window.signal.removeEventListener('abort',abort);abort();this.busy=false;}
 }
}
/** Production constructor never admits private/transition DNS answers. */
export function installedRecallHTTPSV1(target:RecallWireTargetV1):Pick<RecallWireClientV1,'exchange'>{return new RecallWireClientV1(target);}
/** Explicit owned synthetic peer only; production owners never call this. */
export function inventedLoopbackRecallHTTPSV1(target:RecallWireTargetV1,port:number,address:'127.0.0.1'|'::1'='::1'):Pick<RecallWireClientV1,'exchange'>{return new RecallWireClientV1(target,{purpose:'invented-loopback-recall-transport-v1',port,address});}
