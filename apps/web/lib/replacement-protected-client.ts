import {validateConnectedAnswerQuery,type ConnectedAnswerPacket} from '@oracle/shared/protected-client-contracts';
import {validateNaturalQuestionV1,naturalQuerySHA256V1,type NaturalQuestionV1} from '@oracle/shared/protected-natural-question-contract';
import {validateIndustryQuestionV1,industryQuerySHA256V1,type IndustryQuestionV1} from '@oracle/shared/protected-natural-question-contract';
import {validateWorkspaceQuestionV1,workspaceQuerySHA256V1,type WorkspaceQuestionV1} from '@oracle/shared/protected-natural-question-contract';
export {validateNaturalQuestionV1,parseNaturalAnswerResponseV1,type NaturalAnswerPacketV1} from '@oracle/shared/protected-natural-question-contract';
export {validateConnectedAnswerQuery,parseConnectedAnswerResponse,type ConnectedAnswerPacket} from '@oracle/shared/protected-client-contracts';
/** Web-only verified Supabase/employee adapter and retained public wrappers.
 * All wire, protected-file, closed payload and original clock owners are shared.
 */
import {performance} from 'node:perf_hooks';
import {employeeRecipientIndexConfiguredV1,readInstalledEmployeeBindingV1,type EmployeeBindingPurposeV1,type IdentitySnapshot,canonicalHash,canonicalJson,canonicalUuid,instant,matchesIdentity,parseClosedJson,readInstalledBinding,readInstalledViewerBinding,readInstalledUploadBinding,readInstalledMeetingBinding,readInstalledMeetingIngressBinding,verifyInstalledMeetingIngress,readInstalledModelReviewBinding,readInstalledConversationBinding,readInstalledConnectedAnswerBinding,readInstalledMcpAnswerBinding,MAX_ORIGINAL_BYTES,sha256,type InstalledBinding,type ProtectedBinding,type ViewerSourcePin} from './replacement-server-binding';
import {isConversationPath,readControlWindow,unavailableControl,privateControlHeaders,remaining,within,canonicalInstantV1,type Window} from './replacement-control-window';
import {parseConversationResponse,validateConversationRequest,type ConversationPacket} from './replacement-conversation-contract';
import {UPLOAD_CHUNK_BYTES,UPLOAD_MAX_REQUEST_BYTES,type UploadResponse} from './replacement-upload-contract';
import {openProtectedChannelV1,current} from '@oracle/shared/protected-service-channel';
import {reviewEnum,parseControlMetadata,validateControlRequest,validateOriginalViewRequest,parseModelReviewResponse,validateModelReviewRequest,validateUploadRequest,parseUploadResponse,parseMeetingMetadata,validateMeetingControl,type ControlMetadata,type OriginalPacket,type ModelReviewPacket,type MeetingMetadata} from '@oracle/shared/protected-client-contracts';
export {parseControlMetadata,validateControlRequest,validateOriginalViewRequest,parseModelReviewResponse,validateModelReviewRequest,validateUploadRequest,parseUploadResponse,parseMeetingMetadata,validateMeetingControl,type ControlMetadata,type MeetingMetadata} from '@oracle/shared/protected-client-contracts';

if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
const failure = (): never => { throw new Error('Replacement control unavailable'); };
const exact = (v: unknown, fields: readonly string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v,k));
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= 2147483647;
async function verifiedEmployeeSnapshotV1(window:Window):Promise<IdentitySnapshot>{
  // Actual server auth and SQL identity only; never a supplied request actor.
  const {getServerSupabase}=await within(import('./supabase/server'),window);
  const client=await within(getServerSupabase(),window);
  const {data,error}=await within(client.auth.getUser(),window);
  if(error||!data.user?.id)return failure();
  const guard=await within(import('./auth-guard'),window);
  const lookup=employeeRecipientIndexConfiguredV1()?guard.getUniqueEmployeeForAuthUserV1:guard.getEmployeeForAuthUser;
  const employee=await within(lookup(data.user.id),window),actualProjectUrl:unknown=Reflect.get(client,'supabaseUrl');
  if(!employee||typeof actualProjectUrl!=='string')return failure();remaining(window);
  return {configuredProjectUrl:process.env.NEXT_PUBLIC_SUPABASE_URL??'',actualProjectUrl,verifiedUserId:data.user.id,employeeId:employee.id,disabledAt:employee.disabledAt};
}
async function identity(binding:Readonly<Exclude<ProtectedBinding,{purpose:'replacement-meeting-ingress-web-binding-v1'|'replacement-meeting-worker-binding-v1'|'meeting-normalization-worker-v1'|'meeting-supervision-service-binding-v1'|'meeting-ingress-queue-worker-v1'}>>,window:Window):Promise<void>{
  if(!matchesIdentity(binding,await verifiedEmployeeSnapshotV1(window)))return failure();remaining(window);
}
async function installedForEmployeeV1<P extends EmployeeBindingPurposeV1>(kind:P,window:Window){
  // This index is an independently installed selector, never session authority.
  // Partial/malformed configuration refuses; it cannot fall back to singleton.
  if(employeeRecipientIndexConfiguredV1()){
    const value=readInstalledEmployeeBindingV1(kind,await verifiedEmployeeSnapshotV1(window));current(value,window);return value;
  }
  const loaders={control:readInstalledBinding,viewer:readInstalledViewerBinding,upload:readInstalledUploadBinding,review:readInstalledModelReviewBinding,conversation:readInstalledConversationBinding,meeting:readInstalledMeetingBinding,answer:readInstalledConnectedAnswerBinding,'mcp-answer':readInstalledMcpAnswerBinding};
  return loaders[kind]();
}

function origin(request: Request, binding: Readonly<Exclude<ProtectedBinding,{purpose:'replacement-meeting-ingress-web-binding-v1'|'replacement-meeting-worker-binding-v1'|'meeting-normalization-worker-v1'|'meeting-supervision-service-binding-v1'|'meeting-ingress-queue-worker-v1'}>>): void {
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
    const installed = await installedForEmployeeV1('control',window) as InstalledBinding<import('./replacement-server-binding').ServerBinding>;
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
let viewerBusy=false;
/** Original bytes only; separate installed purpose, no result/truth/writer grant. */
export async function requestReplacementOriginal(request:Request):Promise<Response>{
  const wall=Date.now(),mono=performance.now();
  const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
  if(viewerBusy)return unavailableControl();viewerBusy=true;let handedOff=false;
  try{
    const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
    const installed=await installedForEmployeeV1('viewer',window) as InstalledBinding<import('./replacement-server-binding').ViewerBinding>,profile=installed.profile;
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
export async function requestModelReview(request:Request):Promise<Response>{
  const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
  try{
    const proxy=readControlWindow(request.headers);window.end=Math.min(window.end,proxy.wall_end);window.proxyMonoEnd=BigInt(proxy.mono_end);
    const installed=await installedForEmployeeV1('review',window) as InstalledBinding<import('./replacement-server-binding').ModelReviewBinding>,profile=installed.profile;window.end=Math.min(window.end,instant(profile.expires_at),instant(profile.original_horizon));
    origin(request,profile);await identity(profile,window);
    const body=await readBody(request,window),dto=validateModelReviewRequest(body),end=instant(dto.caller_deadline);
    if(dto.model_id!==profile.model_id||end<=Date.now()||end>window.end)return failure();window.end=end;
    current(installed,window);await identity(profile,window);current(installed,window);
    const result=await transport(installed,body,window);if(!('review' in result)||result.review.modelId!==dto.model_id)return failure();
    current(installed,window);await identity(profile,window);current(installed,window);remaining(window);
    return Response.json(result.review,{status:200,headers:privateControlHeaders});
  }catch{return unavailableControl();}
}
export async function requestReplacementUpload(request:Request):Promise<Response>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
  const installed=await installedForEmployeeV1('upload',window) as InstalledBinding<import('./replacement-server-binding').UploadBinding>,profile=installed.profile;window.end=Math.min(window.end,instant(profile.expires_at),instant(profile.original_horizon));
  origin(request,profile);if(['range','if-range','if-match','if-none-match','if-modified-since','if-unmodified-since','expect'].some(k=>request.headers.has(k)))return unavailableControl();
  await identity(profile,window);const body=await readBody(request,window,UPLOAD_MAX_REQUEST_BYTES),dto=validateUploadRequest(body),deadline=instant(dto.caller_deadline);
  if(deadline<=Date.now()||deadline>window.end)return unavailableControl();window.end=Math.min(window.end,deadline);
  current(installed,window);await identity(profile,window);current(installed,window);
  const result=await transport(installed,body,window);if(!('reservation_id' in result))return unavailableControl();
  const end=instant(result.valid_until);if(end<=Date.now()||end>window.end)return unavailableControl();window.end=Math.min(window.end,end);
  if(dto.operation!=='begin'&&(dto.reservation_id!==result.reservation_id||dto.source_id!==result.source_id||dto.revision!==result.revision||dto.begin_sha256!==result.begin_sha256))return unavailableControl();
  if(dto.operation==='begin'&&(result.begin_sha256!==sha256(body)||(dto.source_id!==null&&dto.source_id!==result.source_id)||result.revision!==(dto.expected_head as number)+1||result.received_bytes>(dto.byte_count as number)))return unavailableControl();
  if(dto.operation!=='finalize'&&result.source_snapshot!==null)return unavailableControl();
  current(installed,window);await identity(profile,window);current(installed,window);remaining(window);
  return new Response(canonicalJson(result),{status:200,headers:{...privateControlHeaders,'Content-Type':'application/json'}});
 }catch{return unavailableControl();}
}
export async function requestReplacementMeetingControl(request:Request):Promise<Response>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
  const installed=await installedForEmployeeV1('meeting',window) as InstalledBinding<import('./replacement-server-binding').MeetingControlBinding>,p=installed.profile;window.end=Math.min(window.end,instant(p.expires_at),instant(p.original_horizon));origin(request,p);
  await identity(p,window);const bytes=await readBody(request,window,16384),dto=validateMeetingControl(bytes);const end=instant(dto.caller_deadline);
  if(dto.meeting_id!==p.meeting_id||end<=Date.now()||end>window.end)return unavailableControl();window.end=Math.min(window.end,end);
  const result=await transport(installed,bytes,window);if(!('meeting_id' in result)||result.meeting_id!==p.meeting_id)return unavailableControl();
  const lease=instant(result.valid_until);if(lease<=Date.now()||lease>window.end)return unavailableControl();window.end=Math.min(window.end,lease);
  current(installed,window);await identity(p,window);current(installed,window);return new Response(canonicalJson(result),{status:200,headers:{...privateControlHeaders,'Content-Type':'application/json'}});
 }catch{return unavailableControl();}
}
/** Sole fixed provider-ingress entry. There is no cookie/user/auth callback seam.
 * Its original window is captured here before binding/read/verification, and
 * never inferred from an inbound header or provider signature timestamp. */
export async function requestReplacementMeetingIngress(request:Request):Promise<Response>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  if(request.method!=='POST'||request.headers.get('content-type')!=='application/json'||request.headers.has('content-encoding'))return unavailableControl();
  const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
  const installed=readInstalledMeetingIngressBinding(),p=installed.profile;window.end=Math.min(window.end,instant(p.expires_at),instant(p.original_horizon));
  const raw=await readBody(request,window,1024*1024);verifyInstalledMeetingIngress(raw,request.headers);remaining(window);
  const event=parseClosedJson(raw,1024*1024);
  if(!event||typeof event!=='object'||Array.isArray(event))return unavailableControl();
  const e=event as Record<string,unknown>,data=e.data;if(typeof e.event!=='string'||!(/^(transcript\.(data|partial_data|done|failed)|bot\.[a-z_]{1,64})$/.test(e.event))||!data||typeof data!=='object'||Array.isArray(data))return unavailableControl();
  const d=data as Record<string,unknown>,bot=d.bot;if(!bot||typeof bot!=='object'||Array.isArray(bot)||!canonicalUuid((bot as Record<string,unknown>).id))return unavailableControl();
  const words=d.data&&typeof d.data==='object'&&!Array.isArray(d.data)?(d.data as Record<string,unknown>).words:undefined;
  if(words!==undefined&&(!Array.isArray(words)||words.length>4096))return unavailableControl();
  // Canonical initial absolute deadline is generated once; never renewed. Raw
  // signed provider bytes remain byte-identical inside this closed envelope.
  const deadline=canonicalInstantV1(Math.floor(window.end));
  const body=Buffer.from(canonicalJson({schema_version:1,operation:'ingress',provider_event_id:request.headers.get('webhook-id'),bot_id:(bot as Record<string,unknown>).id,event_kind:e.event,verifier_secret_sha256:p.verifier_secret_sha256,raw_base64:raw.toString('base64'),caller_deadline:deadline}));
  current(installed,window);const result=await transport(installed,body,window);
  if(!('meeting_id' in result)||!('ingress_id' in result)||result.meeting_id!==p.meeting_id||!result.ingress_id)return unavailableControl();
  const lease=instant(result.valid_until);if(lease<=Date.now()||lease>window.end)return unavailableControl();window.end=Math.min(window.end,lease);current(installed,window);
  return new Response(null,{status:202,headers:privateControlHeaders});
 }catch{return unavailableControl();}
}
/** Page props use the SAME actual identity owner; never disclose the installed
 * model selector merely because a different employee can render the page. */
export async function authenticatedModelReviewPageModel():Promise<string|undefined>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const installed=await installedForEmployeeV1('review',window) as InstalledBinding<import('./replacement-server-binding').ModelReviewBinding>;window.end=Math.min(window.end,instant(installed.profile.expires_at),instant(installed.profile.original_horizon));
  current(installed,window);await identity(installed.profile,window);current(installed,window);return installed.profile.model_id;
 }catch{return undefined;}
}

/** Same sole verified identity/clock/socket owner, separate installed purpose. */
export async function requestEmployeeConversation(request:Request):Promise<ConversationPacket|undefined>{
 const wall=Date.now(),mono=performance.now();const window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const url=new URL(request.url);if(!isConversationPath(url.pathname)||url.search)return undefined;
  const proxyWindow=readControlWindow(request.headers);window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
  const installed=await installedForEmployeeV1('conversation',window) as InstalledBinding<import('./replacement-server-binding').ConversationBinding>;window.end=Math.min(window.end,instant(installed.profile.expires_at),instant(installed.profile.original_horizon));
  origin(request,installed.profile);remaining(window);await identity(installed.profile,window);
  const body=await readBody(request,window);const q=validateConversationRequest(body);const deadline=instant(q.caller_deadline);
  if(deadline<=Date.now()||deadline>window.end||deadline>wall+30000)return undefined;window.end=Math.min(window.end,deadline);
  if(url.pathname!=='/api/consultant/interviews'&&q.thread_id!==url.pathname.split('/')[4])return undefined;
  if(url.pathname==='/api/consultant/interviews'&&q.operation!==undefined&&!['list','status'].includes(String(q.operation)))return undefined;
  current(installed,window);await identity(installed.profile,window);current(installed,window);
  const response=await transport(installed,body,window);
  if('runId'in response||'data'in response||!('schema_version'in response))return undefined;
  const result=response as ConversationPacket;
  if('principal_id'in result&&(result.principal_id!==installed.profile.principal_id||result.workspace_id!==installed.profile.workspace_id))return undefined;
  if(q.thread_id&&'thread_id'in result&&result.thread_id!==q.thread_id)return undefined;
  current(installed,window);await identity(installed.profile,window);current(installed,window);return result;
 }catch{return undefined;}
}
async function transport(installed:InstalledBinding<ProtectedBinding>,body:Buffer,window:Window,pin?:Readonly<ViewerSourcePin>){
 if(installed.profile.purpose==='meeting-ingress-queue-worker-v1'||installed.profile.purpose==='meeting-normalization-worker-v1'||installed.profile.purpose==='meeting-supervision-service-binding-v1')return failure();
 const channel=await openProtectedChannelV1(installed,window,pin);
 try{
  current(installed,window);
  if(installed.profile.purpose!=='replacement-meeting-ingress-web-binding-v1'&&installed.profile.purpose!=='replacement-meeting-worker-binding-v1')await identity(installed.profile,window);
  current(installed,window);
  return await channel.send(body);
 }finally{channel.close();}
}

/** SAME verified user/current employee owner; fixed channel selected by source. */
export async function authenticatedConnectedAnswerChannel(request:Request,channel:'web'|'mcp'):Promise<boolean>{
 const wall=Date.now(),mono=performance.now(),window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const proxy=readControlWindow(request.headers);window.end=Math.min(window.end,proxy.wall_end);window.proxyMonoEnd=BigInt(proxy.mono_end);
  const installed=await installedForEmployeeV1(channel==='web'?'answer':'mcp-answer',window) as InstalledBinding<import('./replacement-server-binding').ConnectedAnswerBinding>;window.end=Math.min(window.end,instant(installed.profile.expires_at),instant(installed.profile.original_horizon));
  origin(request,installed.profile);await identity(installed.profile,window);current(installed,window);remaining(window);return true;
 }catch{return false;}
}
async function connectedAnswer(request:Request,channel:'web'|'mcp',supplied?:{kind:'legacy';query:unknown}|{kind:'natural';question:string}):Promise<Response>{
 let phase='original-window';
 // Fixed operational stage only: no error text, identifiers, request or evidence.
 const refuse=()=>{console.error('Oracle qualified read refused',channel,phase);return unavailableControl();};
 const refuseErr=(err:unknown)=>{console.error('Oracle qualified read refused',channel,phase,'err',err instanceof Error?err.message:typeof err);return unavailableControl();};
 const wall=Date.now(),mono=performance.now(),window:Window={wall,mono,end:wall+30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
 try{
  const proxy=readControlWindow(request.headers);window.end=Math.min(window.end,proxy.wall_end);window.proxyMonoEnd=BigInt(proxy.mono_end);
  phase='installed-binding';const installed=await installedForEmployeeV1(channel==='web'?'answer':'mcp-answer',window) as InstalledBinding<import('./replacement-server-binding').ConnectedAnswerBinding>,p=installed.profile;window.end=Math.min(window.end,instant(p.expires_at),instant(p.original_horizon));
  phase='origin';origin(request,p);phase='employee';await identity(p,window);phase='current-binding';current(installed,window);
  phase='request-body';const body=supplied===undefined?await readBody(request,window):Buffer.from(canonicalJson(supplied.kind==='legacy'
   ?{schema_version:1,caller_deadline:canonicalInstantV1(Math.floor(window.end)),query:validateConnectedAnswerQuery(supplied.query)}
   :validateNaturalQuestionV1({schema_version:1,protocol:'qualified-natural-question-v1',caller_deadline:canonicalInstantV1(Math.floor(window.end)),question:supplied.question})));
  phase='request-schema';const wire=parseClosedJson(body,65536);
  if(!wire||typeof wire!=='object'||Array.isArray(wire)||canonicalJson(wire)!==body.toString('utf8'))return refuse();
  const industry=(wire as Record<string,unknown>).protocol==='qualified-industry-question-v1';
  const workspace=(wire as Record<string,unknown>).protocol==='qualified-workspace-question-v1';
  const natural=Object.hasOwn(wire,'protocol')&&!industry&&!workspace;let original:NaturalQuestionV1|undefined;let research:IndustryQuestionV1|undefined;let overview:WorkspaceQuestionV1|undefined;let q:Readonly<Record<string,unknown>>|undefined;
  if(workspace)overview=validateWorkspaceQuestionV1(wire);
  else if(industry)research=validateIndustryQuestionV1(wire);
  else if(natural)original=validateNaturalQuestionV1(wire);
  else{if(!exact(wire,['schema_version','caller_deadline','query'])||wire.schema_version!==1)return refuse();q=validateConnectedAnswerQuery(wire.query);}
  const expectedQuerySHA=overview?workspaceQuerySHA256V1(overview):research?industryQuerySHA256V1(research):original?naturalQuerySHA256V1(original):sha256(Buffer.from(canonicalJson(q)));
  const deadline=instant(overview?overview.caller_deadline:research?research.caller_deadline:original?original.caller_deadline:(wire as Record<string,unknown>).caller_deadline);if(deadline<=Date.now()||deadline>window.end)return refuse();window.end=Math.min(window.end,deadline);
  current(installed,window);await identity(p,window);current(installed,window);
  phase='protected-transport';const value=await transport(installed,body,window);
  phase='response-binding';if(!('protocol'in value)||!(value.protocol==='qualified-connected-answer-v1'||value.protocol==='qualified-natural-answer-v1'||value.protocol==='qualified-industry-answer-v1'||value.protocol==='qualified-workspace-answer-v1')||value.channel!==channel||value.principal_id!==p.principal_id||value.workspace_id!==p.workspace_id||value.model_id!==p.model_id||value.query_sha256!==expectedQuerySHA)return refuse();
  if(workspace){if(value.protocol!=='qualified-workspace-answer-v1'||!overview||value.operation!==overview.operation||value.process_id!==overview.process_id||value.page!==overview.page||value.request_sha256!==sha256(body))return refuse();}
  else if(industry){if(value.protocol!=='qualified-industry-answer-v1'||!research||value.operation!==research.operation||value.decision_id!==research.decision_id||value.request_sha256!==sha256(body))return refuse();}
  else if(natural){if(value.protocol!=='qualified-natural-answer-v1'||value.request_sha256!==sha256(body))return refuse();}
  else if(value.protocol!=='qualified-connected-answer-v1'||!q||value.answer.mode!==q.mode||(q.expected_version!==null&&value.answer.model_version!==q.expected_version))return refuse();
  phase='response-deadline';const end=instant(value.expires_at);if(end<=Date.now()||end>window.end||instant(value.checked_at)>Date.now())return refuse();window.end=Math.min(window.end,end);
  phase='final-current-employee';current(installed,window);await identity(p,window);current(installed,window);remaining(window);
  return new Response(canonicalJson(value),{status:200,headers:{...privateControlHeaders,'Content-Type':'application/json'}});
 }catch(err){return refuseErr(err);}
}
export async function requestConnectedAnswer(request:Request):Promise<Response>{return connectedAnswer(request,'web');}
export async function requestEmployeeMcpAnswer(request:Request,query:unknown):Promise<Response>{return connectedAnswer(request,'mcp',{kind:'legacy',query});}
export async function requestEmployeeMcpQuestion(request:Request,question:string):Promise<Response>{return connectedAnswer(request,'mcp',{kind:'natural',question});}
