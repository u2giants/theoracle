/** Browser-only selected-file controller. No credentials, profiles or retry. */
import { canonicalJson } from './replacement-canonical-json';
import { UPLOAD_CHUNK_BYTES,UPLOAD_MAX_BYTES,UPLOAD_MAX_REQUEST_BYTES,type UploadResponse } from './replacement-upload-contract';
const PATH='/api/consultant/replacement/v1/protected/upload';
const sha=async(data:ArrayBuffer)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),b=>b.toString(16).padStart(2,'0')).join('');
const wireTime=(ms:number)=>{const s=new Date(ms).toISOString();return s.endsWith('.000Z')?s.replace('.000Z','Z'):s.replace(/([0-9]{3})Z$/,'$1000Z');};
const base64=(bytes:Uint8Array)=>{let raw='';for(let i=0;i<bytes.length;i+=16384)raw+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(raw);};
export class OriginalUploadUnknown extends Error {constructor(){super('Upload outcome is unknown. No further data will be sent.');}}
export interface OriginalUploadSession {run(file:File,onObservation:(value:UploadResponse)=>void):Promise<UploadResponse>;cancel():void;}
export function createOriginalUploadSession():OriginalUploadSession{
 let started=false,cancelled=false;
 return {
  cancel(){cancelled=true;},
  async run(file,onObservation){
   if(started)throw new OriginalUploadUnknown();started=true;
   const start=Date.now(),mono=performance.now(),end=start+25000,deadline=wireTime(end);
   if(!(file instanceof File)||!file.name||[...file.name].length>255||/[\/\\\u0000-\u001f\u007f]/.test(file.name)||file.type!=='application/pdf'||file.size<1||file.size>UPLOAD_MAX_BYTES)throw new Error('Choose one PDF up to 25 MiB.');
   const entire=await file.arrayBuffer();if(new TextDecoder().decode(entire.slice(0,5))!=='%PDF-')throw new Error('Choose an original PDF.');
   const fullHash=await sha(entire),key=crypto.randomUUID();let last:UploadResponse|undefined;
   const remaining=()=>Math.min(end-Date.now(),25000-(performance.now()-mono),last?Date.parse(last.valid_until)-Date.now():25000);
   async function send(body:Record<string,unknown>):Promise<UploadResponse>{
    const raw=canonicalJson(body),bytes=new TextEncoder().encode(raw);const ms=remaining();if(bytes.length>UPLOAD_MAX_REQUEST_BYTES||ms<=0)throw new OriginalUploadUnknown();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),ms);
    try{
     const response=await fetch(PATH,{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json'},body:raw,signal:controller.signal});
     if(response.status!==200||response.headers.get('content-type')!=='application/json')throw new OriginalUploadUnknown();
     const text=await response.text();if(new TextEncoder().encode(text).length>16384)throw new OriginalUploadUnknown();
     const value=JSON.parse(text) as UploadResponse;
     if(value.schema_version!==1||value.qualification!==false||value.remote_stop_proven!==false||value.observation_only!==true||!Number.isSafeInteger(value.received_bytes)||!Number.isSafeInteger(value.next_chunk_index)||!Number.isSafeInteger(value.revision)||!Number.isFinite(Date.parse(value.valid_until))||Date.parse(value.valid_until)>end||Date.parse(value.valid_until)<=Date.now()||remaining()<=0)throw new OriginalUploadUnknown();
     if(last&&(value.reservation_id!==last.reservation_id||value.source_id!==last.source_id||value.revision!==last.revision||value.begin_sha256!==last.begin_sha256||Date.parse(value.valid_until)>Date.parse(last.valid_until)))throw new OriginalUploadUnknown();
     if(body.operation!=='finalize'&&value.source_snapshot!==null)throw new OriginalUploadUnknown();
     last=value;onObservation(value);return value;
    }catch{throw new OriginalUploadUnknown();}finally{clearTimeout(timer);}
   }
   const begin={schema_version:1,operation:'begin',source_id:null,expected_head:0,idempotency_key:key,filename:file.name,original_sha256:fullHash,byte_count:file.size,caller_deadline:deadline};
   if(cancelled)throw new OriginalUploadUnknown();
   const reserved=await send(begin);if(reserved.state!=='reserved'||reserved.received_bytes!==0||reserved.next_chunk_index!==0||reserved.begin_sha256!==await sha(new TextEncoder().encode(canonicalJson(begin)).buffer))throw new OriginalUploadUnknown();
   const action=(operation:string)=>({schema_version:1,operation,reservation_id:reserved.reservation_id,source_id:reserved.source_id,revision:reserved.revision,begin_sha256:reserved.begin_sha256,caller_deadline:deadline});
   const cancel=()=>send(action('cancel'));
   for(let offset=0,index=0;offset<file.size;offset+=UPLOAD_CHUNK_BYTES,index++){
    if(cancelled)return cancel();
    const part=entire.slice(offset,Math.min(offset+UPLOAD_CHUNK_BYTES,file.size));
    const response=await send({...action('chunk'),chunk_index:index,offset,chunk_sha256:await sha(part),data_base64:base64(new Uint8Array(part))});
    if(response.state!=='receiving'||response.received_bytes!==Math.min(offset+UPLOAD_CHUNK_BYTES,file.size)||response.next_chunk_index!==index+1)throw new OriginalUploadUnknown();
   }
   if(cancelled)return cancel();
   const final=await send(action('finalize'));
   if(final.state!=='committed'||final.received_bytes!==file.size||final.source_snapshot?.originalSha256!==fullHash||final.source_snapshot?.byteCount!==file.size||final.source_snapshot?.state!=='awaiting_original_reading'||final.source_snapshot?.qualifiedSourceRef!==null)throw new OriginalUploadUnknown();
   return final;
  },
 };
}
