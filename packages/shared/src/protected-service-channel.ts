import {type ConnectedAnswerPacket} from './protected-client-contracts';
import {parseQualifiedAnswerResponseV1,type NaturalAnswerPacketV1} from './protected-natural-question-contract';
/** ONE concrete Node mTLS channel; old web identity stays web-owned.
 * open verifies TLS without HTTP; send is single-use within the original fence.
 * No caller-selected auth adapter, URL, header, role or peer is accepted.
 */
import * as https from 'node:https';import * as tls from 'node:tls';
import {canonicalJson,instant,rereadInstalledMeetingWorkerBinding,readInstalledBinding,readInstalledViewerBinding,readInstalledUploadBinding,readInstalledMeetingBinding,readInstalledMeetingIngressBinding,readInstalledModelReviewBinding,readInstalledConversationBinding,readInstalledConnectedAnswerBinding,readInstalledMcpAnswerBinding,MAX_ORIGINAL_BYTES,sha256,type InstalledBinding,type ProtectedBinding,type ViewerSourcePin} from './protected-server-binding';
import {remaining,within,type Window} from './protected-control-window';
import {parseControlMetadata,parseModelReviewResponse,parseUploadResponse,parseMeetingMetadata,type ControlMetadata,type OriginalPacket,type ModelReviewPacket,type MeetingMetadata} from './protected-client-contracts';
import {parseConversationResponse,type ConversationPacket} from './protected-conversation-contract';
import {parseMeetingWorkerPacketV1,type MeetingWorkerPacketV1} from './protected-worker-contract';
import type {UploadResponse} from './protected-upload-contract';
if(typeof window!=='undefined')throw new Error('Replacement control unavailable');
const failure=():never=>{throw new Error('Replacement control unavailable');};

export function current(initial: InstalledBinding<ProtectedBinding>, window: Window): void {
  const again = initial.profile.purpose==='qualified-connected-answer-web-binding-v1'?readInstalledConnectedAnswerBinding():initial.profile.purpose==='qualified-connected-answer-mcp-binding-v1'?readInstalledMcpAnswerBinding():initial.profile.purpose==='replacement-meeting-worker-binding-v1'?rereadInstalledMeetingWorkerBinding(initial as InstalledBinding<import('./protected-server-binding').MeetingWorkerBinding>):initial.profile.purpose==='replacement-meeting-ingress-web-binding-v1'?readInstalledMeetingIngressBinding():initial.profile.purpose==='replacement-meeting-control-web-binding-v1'?readInstalledMeetingBinding():initial.profile.purpose==='employee-conversation-web-binding-v1'?readInstalledConversationBinding():initial.profile.purpose==='replacement-model-review-web-binding-v1'?readInstalledModelReviewBinding():initial.profile.purpose==='replacement-upload-web-binding-v1'?readInstalledUploadBinding():initial.profile.purpose==='replacement-original-web-binding-v1'?readInstalledViewerBinding():readInstalledBinding();
  if (canonicalJson(again.profile) !== canonicalJson(initial.profile)) return failure();
  window.end = Math.min(window.end,instant(again.profile.expires_at),instant(again.profile.original_horizon));
  remaining(window);
}
export async function openProtectedChannelV1(installed:InstalledBinding<ProtectedBinding>,window:Window,pin?:Readonly<ViewerSourcePin>){
  const p = installed.profile; const url = new URL(p.backend_origin);
  let socket: tls.TLSSocket | undefined; let request: ReturnType<typeof https.request> | undefined;
  const abort = () => { request?.destroy(); socket?.destroy(); };
  window.signal.addEventListener('abort',abort,{once:true});
  try {
    socket = tls.connect({host:p.server_dns,port:url.port ? Number(url.port) : 443,servername:p.server_dns,ca:installed.ca,cert:installed.cert,key:installed.key,rejectUnauthorized:true,minVersion:'TLSv1.2',ALPNProtocols:['http/1.1'],checkServerIdentity:(host,cert) => tls.checkServerIdentity(host,cert) ?? (sha256(cert.raw) === p.server_certificate_der_sha256 ? undefined : new Error('Replacement control unavailable'))});
    socket.on('error',() => undefined);
    socket.setTimeout(remaining(window),() => socket?.destroy(new Error('Replacement control unavailable')));
    await within(new Promise<void>((resolve,reject) => { socket!.once('secureConnect',() => {
      try {
        if (!socket!.authorized || tls.checkServerIdentity(p.server_dns,socket!.getPeerCertificate()) || sha256(socket!.getPeerCertificate().raw) !== p.server_certificate_der_sha256 || (socket!.alpnProtocol && socket!.alpnProtocol !== 'http/1.1')) return reject(new Error('Replacement control unavailable'));
        resolve();
      } catch { reject(new Error('Replacement control unavailable')); }
    }); socket!.once('error',reject); socket!.once('close',() => reject(new Error('Replacement control unavailable'))); }),window);
    current(installed,window);
    let used=false,closed=false;
    const close=()=>{if(closed)return;closed=true;window.signal.removeEventListener('abort',abort);abort();};
    return Object.freeze({
      async send(body:Buffer){
        if(used||closed)return failure();
        used=true;
        try{
        if(socket!.destroyed||!Buffer.isBuffer(body)||!body.length||body.length>2850000)return failure();
        current(installed,window);remaining(window);
    const connected = socket!;
    // Node HTTP closes Connection:close responses with destroySoon after the
    // declared body. Keep this verified TLS socket's read side owned until its
    // actual peer end; the unchanged absolute timer/abort still destroys it.
    connected.destroySoon = () => connected.end();
    // Keep observing the same verified socket after Node detaches its HTTP
    // parser. Count bytes only; HTTPS remains the sole semantic HTTP parser.
    const review=p.purpose==='replacement-model-review-web-binding-v1';
    const answer=p.purpose==='qualified-connected-answer-web-binding-v1'||p.purpose==='qualified-connected-answer-mcp-binding-v1';
    const headerLimit=16384,bodyLimit=answer?262144:p.purpose==='replacement-meeting-worker-binding-v1'?131072:p.purpose==='employee-conversation-web-binding-v1'?4194304:review?262144:pin?MAX_ORIGINAL_BYTES:16384;
    let wireSize=0,headerPrefix=Buffer.alloc(0),headerLength:number|undefined,expectedWireSize:number|undefined,wireFailed=false;
    let rejectWire:(()=>void)|undefined;
    const wireRefuse=()=>{wireFailed=true;rejectWire?.();abort();};
    const observeWire=(chunk:Buffer)=>{
      if(wireFailed)return;wireSize+=chunk.length;
      if(wireSize>headerLimit+bodyLimit){wireRefuse();return;}
      if(headerLength===undefined){
        headerPrefix=Buffer.concat([headerPrefix,chunk.subarray(0,headerLimit-headerPrefix.length)]);
        const boundary=headerPrefix.indexOf('\r\n\r\n');
        if(boundary>=0){headerLength=boundary+4;headerPrefix=Buffer.alloc(0);}
        else if(headerPrefix.length===headerLimit){wireRefuse();return;}
      }
      if(expectedWireSize!==undefined&&wireSize>expectedWireSize)wireRefuse();
    };
    connected.on('data',observeWire);
    const agent = new https.Agent({keepAlive:false,maxSockets:1});
    agent.createConnection = () => connected;
    try {
      const response = new Promise<Readonly<ControlMetadata>|OriginalPacket|UploadResponse|ModelReviewPacket|ConversationPacket|MeetingMetadata|MeetingWorkerPacketV1|ConnectedAnswerPacket|NaturalAnswerPacketV1>((resolve,reject) => {
        let metadata: Readonly<ControlMetadata>|OriginalPacket|UploadResponse|ModelReviewPacket|ConversationPacket|MeetingMetadata|MeetingWorkerPacketV1|ConnectedAnswerPacket|NaturalAnswerPacketV1|undefined; let ended = false; let peerEnded = false; let responseCount = 0;
        let refusalStage='request-event';
        const refuse = () => {console.error('Oracle protected channel refused',refusalStage);reject(new Error('Replacement control unavailable'));};
        rejectWire=refuse;
        connected.once('end',() => { peerEnded = true; });
        connected.once('close',(hadError) => { refusalStage='closed-wire';if (hadError || !peerEnded || !ended || !metadata || wireFailed || headerLength===undefined || expectedWireSize===undefined || wireSize!==expectedWireSize) refuse(); else resolve(metadata); });
        request = https.request({protocol:'https:',hostname:p.server_dns,port:url.port || 443,path:'answer_path'in p?p.answer_path:p.purpose==='replacement-meeting-worker-binding-v1'?p.worker_path:p.purpose==='replacement-meeting-ingress-web-binding-v1'?p.ingress_path:p.purpose==='replacement-meeting-control-web-binding-v1'?p.meeting_path:p.purpose==='employee-conversation-web-binding-v1'?p.conversation_path:p.purpose==='replacement-model-review-web-binding-v1'?p.review_path:p.purpose==='replacement-upload-web-binding-v1'?p.upload_path:p.purpose==='replacement-original-web-binding-v1'?p.original_path:p.control_path,method:'POST',agent,headers:{'Content-Type':'application/json','Content-Length':String(body.length),'Connection':'close'}},res => {
          refusalStage='http-headers';responseCount++; if (responseCount !== 1 || res.statusCode !== 200 || res.headers['content-type'] !== (pin?(pin.media_type==='application/pdf'?'application/pdf':'text/plain; charset=utf-8'):'application/json') || res.headers['content-encoding'] !== undefined || res.headers['transfer-encoding'] !== undefined || res.headers.connection !== 'close') { refuse(); abort(); return; }
          const seen = new Set<string>();
          for (let i = 0; i < res.rawHeaders.length; i += 2) { const h = res.rawHeaders[i]!.toLowerCase(); if (seen.has(h)) { refuse(); abort(); return; } seen.add(h); }
          refusalStage='content-length';const len = res.headers['content-length'];
          if (typeof len !== 'string' || !/^[1-9][0-9]{0,7}$/.test(len) || Number(len) > (answer?262144:p.purpose==='replacement-meeting-worker-binding-v1'?131072:p.purpose==='employee-conversation-web-binding-v1'?4194304:review?262144:pin?MAX_ORIGINAL_BYTES:['replacement-upload-web-binding-v1','replacement-meeting-control-web-binding-v1','replacement-meeting-ingress-web-binding-v1'].includes(p.purpose)?16384:4096) || (pin!==undefined&&Number(len)!==pin.byte_count)) { refuse(); abort(); return; }
          refusalStage='wire-boundary';if(headerLength===undefined){wireRefuse();return;}expectedWireSize=headerLength+Number(len);
          if(wireSize>expectedWireSize){wireRefuse();return;}
          let lease:string|undefined;
          if(pin||review){
            try{
              const value=res.headers[review?'x-oracle-review-valid-until':'x-oracle-original-valid-until'];
              if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value)||res.headers['cache-control']!=='no-store, private'||res.headers['x-content-type-options']!=='nosniff'||res.headers['accept-ranges']!==undefined)throw new Error();
              const end=instant(value);if(end<=Date.now()||end>window.end)throw new Error();
              lease=value;window.end=Math.min(window.end,end);connected.setTimeout(remaining(window));
            }catch{refuse();abort();return;}
          }
          let size = 0; const chunks: Buffer[] = [];const original=pin?Buffer.alloc(pin.byte_count):undefined;
          res.on('data',(chunk: Buffer) => {
            try { connected.setTimeout(remaining(window)); size += chunk.length; if (size > Number(len)) throw new Error(); if(original)chunk.copy(original,size-chunk.length);else chunks.push(chunk); }
            catch { refuse(); abort(); }
          });
          res.once('aborted',refuse); res.once('error',refuse);
          res.once('end',() => { refusalStage='response-body';try { remaining(window); if (!res.complete || size !== Number(len) || res.trailers && Object.keys(res.trailers).length) return refuse(); if(pin&&original&&lease){if(sha256(original)!==pin.original_sha256)throw new Error();if(pin.media_type==='application/pdf'){if(!original.subarray(0,5).equals(Buffer.from('%PDF-')))throw new Error();}else{const text=original.toString('utf8');if(text.includes('\0')||!Buffer.from(text,'utf8').equals(original))throw new Error();}remaining(window);metadata={data:original,validUntil:lease};}else if(review&&lease)metadata={review:parseModelReviewResponse(Buffer.concat(chunks,size)),validUntil:lease};else metadata = answer?parseQualifiedAnswerResponseV1(Buffer.concat(chunks,size)):p.purpose==='replacement-meeting-worker-binding-v1'?parseMeetingWorkerPacketV1(Buffer.concat(chunks,size)):p.purpose==='replacement-meeting-control-web-binding-v1'||p.purpose==='replacement-meeting-ingress-web-binding-v1'?parseMeetingMetadata(Buffer.concat(chunks,size)):p.purpose==='employee-conversation-web-binding-v1'?parseConversationResponse(Buffer.concat(chunks,size)):p.purpose==='replacement-upload-web-binding-v1'?parseUploadResponse(Buffer.concat(chunks,size)):parseControlMetadata(Buffer.concat(chunks,size)); ended = true; } catch { refuse(); abort(); } });
        });
        request.once('error',refuse);
        request.setTimeout(remaining(window),() => { refuse(); abort(); });
        request.end(body);
      });
      return await within(response,window);
    } finally { connected.removeListener('data',observeWire);agent.destroy(); }

        }finally{close();}
      },close
    });
  }catch(error){window.signal.removeEventListener('abort',abort);abort();throw error;}
}
