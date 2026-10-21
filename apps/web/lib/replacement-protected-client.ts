/** Server-only, fixed-peer control transport. No admission, retries, result API,
 * writer capability or fixture fallback. Used by the protected control route. */
import * as https from 'node:https';
import * as tls from 'node:tls';
import { performance } from 'node:perf_hooks';
import { canonicalHash, canonicalJson, canonicalUuid, instant, matchesIdentity, parseClosedJson, readInstalledBinding, readInstalledViewerBinding, readInstalledUploadBinding,readInstalledModelReviewBinding, MAX_ORIGINAL_BYTES, sha256, type InstalledBinding, type ProtectedBinding, type ViewerSourcePin } from './replacement-server-binding';
import { readControlWindow, unavailableControl, privateControlHeaders } from './replacement-control-window';
if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
const failure = (): never => { throw new Error('Replacement control unavailable'); };
const exact = (v: unknown, fields: readonly string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v,k));
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= 2147483647;
export interface ControlMetadata {
  readonly runId: string; readonly journeyRevision: number; readonly controlState: 'pending'|'processing'|'delivered'|'revision_pending'|'cancelled'|'error'|'awaiting-external-authority'|'missing-evidence'|'cancel-requested'|'failed'|'UNKNOWN';
  readonly populationSha256: string; readonly cancelRequested: boolean; readonly remoteStopProven: false; readonly resultAvailable: false;
}
const states = new Set(['pending','processing','delivered','revision_pending','cancelled','error','awaiting-external-authority','missing-evidence','cancel-requested','failed','UNKNOWN']);
/** Descriptive wire validation; a valid DTO grants no access. */
export function parseControlMetadata(bytes: Uint8Array): Readonly<ControlMetadata> {
  const v = parseClosedJson(bytes,4096);
  if (canonicalJson(v) !== Buffer.from(bytes).toString('utf8') || !exact(v,['runId','journeyRevision','controlState','populationSha256','cancelRequested','remoteStopProven','resultAvailable']) || !canonicalUuid(v.runId) || !integer(v.journeyRevision) || typeof v.controlState !== 'string' || !states.has(v.controlState) || !canonicalHash(v.populationSha256) || typeof v.cancelRequested !== 'boolean' || v.remoteStopProven !== false || v.resultAvailable !== false) return failure();
  return Object.freeze(v) as unknown as Readonly<ControlMetadata>;
}
interface Window { readonly wall: number; readonly mono: number; end: number; readonly signal: AbortSignal; proxyMonoEnd: bigint; }
const remaining = (window: Window): number => {
  const ms = Math.min(window.end - Date.now(), window.end - window.wall - (performance.now() - window.mono), Number(window.proxyMonoEnd - process.hrtime.bigint()) / 1e6);
  if (window.signal.aborted || ms <= 0) return failure();
  return Math.max(1, Math.floor(ms));
};
async function within<T>(promise: Promise<T>, window: Window): Promise<T> {
  const ms = remaining(window);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let onAbort: (() => void) | undefined;
  try {
    return await Promise.race([promise,new Promise<never>((_,reject) => {
      timer = setTimeout(() => reject(new Error('Replacement control unavailable')),ms);
      onAbort = () => reject(new Error('Replacement control unavailable'));
      window.signal.addEventListener('abort',onAbort,{once:true});
      if (window.signal.aborted) onAbort();
    })]);
  } finally { if (timer) clearTimeout(timer); if (onAbort) window.signal.removeEventListener('abort',onAbort); }
}
async function identity(binding: Readonly<ProtectedBinding>, window: Window): Promise<void> {
  // The sole production adapter: no supplied snapshot, JWT decoding, role,
  // fixture cookie, service client or caller-selected identity can enter here.
  const { getServerSupabase } = await within(import('./supabase/server'),window);
  const client = await within(getServerSupabase(),window);
  const { data, error } = await within(client.auth.getUser(),window);
  if (error || !data.user?.id) return failure();
  const { getEmployeeForAuthUser } = await within(import('./auth-guard'),window);
  const employee = await within(getEmployeeForAuthUser(data.user.id),window);
  // Supabase exposes this actual configured property at runtime but marks it
  // protected in its TypeScript class; validate the value without a type cast.
  const actualProjectUrl: unknown = Reflect.get(client, 'supabaseUrl');
  if (typeof actualProjectUrl !== 'string') return failure();
  if (!employee || !matchesIdentity(binding, { configuredProjectUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? '', actualProjectUrl, verifiedUserId:data.user.id,employeeId:employee.id,disabledAt:employee.disabledAt })) return failure();
  remaining(window);
}
function current(initial: InstalledBinding<ProtectedBinding>, window: Window): void {
  const again = initial.profile.purpose==='replacement-model-review-web-binding-v1'?readInstalledModelReviewBinding():initial.profile.purpose==='replacement-upload-web-binding-v1'?readInstalledUploadBinding():initial.profile.purpose==='replacement-original-web-binding-v1'?readInstalledViewerBinding():readInstalledBinding();
  if (canonicalJson(again.profile) !== canonicalJson(initial.profile)) return failure();
  window.end = Math.min(window.end,instant(again.profile.expires_at),instant(again.profile.original_horizon));
  remaining(window);
}
function origin(request: Request, binding: Readonly<ProtectedBinding>): void {
  if (request.method !== 'POST' || request.headers.get('origin') !== binding.web_origin || new URL(request.url).origin !== binding.web_origin || request.headers.get('content-type') !== 'application/json' || request.headers.has('content-encoding')) return failure();
}
async function readBody(request: Request, window: Window,limit=65536): Promise<Buffer> {
  const declared = request.headers.get('content-length');
  if (declared !== null && (!/^[1-9][0-9]{0,6}$/.test(declared) || Number(declared) > limit)) return failure();
  if (!request.body) return failure();
  const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let length = 0;
  try {
    for (;;) {
      const next = await within(reader.read(),window); if (next.done) break;
      length += next.value.length; if (length > limit) return failure(); chunks.push(next.value);
    }
    if (!length || (declared !== null && Number(declared) !== length)) return failure();
    return Buffer.concat(chunks,length);
  } finally { void reader.cancel().catch(() => undefined); reader.releaseLock(); }
}
/** Exact Python requester wire, including the unchanged caller narrowing value. */
export function validateControlRequest(bytes: Uint8Array): Readonly<Record<string, unknown>> {
  const v = parseClosedJson(bytes,65536);
  if (!v || typeof v !== 'object' || Array.isArray(v)) return failure();
  const p = v as Record<string,unknown>;
  const common = ['schema_version','operation','caller_deadline'];
  if (p.schema_version !== 1 || typeof p.operation !== 'string') return failure();
  instant(p.caller_deadline);
  if (p.operation === 'reserve') {
    if (!exact(p,[...common,'source_selectors','population_sha256','idempotency_key']) || !canonicalHash(p.population_sha256) || !canonicalUuid(p.idempotency_key) || !Array.isArray(p.source_selectors) || p.source_selectors.length < 1 || p.source_selectors.length > 100) return failure();
    const seen = new Set<string>();
    for (const s of p.source_selectors) {
      if (!exact(s,['source_id','revision']) || !canonicalUuid(s.source_id) || !integer(s.revision) || seen.has(s.source_id)) return failure();
      seen.add(s.source_id);
    }
  } else if (p.operation === 'status') {
    if (!exact(p,[...common,'run_id']) || !canonicalUuid(p.run_id)) return failure();
  } else if (p.operation === 'cancel') {
    if (!exact(p,[...common,'run_id','expected_revision','reason','idempotency_key']) || !canonicalUuid(p.run_id) || !integer(p.expected_revision) || !canonicalUuid(p.idempotency_key) || typeof p.reason !== 'string' || [...p.reason].length < 1 || [...p.reason].length > 1600) return failure();
  } else return failure();
  if (canonicalJson(p) !== Buffer.from(bytes).toString('utf8')) return failure();
  return Object.freeze(p);
}

async function transport(installed: InstalledBinding<ProtectedBinding>, body: Buffer, window: Window,pin?:Readonly<ViewerSourcePin>): Promise<Readonly<ControlMetadata>|OriginalPacket|UploadResponse|ModelReviewPacket> {
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
    // No HTTP bytes exist until chain, hostname and actual leaf DER pass.
    current(installed,window);
    await identity(p,window);
    current(installed,window);
    const connected = socket;
    // Node HTTP closes Connection:close responses with destroySoon after the
    // declared body. Keep this verified TLS socket's read side owned until its
    // actual peer end; the unchanged absolute timer/abort still destroys it.
    connected.destroySoon = () => connected.end();
    // Keep observing the same verified socket after Node detaches its HTTP
    // parser. Count bytes only; HTTPS remains the sole semantic HTTP parser.
    const review=p.purpose==='replacement-model-review-web-binding-v1';
    const headerLimit=16384,bodyLimit=review?262144:pin?MAX_ORIGINAL_BYTES:16384;
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
      const response = new Promise<Readonly<ControlMetadata>|OriginalPacket|UploadResponse|ModelReviewPacket>((resolve,reject) => {
        let metadata: Readonly<ControlMetadata>|OriginalPacket|UploadResponse|ModelReviewPacket|undefined; let ended = false; let peerEnded = false; let responseCount = 0;
        const refuse = () => reject(new Error('Replacement control unavailable'));
        rejectWire=refuse;
        connected.once('end',() => { peerEnded = true; });
        connected.once('close',(hadError) => { if (hadError || !peerEnded || !ended || !metadata || wireFailed || headerLength===undefined || expectedWireSize===undefined || wireSize!==expectedWireSize) refuse(); else resolve(metadata); });
        request = https.request({protocol:'https:',hostname:p.server_dns,port:url.port || 443,path:p.purpose==='replacement-model-review-web-binding-v1'?p.review_path:p.purpose==='replacement-upload-web-binding-v1'?p.upload_path:p.purpose==='replacement-original-web-binding-v1'?p.original_path:p.control_path,method:'POST',agent,headers:{'Content-Type':'application/json','Content-Length':String(body.length),'Connection':'close'}},res => {
          responseCount++; if (responseCount !== 1 || res.statusCode !== 200 || res.headers['content-type'] !== (pin?(pin.media_type==='application/pdf'?'application/pdf':'text/plain; charset=utf-8'):'application/json') || res.headers['content-encoding'] !== undefined || res.headers['transfer-encoding'] !== undefined || res.headers.connection !== 'close') { refuse(); abort(); return; }
          const seen = new Set<string>();
          for (let i = 0; i < res.rawHeaders.length; i += 2) { const h = res.rawHeaders[i]!.toLowerCase(); if (seen.has(h)) { refuse(); abort(); return; } seen.add(h); }
          const len = res.headers['content-length'];
          if (typeof len !== 'string' || !/^[1-9][0-9]{0,7}$/.test(len) || Number(len) > (review?262144:pin?MAX_ORIGINAL_BYTES:p.purpose==='replacement-upload-web-binding-v1'?16384:4096) || (pin!==undefined&&Number(len)!==pin.byte_count)) { refuse(); abort(); return; }
          if(headerLength===undefined){wireRefuse();return;}expectedWireSize=headerLength+Number(len);
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
          res.once('end',() => { try { remaining(window); if (!res.complete || size !== Number(len) || res.trailers && Object.keys(res.trailers).length) return refuse(); if(pin&&original&&lease){if(sha256(original)!==pin.original_sha256)throw new Error();if(pin.media_type==='application/pdf'){if(!original.subarray(0,5).equals(Buffer.from('%PDF-')))throw new Error();}else{const text=original.toString('utf8');if(text.includes('\0')||!Buffer.from(text,'utf8').equals(original))throw new Error();}remaining(window);metadata={data:original,validUntil:lease};}else if(review&&lease)metadata={review:parseModelReviewResponse(Buffer.concat(chunks,size)),validUntil:lease};else metadata = p.purpose==='replacement-upload-web-binding-v1'?parseUploadResponse(Buffer.concat(chunks,size)):parseControlMetadata(Buffer.concat(chunks,size)); ended = true; } catch { refuse(); abort(); } });
        });
        request.once('error',refuse);
        request.setTimeout(remaining(window),() => { refuse(); abort(); });
        request.end(body);
      });
      return await within(response,window);
    } finally { connected.removeListener('data',observeWire);agent.destroy(); }
  } finally { window.signal.removeEventListener('abort',abort); abort(); }
}
export type ProtectedControlResult = Readonly<{available:true;metadata:Readonly<ControlMetadata>}> | Readonly<{available:false}>;
/** Sole production entry point. Captures wall+monotonic start before binding,
 * verified identity or request-body work. Client cancellation only closes this
 * connection; it never proves remote stop. No automatic replay is performed.
 */
export async function requestReplacementControl(request: Request): Promise<ProtectedControlResult> {
  const wall = Date.now(), mono = performance.now();
  const window: Window = {wall,mono,end:wall + 30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
  try {
    const proxyWindow=readControlWindow(request.headers);
    window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
    const installed = readInstalledBinding();
    window.end = Math.min(window.end,instant(installed.profile.expires_at),instant(installed.profile.original_horizon));
    origin(request,installed.profile); remaining(window);
    await identity(installed.profile,window);
    const body = await readBody(request,window); const dto = validateControlRequest(body);
    const callerDeadline = instant(dto.caller_deadline);
    // Caller input narrows this original window; never mint, clamp or renew it.
    if (callerDeadline <= Date.now() || callerDeadline > wall + 30000 || callerDeadline > proxyWindow.wall_end || callerDeadline > instant(installed.profile.original_horizon) || callerDeadline > instant(installed.profile.expires_at)) return failure();
    window.end = Math.min(window.end,callerDeadline);
    current(installed,window); await identity(installed.profile,window); current(installed,window);
    const response = await transport(installed,body,window);
    if(!('runId' in response))return failure();const metadata=response;
    if (dto.operation === 'reserve' ? metadata.populationSha256 !== dto.population_sha256 : metadata.runId !== dto.run_id) return failure();
    current(installed,window); await identity(installed.profile,window); current(installed,window);
    // The original deadline remains private in this invocation and the exact
    // request bytes. A later explicit identical request still needs every gate.
    return Object.freeze({available:true,metadata});
  } catch { return Object.freeze({available:false}); }
}

interface OriginalPacket {readonly data:Buffer;readonly validUntil:string;}
/** Closed original-view wire: exact Python post-validation datetime rendering. */
export function validateOriginalViewRequest(bytes:Uint8Array):Readonly<Record<string,unknown>>{
  const v=parseClosedJson(bytes,4096);
  if(!exact(v,['schema_version','source_id','revision','caller_deadline'])||v.schema_version!==1||!canonicalUuid(v.source_id)||typeof v.revision!=='number'||!Number.isSafeInteger(v.revision)||v.revision<1||typeof v.caller_deadline!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(?!000000)[0-9]{6})?Z$/.test(v.caller_deadline)||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return failure();
  instant(v.caller_deadline);return Object.freeze(v);
}
let viewerBusy=false;
/** Original bytes only; separate installed purpose, no result/truth/writer grant. */
export async function requestReplacementOriginal(request:Request):Promise<Response>{
  const wall=Date.now(),mono=performance.now();
  const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
  if(viewerBusy)return unavailableControl();viewerBusy=true;let handedOff=false;
  try{
    const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
    const installed=readInstalledViewerBinding(),profile=installed.profile;
    window.end=Math.min(window.end,instant(profile.expires_at),instant(profile.original_horizon));
    origin(request,profile);if(['range','if-range','if-match','if-none-match','if-modified-since','if-unmodified-since','expect'].some(k=>request.headers.has(k)))return unavailableControl();
    remaining(window);await identity(profile,window);
    const bytes=await readBody(request,window,4096),dto=validateOriginalViewRequest(bytes),deadline=instant(dto.caller_deadline);
    if(deadline<=Date.now()||deadline>window.end)return unavailableControl();window.end=Math.min(window.end,deadline);
    const pins=profile.sources.filter(pin=>pin.source_id===dto.source_id&&pin.revision===dto.revision);if(pins.length!==1)return unavailableControl();
    current(installed,window);await identity(profile,window);current(installed,window);
    const result=await transport(installed,bytes,window,pins[0]);if(!('data' in result))return unavailableControl();
    current(installed,window);await identity(profile,window);current(installed,window);remaining(window);
    let offset=0,timer:ReturnType<typeof setTimeout>|undefined,closed=false,controller:ReadableStreamDefaultController<Uint8Array>|undefined;
    const release=()=>{if(closed)return;closed=true;if(timer)clearTimeout(timer);request.signal.removeEventListener('abort',abort);viewerBusy=false;};
    const abort=()=>{if(closed)return;controller?.error(new Error('Replacement control unavailable'));release();};
    const stream=new ReadableStream<Uint8Array>({
      start(c){controller=c;timer=setTimeout(abort,remaining(window));request.signal.addEventListener('abort',abort,{once:true});if(request.signal.aborted)abort();},
      pull(c){try{current(installed,window);remaining(window);const end=Math.min(offset+65536,result.data.length);c.enqueue(result.data.subarray(offset,end));offset=end;if(offset===result.data.length){c.close();release();}}catch{abort();}},
      cancel(){release();},
    },{highWaterMark:0});
    handedOff=true;return new Response(stream,{status:200,headers:{...privateControlHeaders,'Content-Type':pins[0]!.media_type==='application/pdf'?'application/pdf':'text/plain; charset=utf-8','Content-Length':String(result.data.length),'Content-Disposition':pins[0]!.media_type==='application/pdf'?'inline; filename="original.pdf"':'inline; filename="original.txt"'}});
  }catch{return unavailableControl();}
  finally{if(!handedOff)viewerBusy=false;}
}

interface ModelReviewPacket {readonly review:Readonly<Record<string,unknown>>;readonly validUntil:string;}
function reviewEnum(value:unknown,choices:readonly string[]):boolean{return typeof value==='string'&&choices.includes(value);}
function reviewScope(v:unknown):boolean{
 if(!exact(v,['schema_version','process','customer','product','region'])||v.schema_version!==1)return false;
 return ['process','customer','product','region'].every(k=>{const d=v[k];return exact(d,['schema_version','mode','identities'])&&d.schema_version===1&&reviewEnum(d.mode,['unknown','all','exact'])&&Array.isArray(d.identities)&&d.identities.length<=64&&d.identities.every(canonicalUuid)&&new Set(d.identities).size===d.identities.length&&(d.mode==='exact')===(d.identities.length>0)&&canonicalJson(d.identities)===canonicalJson([...d.identities].sort());});
}
function reviewAssertion(v:unknown):boolean{
 if(!exact(v,['schema_version','assertion_id','revision','predecessor_hash','subject_id','predicate','value','unit','provenance','scope','valid_time','valid_from','valid_to','supporting_observations','opposing_observations','unknown_finding_ids','temporal_observations'])||v.schema_version!==1||!canonicalUuid(v.assertion_id)||!integer(v.revision)||!canonicalUuid(v.subject_id)||(v.revision===1)!==(v.predecessor_hash===null)||(v.predecessor_hash!==null&&!canonicalHash(v.predecessor_hash))||typeof v.predicate!=='string'||!v.predicate.length||v.predicate.length>200||typeof v.value!=='string'||!v.value.length||v.value.length>4000||(v.unit!==null&&(typeof v.unit!=='string'||!v.unit.length||v.unit.length>100))||!reviewEnum(v.provenance,['employee_account','documented_process','reported_policy','unknown'])||!reviewScope(v.scope))return false;
 if(v.valid_time==='unknown'){if(v.valid_from!==null||v.valid_to!==null)return false;}else if(v.valid_time==='evidenced'){const at=instant(v.valid_from);if(v.valid_to!==null&&instant(v.valid_to)<=at)return false;}else return false;
 return ['supporting_observations','opposing_observations','unknown_finding_ids','temporal_observations'].every(k=>Array.isArray(v[k])&&v[k].length<=1000&&v[k].every((x:unknown)=>typeof x==='string'&&x.length>0&&x.length<=200));
}
function reviewEvidence(v:unknown):boolean{
 if(!exact(v,['supporting','opposing','unknown','temporal']))return false;
 return Object.values(v).every(group=>Array.isArray(group)&&group.length<=1000&&group.every(q=>{
  if(!exact(q,['schema_version','ref','start','end','quote'])||q.schema_version!==1||!Number.isSafeInteger(q.start)||(q.start as number)<0||!integer(q.end)||(q.end as number)<=(q.start as number)||typeof q.quote!=='string'||q.quote.length>65536||!exact(q.ref,['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id']))return false;
  const r=q.ref;return r.schema_version===1&&canonicalUuid(r.workspace_id)&&canonicalUuid(r.source_id)&&integer(r.revision)&&canonicalHash(r.original_sha256)&&canonicalHash(r.reading_sha256)&&typeof r.parser_id==='string'&&r.parser_id.length>0&&r.parser_id.length<=1024;
 }));
}
export function parseModelReviewResponse(bytes:Uint8Array):Readonly<Record<string,unknown>>{
  const v=parseClosedJson(bytes,262144);
  if(!v||typeof v!=='object'||Array.isArray(v)||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return failure();
  const dto=v as Record<string,unknown>;
  if(!canonicalUuid(dto.modelId)||dto.policyEligibility!=='unknown'||dto.automaticRebase!==false)return failure();
  // Exact response union is selected by the actual fixed service operation.
  const allowed='decision' in dto?['modelId','version','decision','decisionKind','eventId','policyEligibility','modelConfirmed','automaticRebase']:
    dto.basePermitted===true?['modelId','currentVersion','currentContentHash','conflict','basePermitted','message','automaticRebase','policyEligibility','baseRecordedAt','currentRecordedAt','currentAssertions','totalAssertions','businessDecisions','changes','totalChanges','truncated']:
    ['modelId','currentVersion','currentContentHash','conflict','basePermitted','message','automaticRebase','policyEligibility'];
  if(!exact(dto,allowed))return failure();
  if('decision' in dto){if(!integer(dto.version)||!reviewEnum(dto.decision,['accept','reject'])||!reviewEnum(dto.decisionKind,['employee-account','process-policy','company-policy'])||!canonicalUuid(dto.eventId)||dto.modelConfirmed!==false)return failure();}
  else if(!integer(dto.currentVersion)||!canonicalHash(dto.currentContentHash)||typeof dto.conflict!=='boolean'||typeof dto.basePermitted!=='boolean'||typeof dto.message!=='string'||dto.message.length>256)return failure();
  if(dto.basePermitted===true){instant(dto.baseRecordedAt);instant(dto.currentRecordedAt);if(!Array.isArray(dto.businessDecisions)||dto.businessDecisions.length>64||!Array.isArray(dto.currentAssertions)||dto.currentAssertions.length>64||typeof dto.totalAssertions!=='number'||!Number.isSafeInteger(dto.totalAssertions)||dto.totalAssertions<dto.currentAssertions.length||!Array.isArray(dto.changes)||dto.changes.length>64||typeof dto.totalChanges!=='number'||!Number.isSafeInteger(dto.totalChanges)||dto.totalChanges<dto.changes.length||typeof dto.truncated!=='boolean')return failure();}
  if(dto.basePermitted===true){
    for(const item of dto.currentAssertions as unknown[]){if(!exact(item,['assertion','evidence'])||!reviewAssertion(item.assertion)||!reviewEvidence(item.evidence))return failure();}
    for(const item of dto.changes as unknown[]){if(!exact(item,['assertionId','change','before','after','beforeEvidence','afterEvidence'])||!canonicalUuid(item.assertionId)||!reviewEnum(item.change,['added','retired','changed'])||![item.before,item.after].every(a=>a===null||reviewAssertion(a))||![item.beforeEvidence,item.afterEvidence].every(e=>e===null||reviewEvidence(e)))return failure();}
    for(const item of dto.businessDecisions as unknown[]){if(!exact(item,['eventId','recordedAt','decisionKind','scopeSha256','assertions','challenged','withdrawn','policyInForce'])||!canonicalUuid(item.eventId)||!canonicalHash(item.scopeSha256)||!reviewEnum(item.decisionKind,['employee-account','process-policy','company-policy'])||typeof item.challenged!=='boolean'||typeof item.withdrawn!=='boolean'||typeof item.policyInForce!=='boolean'||item.withdrawn&&item.policyInForce||(item.decisionKind!=='company-policy'&&item.policyInForce)||!Array.isArray(item.assertions)||item.assertions.length>1000||item.assertions.some(a=>!exact(a,['assertion_id','revision'])||!canonicalUuid(a.assertion_id)||!integer(a.revision)))return failure();instant(item.recordedAt);}
  }
  return Object.freeze(dto);
}
export function validateModelReviewRequest(bytes:Uint8Array):Readonly<Record<string,unknown>>{
  const v=parseClosedJson(bytes,65536);
  if(!v||typeof v!=='object'||Array.isArray(v)||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return failure();
  const p=v as Record<string,unknown>;if(p.schema_version!==1||!canonicalUuid(p.model_id))return failure();instant(p.caller_deadline);
  const common=['schema_version','operation','model_id','caller_deadline'];
  if(p.operation==='inspect'){if(!exact(p,[...common,'base_version'])||!integer(p.base_version))return failure();}
  else if(p.operation==='decide'){
    if(!exact(p,[...common,'version','expected_hash','decision','decision_kind','scope','assertions','command_id'])||!integer(p.version)||!canonicalHash(p.expected_hash)||!reviewEnum(p.decision,['accept','reject'])||!reviewEnum(p.decision_kind,['employee-account','process-policy','company-policy'])||!canonicalUuid(p.command_id)||!Array.isArray(p.assertions)||p.assertions.length<1||p.assertions.length>64)return failure();
    const ids=new Set<string>();for(const a of p.assertions){if(!exact(a,['assertion_id','revision'])||!canonicalUuid(a.assertion_id)||!integer(a.revision)||ids.has(a.assertion_id))return failure();ids.add(a.assertion_id);}
    if(!exact(p.scope,['schema_version','process','customer','product','region'])||p.scope.schema_version!==1)return failure();
    for(const key of ['process','customer','product','region']){const d=p.scope[key];if(!exact(d,['schema_version','mode','identities'])||d.schema_version!==1||!reviewEnum(d.mode,['unknown','all','exact'])||!Array.isArray(d.identities)||d.identities.length>64||d.identities.some(x=>!canonicalUuid(x))||new Set(d.identities).size!==d.identities.length||(d.mode==='exact')!==(d.identities.length>0)||canonicalJson(d.identities)!==canonicalJson([...d.identities].sort()))return failure();}
  }else return failure();
  return Object.freeze(p);
}
export async function requestModelReview(request:Request):Promise<Response>{
  const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
  try{
    const proxy=readControlWindow(request.headers);window.end=Math.min(window.end,proxy.wall_end);window.proxyMonoEnd=BigInt(proxy.mono_end);
    const installed=readInstalledModelReviewBinding(),profile=installed.profile;window.end=Math.min(window.end,instant(profile.expires_at),instant(profile.original_horizon));
    origin(request,profile);await identity(profile,window);
    const body=await readBody(request,window),dto=validateModelReviewRequest(body),end=instant(dto.caller_deadline);
    if(dto.model_id!==profile.model_id||end<=Date.now()||end>window.end)return failure();window.end=end;
    current(installed,window);await identity(profile,window);current(installed,window);
    const result=await transport(installed,body,window);if(!('review' in result)||result.review.modelId!==dto.model_id)return failure();
    current(installed,window);await identity(profile,window);current(installed,window);remaining(window);
    return Response.json(result.review,{status:200,headers:privateControlHeaders});
  }catch{return unavailableControl();}
}

// Same fixed auth/TLS/file/window owners; only this installed purpose chooses
// the chunk endpoint. No transport selector is accepted from the browser.
import { UPLOAD_CHUNK_BYTES,UPLOAD_MAX_REQUEST_BYTES,type UploadResponse } from './replacement-upload-contract';
export function validateUploadRequest(bytes:Uint8Array):Readonly<Record<string,unknown>>{
 const v=parseClosedJson(bytes,UPLOAD_MAX_REQUEST_BYTES);
 if(!v||typeof v!=='object'||Array.isArray(v))return failure();const p=v as Record<string,unknown>;
 if(p.schema_version!==1||typeof p.operation!=='string'||typeof p.caller_deadline!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(?!000000)[0-9]{6})?Z$/.test(p.caller_deadline)||canonicalJson(p)!==Buffer.from(bytes).toString('utf8'))return failure();
 instant(p.caller_deadline);
 if(p.operation==='begin'){
  if(!exact(p,['schema_version','operation','source_id','expected_head','idempotency_key','filename','original_sha256','byte_count','caller_deadline'])||!Number.isSafeInteger(p.expected_head)||(p.expected_head as number)<0||((p.source_id===null)!==(p.expected_head===0))||(p.source_id!==null&&!canonicalUuid(p.source_id))||!canonicalUuid(p.idempotency_key)||typeof p.filename!=='string'||[...p.filename].length<1||[...p.filename].length>255||/[\/\\\u0000-\u001f\u007f]/.test(p.filename)||!canonicalHash(p.original_sha256)||!Number.isSafeInteger(p.byte_count)||(p.byte_count as number)<1||(p.byte_count as number)>MAX_ORIGINAL_BYTES)return failure();
 }else{
  const fields=['schema_version','operation','reservation_id','source_id','revision','begin_sha256','caller_deadline'];
  if(!canonicalUuid(p.reservation_id)||!canonicalUuid(p.source_id)||!Number.isSafeInteger(p.revision)||(p.revision as number)<1||!canonicalHash(p.begin_sha256))return failure();
  if(p.operation==='chunk'){
   if(!exact(p,[...fields,'chunk_index','offset','chunk_sha256','data_base64'])||!Number.isSafeInteger(p.chunk_index)||(p.chunk_index as number)<0||(p.chunk_index as number)>12||p.offset!==(p.chunk_index as number)*UPLOAD_CHUNK_BYTES||!canonicalHash(p.chunk_sha256)||typeof p.data_base64!=='string'||p.data_base64.length>2796204||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(p.data_base64))return failure();
   const data=Buffer.from(p.data_base64,'base64');if(!data.length||data.length>UPLOAD_CHUNK_BYTES||data.toString('base64')!==p.data_base64||sha256(data)!==p.chunk_sha256)return failure();
  }else if(!['status','cancel','finalize'].includes(p.operation)||!exact(p,fields))return failure();
 }
 return Object.freeze(p);
}
export function parseUploadResponse(bytes:Uint8Array):Readonly<UploadResponse>{
 const v=parseClosedJson(bytes,16384);
 if(!exact(v,['schema_version','state','reservation_id','source_id','revision','begin_sha256','received_bytes','next_chunk_index','valid_until','qualification','remote_stop_proven','observation_only','source_snapshot'])||v.schema_version!==1||typeof v.state!=='string'||!['reserved','receiving','finalizing','committed','cancelled','expired','UNKNOWN'].includes(v.state)||!canonicalUuid(v.reservation_id)||!canonicalUuid(v.source_id)||!Number.isSafeInteger(v.revision)||(v.revision as number)<1||!canonicalHash(v.begin_sha256)||!Number.isSafeInteger(v.received_bytes)||(v.received_bytes as number)<0||(v.received_bytes as number)>MAX_ORIGINAL_BYTES||!Number.isSafeInteger(v.next_chunk_index)||(v.next_chunk_index as number)<0||(v.next_chunk_index as number)>13||v.qualification!==false||v.remote_stop_proven!==false||v.observation_only!==true||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return failure();
 instant(v.valid_until);
 if(v.next_chunk_index!==Math.ceil((v.received_bytes as number)/UPLOAD_CHUNK_BYTES)||(v.state==='reserved'&&v.received_bytes!==0)||(['receiving','committed'].includes(v.state)&&v.received_bytes===0))return failure();
 if(v.source_snapshot!==null){const s=v.source_snapshot;if(v.state!=='committed'||!exact(s,['sourceId','revision','originalSha256','byteCount','mediaType','filename','state','qualifiedSourceRef'])||s.sourceId!==v.source_id||s.revision!==v.revision||!canonicalHash(s.originalSha256)||s.byteCount!==v.received_bytes||s.mediaType!=='application/pdf'||typeof s.filename!=='string'||[...s.filename].length<1||[...s.filename].length>255||s.state!=='awaiting_original_reading'||s.qualifiedSourceRef!==null)return failure();Object.freeze(s);}
 return Object.freeze(v) as unknown as Readonly<UploadResponse>;
}
export async function requestReplacementUpload(request:Request):Promise<Response>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
  const installed=readInstalledUploadBinding(),profile=installed.profile;window.end=Math.min(window.end,instant(profile.expires_at),instant(profile.original_horizon));
  origin(request,profile);if(['range','if-range','if-match','if-none-match','if-modified-since','if-unmodified-since','expect'].some(k=>request.headers.has(k)))return unavailableControl();
  await identity(profile,window);const body=await readBody(request,window,UPLOAD_MAX_REQUEST_BYTES),dto=validateUploadRequest(body),deadline=instant(dto.caller_deadline);
  if(deadline<=Date.now()||deadline>window.end)return unavailableControl();window.end=Math.min(window.end,deadline);
  current(installed,window);await identity(profile,window);current(installed,window);
  const result=await transport(installed,body,window);if(!('observation_only' in result))return unavailableControl();
  const end=instant(result.valid_until);if(end<=Date.now()||end>window.end)return unavailableControl();window.end=Math.min(window.end,end);
  if(dto.operation!=='begin'&&(dto.reservation_id!==result.reservation_id||dto.source_id!==result.source_id||dto.revision!==result.revision||dto.begin_sha256!==result.begin_sha256))return unavailableControl();
  if(dto.operation==='begin'&&(result.begin_sha256!==sha256(body)||(dto.source_id!==null&&dto.source_id!==result.source_id)||result.revision!==(dto.expected_head as number)+1||result.received_bytes>(dto.byte_count as number)))return unavailableControl();
  if(dto.operation!=='finalize'&&result.source_snapshot!==null)return unavailableControl();
  current(installed,window);await identity(profile,window);current(installed,window);remaining(window);
  return new Response(canonicalJson(result),{status:200,headers:{...privateControlHeaders,'Content-Type':'application/json'}});
 }catch{return unavailableControl();}
}

/** Page props use the SAME actual identity owner; never disclose the installed
 * model selector merely because a different employee can render the page. */
export async function authenticatedModelReviewPageModel():Promise<string|undefined>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const installed=readInstalledModelReviewBinding();window.end=Math.min(window.end,instant(installed.profile.expires_at),instant(installed.profile.original_horizon));
  current(installed,window);await identity(installed.profile,window);current(installed,window);return installed.profile.model_id;
 }catch{return undefined;}
}
