import {canonicalJson} from './protected-canonical-json';
import {verifyReplacementRecallRequestV1} from './recall-webhook-verifier';
/** Node-only consumer of an independently installed appointment. Never issues one.
 * No framework `server-only` marker is installed; Node imports and runtime refusal
 * prevent browser use. Framework target verification remains a separate gate.
 */
import {isAbsolute,resolve} from 'node:path';
import { createPrivateKey, createPublicKey, X509Certificate } from 'node:crypto';

if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
const unavailable = (): never => { throw new Error('Replacement control unavailable'); };
import {protectedRead,sha256,type PinnedFile} from './_protected-file';
export {sha256} from './_protected-file';
const hash = /^[0-9a-f]{64}$/;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const exact = (v: unknown, fields: readonly string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k));
const text = (v: unknown, limit = 2048): v is string => typeof v === 'string' && v.length > 0 && v.length <= limit && v.trim() === v && !/[\u0000-\u001f\u007f]/.test(v);

/** Closed JSON parser. Duplicate names, invalid UTF-8, nonfinite numbers and
 * unpaired surrogates refuse before any DTO is used. ASCII wire field names
 * make canonical ordering identical to the Python requester's JSON encoding.
 */
export function parseClosedJson(bytes: Uint8Array, limit: number): unknown {
  if (bytes.length < 1 || bytes.length > limit) return unavailable();
  const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  let i = 0;
  const ws = () => { while (/[\x20\t\r\n]/.test(raw[i] ?? '') && i < raw.length) i++; };
  const string = (): string => {
    const start = i++;
    while (i < raw.length) {
      const c = raw[i++];
      if (c === '\\') { i++; continue; }
      if (c === '"') {
        const value: unknown = JSON.parse(raw.slice(start, i));
        if (typeof value !== 'string' || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) return unavailable();
        return value;
      }
    }
    return unavailable();
  };
  const value = (depth: number): unknown => {
    if (depth > 10) return unavailable();
    ws(); const c = raw[i];
    if (c === '"') return string();
    if (c === '{') {
      i++; ws(); const result: Record<string, unknown> = Object.create(null);
      if (raw[i] === '}') { i++; return result; }
      for (;;) {
        ws(); if (raw[i] !== '"') return unavailable();
        const key = string(); if (Object.hasOwn(result, key)) return unavailable();
        ws(); if (raw[i++] !== ':') return unavailable();
        result[key] = value(depth + 1); ws();
        const end = raw[i++]; if (end === '}') return result;
        if (end !== ',') return unavailable();
      }
    }
    if (c === '[') {
      i++; ws(); const result: unknown[] = [];
      if (raw[i] === ']') { i++; return result; }
      for (;;) {
        if (result.length >= 1000) return unavailable();
        result.push(value(depth + 1)); ws();
        const end = raw[i++]; if (end === ']') return result;
        if (end !== ',') return unavailable();
      }
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(raw.slice(i))?.[0];
    if (!token) return unavailable();
    i += token.length; const out: unknown = JSON.parse(token);
    if (typeof out === 'number' && (!Number.isSafeInteger(out) || Object.is(out, -0))) return unavailable();
    return out;
  };
  const out = value(0); ws(); if (i !== raw.length) return unavailable();
  return out;
}
export { canonicalJson } from './protected-canonical-json';
export const canonicalUuid = (v: unknown): v is string => typeof v === 'string' && uuid.test(v);
export const canonicalHash = (v: unknown): v is string => typeof v === 'string' && hash.test(v);
export function instant(v: unknown): number {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(v)) return unavailable();
  const ms = Date.parse(v); if (!Number.isFinite(ms)) return unavailable();
  // Date.parse normalizes nonexistent dates. Reject these before accepting a window.
  const date = v.slice(0, 10), day = Number(date.slice(8)), month = Number(date.slice(5, 7)), year = Number(date.slice(0, 4));
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate() || Number(v.slice(11, 13)) > 23 || Number(v.slice(14, 16)) > 59 || Number(v.slice(17, 19)) > 59) return unavailable();
  const fraction = /\.(\d+)/.exec(v)?.[1] ?? '';
  return ms + Number(fraction.padEnd(6, '0').slice(3, 6)) / 1000;
}

export interface ServerBinding {
  readonly schema_version: 1;
  readonly purpose: 'replacement-web-binding-v1';
  readonly project_url: string; readonly auth_issuer: string;
  readonly auth_user_id: string; readonly employee_id: string;
  readonly principal_id: string; readonly workspace_id: string;
  readonly runtime_hash: string; readonly registry_hash: string;
  readonly intake_appointment_sha256: string; readonly peer_profile_sha256: string;
  readonly web_origin: string; readonly backend_origin: string;
  readonly control_path: '/v1/replacement/control'; readonly server_dns: string;
  readonly server_certificate_der_sha256: string;
  readonly server_ca_file: string; readonly server_ca_sha256: string;
  readonly client_certificate_file: string; readonly client_certificate_sha256: string;
  readonly client_certificate_der_sha256: string; readonly client_uri: string;
  readonly client_key_file: string; readonly client_key_sha256: string;
  readonly issuer_actor: string; readonly reviewer_actor: string;
  readonly valid_from: string; readonly expires_at: string; readonly original_horizon: string;
}
const fields = ['schema_version','purpose','project_url','auth_issuer','auth_user_id','employee_id','principal_id','workspace_id','runtime_hash','registry_hash','intake_appointment_sha256','peer_profile_sha256','web_origin','backend_origin','control_path','server_dns','server_certificate_der_sha256','server_ca_file','server_ca_sha256','client_certificate_file','client_certificate_sha256','client_certificate_der_sha256','client_uri','client_key_file','client_key_sha256','issuer_actor','reviewer_actor','valid_from','expires_at','original_horizon'] as const;
const httpsOrigin = (v: unknown): v is string => {
  if (!text(v)) return false;
  try { const u = new URL(v); return u.protocol === 'https:' && !u.username && !u.password && u.origin === v; } catch { return false; }
};
/** Descriptive validation alone is never installation, admission or permission. */
export function validateBinding(v: unknown): Readonly<ServerBinding> {
  if (!exact(v, fields) || v.schema_version !== 1 || v.purpose !== 'replacement-web-binding-v1') return unavailable();
  validateCommonBinding(v);
  if (!canonicalHash(v.intake_appointment_sha256) || !canonicalHash(v.peer_profile_sha256) || v.control_path !== '/v1/replacement/control') return unavailable();
  return Object.freeze(v) as unknown as Readonly<ServerBinding>;
}

function validateCommonBinding(v: Record<string,unknown>):void {
  for (const k of (['replacement-meeting-ingress-web-binding-v1','replacement-meeting-worker-binding-v1'].includes(String(v.purpose))?['principal_id','workspace_id']:['auth_user_id','employee_id','principal_id','workspace_id'])) if (!canonicalUuid(v[k])) return unavailable();
  for (const k of ['runtime_hash','registry_hash','server_certificate_der_sha256','server_ca_sha256','client_certificate_sha256','client_certificate_der_sha256','client_key_sha256'] as const) if (!canonicalHash(v[k])) return unavailable();
  if (!httpsOrigin(v.backend_origin)||(!['replacement-meeting-ingress-web-binding-v1','replacement-meeting-worker-binding-v1'].includes(String(v.purpose))&&(!httpsOrigin(v.project_url)||v.auth_issuer!==v.project_url+'/auth/v1'||!httpsOrigin(v.web_origin)))) return unavailable();
  if (!text(v.server_dns, 253) || !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(v.server_dns) || new URL(v.backend_origin).hostname !== v.server_dns || !v.server_dns.includes('.') || v.server_dns.includes('..')) return unavailable();
  if (!text(v.client_uri, 256) || !/^spiffe:\/\/oracle\/[a-zA-Z0-9/_-]+$/.test(v.client_uri)) return unavailable();
  for (const k of ['server_ca_file','client_certificate_file','client_key_file'] as const) if (!text(v[k]) || !isAbsolute(v[k]) || resolve(v[k]) !== v[k]) return unavailable();
  if (v.server_ca_file === v.client_key_file || v.server_ca_file === v.client_certificate_file || v.client_key_file === v.client_certificate_file) return unavailable();
  if (!text(v.issuer_actor, 160) || !text(v.reviewer_actor, 160) || v.issuer_actor === v.reviewer_actor || v.issuer_actor === v.principal_id || v.reviewer_actor === v.principal_id) return unavailable();
  const from = instant(v.valid_from), expires = instant(v.expires_at), horizon = instant(v.original_horizon);
  if (!(from < expires && expires <= horizon)) return unavailable();
}
export const MAX_ORIGINAL_BYTES=25*1024*1024;
export interface ViewerSourcePin { readonly schema_version:1; readonly source_id:string; readonly revision:number; readonly original_sha256:string; readonly byte_count:number; readonly media_type:'application/pdf'|'text/plain'; readonly reservation_id:string; readonly custody_seal_sha256:string; }
export interface ViewerBinding extends Omit<ServerBinding,'purpose'|'intake_appointment_sha256'|'peer_profile_sha256'|'control_path'> {
  readonly purpose:'replacement-original-web-binding-v1'; readonly original_path:'/v1/replacement/original';
  readonly viewer_config_sha256:string; readonly viewer_appointment_sha256:string; readonly viewer_peer_profile_sha256:string; readonly storage_profile_hash:string;
  readonly sources:readonly Readonly<ViewerSourcePin>[];
}
export function validateViewerBinding(value:unknown):Readonly<ViewerBinding> {
  const keys=[...fields.filter(k=>!['purpose','intake_appointment_sha256','peer_profile_sha256','control_path'].includes(k)),'purpose','original_path','viewer_config_sha256','viewer_appointment_sha256','viewer_peer_profile_sha256','storage_profile_hash','sources'];
  if(!exact(value,keys)||value.schema_version!==1||value.purpose!=='replacement-original-web-binding-v1'||value.original_path!=='/v1/replacement/original')return unavailable();
  validateCommonBinding(value);
  for(const k of ['viewer_config_sha256','viewer_appointment_sha256','viewer_peer_profile_sha256','storage_profile_hash'])if(!canonicalHash(value[k]))return unavailable();
  if(!Array.isArray(value.sources)||value.sources.length<1||value.sources.length>64)return unavailable();
  const seen=new Set<string>();
  for(const pin of value.sources){
    if(!exact(pin,['schema_version','source_id','revision','original_sha256','byte_count','media_type','reservation_id','custody_seal_sha256'])||pin.schema_version!==1||!canonicalUuid(pin.source_id)||typeof pin.revision!=='number'||!Number.isSafeInteger(pin.revision)||pin.revision<1||!canonicalHash(pin.original_sha256)||typeof pin.byte_count!=='number'||!Number.isSafeInteger(pin.byte_count)||pin.byte_count<1||pin.byte_count>MAX_ORIGINAL_BYTES||(pin.media_type!=='application/pdf'&&pin.media_type!=='text/plain')||!canonicalUuid(pin.reservation_id)||!canonicalHash(pin.custody_seal_sha256))return unavailable();
    const key=pin.source_id+':'+pin.revision;if(seen.has(key))return unavailable();seen.add(key);Object.freeze(pin);
  }
  Object.freeze(value.sources);return Object.freeze(value) as unknown as Readonly<ViewerBinding>;
}
export interface ModelReviewBinding extends Omit<ServerBinding,'purpose'|'intake_appointment_sha256'|'peer_profile_sha256'|'control_path'> {
  readonly purpose:'replacement-model-review-web-binding-v1';readonly review_path:'/v1/replacement/model-review';
  readonly model_id:string;readonly review_config_sha256:string;readonly review_peer_profile_sha256:string;
}
export function validateModelReviewBinding(value:unknown):Readonly<ModelReviewBinding>{
  const keys=[...fields.filter(k=>!['purpose','intake_appointment_sha256','peer_profile_sha256','control_path'].includes(k)),'purpose','review_path','model_id','review_config_sha256','review_peer_profile_sha256'];
  if(!exact(value,keys)||value.schema_version!==1||value.purpose!=='replacement-model-review-web-binding-v1'||value.review_path!=='/v1/replacement/model-review'||!canonicalUuid(value.model_id)||!canonicalHash(value.review_config_sha256)||!canonicalHash(value.review_peer_profile_sha256))return unavailable();
  validateCommonBinding(value);return Object.freeze(value) as unknown as Readonly<ModelReviewBinding>;
}
export interface UploadBinding extends Omit<ServerBinding,'purpose'|'peer_profile_sha256'|'control_path'> {
  readonly purpose:'replacement-upload-web-binding-v1';readonly upload_path:'/v1/replacement/upload/chunks';
  readonly intake_config_sha256:string;readonly upload_peer_profile_sha256:string;readonly upload_spool_initialization_sha256:string;readonly storage_profile_hash:string;
}
export function validateUploadBinding(value:unknown):Readonly<UploadBinding>{
 const keys=[...fields.filter(k=>!['purpose','peer_profile_sha256','control_path'].includes(k)),'purpose','upload_path','intake_config_sha256','upload_peer_profile_sha256','upload_spool_initialization_sha256','storage_profile_hash'];
 if(!exact(value,keys)||value.schema_version!==1||value.purpose!=='replacement-upload-web-binding-v1'||value.upload_path!=='/v1/replacement/upload/chunks')return unavailable();
 validateCommonBinding(value);
 for(const k of ['intake_config_sha256','intake_appointment_sha256','upload_peer_profile_sha256','upload_spool_initialization_sha256','storage_profile_hash'])if(!canonicalHash(value[k]))return unavailable();
 return Object.freeze(value) as unknown as Readonly<UploadBinding>;
}
export interface MeetingControlBinding extends Omit<ServerBinding,'purpose'|'control_path'|'intake_appointment_sha256'|'peer_profile_sha256'> {
 readonly purpose:'replacement-meeting-control-web-binding-v1';readonly meeting_path:'/v1/replacement/meetings/control';
 readonly meeting_id:string;readonly meeting_config_sha256:string;readonly meeting_peer_profile_sha256:string;
}
export interface MeetingIngressBinding extends Omit<ServerBinding,'purpose'|'control_path'|'intake_appointment_sha256'|'peer_profile_sha256'|'project_url'|'auth_issuer'|'auth_user_id'|'employee_id'|'web_origin'> {
 readonly purpose:'replacement-meeting-ingress-web-binding-v1';readonly ingress_path:'/v1/replacement/meetings/ingress';
 readonly meeting_id:string;readonly meeting_config_sha256:string;readonly meeting_peer_profile_sha256:string;
 readonly provider_account:string;readonly verifier_secret_file:string;readonly verifier_secret_sha256:string;
}
export function validateMeetingBinding(value:unknown,service:false):Readonly<MeetingControlBinding>;
export function validateMeetingBinding(value:unknown,service:true):Readonly<MeetingIngressBinding>;
export function validateMeetingBinding(value:unknown,service:boolean):Readonly<MeetingControlBinding|MeetingIngressBinding>{
 const removed=['purpose','control_path','intake_appointment_sha256','peer_profile_sha256',...(service?['project_url','auth_issuer','auth_user_id','employee_id','web_origin']:[])];
 const keys=[...fields.filter(k=>!removed.includes(k)),'purpose',service?'ingress_path':'meeting_path','meeting_id','meeting_config_sha256','meeting_peer_profile_sha256',...(service?['provider_account','verifier_secret_file','verifier_secret_sha256']:[])];
 if(!exact(value,keys)||value.schema_version!==1||value.purpose!==(service?'replacement-meeting-ingress-web-binding-v1':'replacement-meeting-control-web-binding-v1')||value[service?'ingress_path':'meeting_path']!==(service?'/v1/replacement/meetings/ingress':'/v1/replacement/meetings/control'))return unavailable();
 validateCommonBinding(value);
 if(!canonicalUuid(value.meeting_id)||!canonicalHash(value.meeting_config_sha256)||!canonicalHash(value.meeting_peer_profile_sha256))return unavailable();
 if(service&&(!text(value.provider_account,256)||!text(value.verifier_secret_file)||!isAbsolute(value.verifier_secret_file)||resolve(value.verifier_secret_file)!==value.verifier_secret_file||!canonicalHash(value.verifier_secret_sha256)))return unavailable();
 return Object.freeze(value) as unknown as Readonly<MeetingControlBinding|MeetingIngressBinding>;
}
export interface ConversationBinding extends Omit<ServerBinding,'purpose'|'intake_appointment_sha256'|'peer_profile_sha256'|'control_path'> {
 readonly purpose:'employee-conversation-web-binding-v1';readonly conversation_path:'/v1/employee/conversation';
 readonly conversation_config_sha256:string;readonly conversation_appointment_sha256:string;readonly conversation_peer_profile_sha256:string;
}
export function validateConversationBinding(v:unknown):Readonly<ConversationBinding>{
 const keys=[...fields.filter(k=>!['purpose','intake_appointment_sha256','peer_profile_sha256','control_path'].includes(k)),'purpose','conversation_path','conversation_config_sha256','conversation_appointment_sha256','conversation_peer_profile_sha256'];
 if(!exact(v,keys)||v.schema_version!==1||v.purpose!=='employee-conversation-web-binding-v1'||v.conversation_path!=='/v1/employee/conversation')return unavailable();
 validateCommonBinding(v);for(const k of ['conversation_config_sha256','conversation_appointment_sha256','conversation_peer_profile_sha256'])if(!canonicalHash(v[k]))return unavailable();
 return Object.freeze(v) as unknown as Readonly<ConversationBinding>;
}
export type MeetingWorkerPurposeV1='capture-create'|'capture-leave'|'capture-retrieve'|'participation-send';
export interface MeetingWorkerBinding extends Omit<ServerBinding,'purpose'|'control_path'|'intake_appointment_sha256'|'peer_profile_sha256'|'project_url'|'auth_issuer'|'auth_user_id'|'employee_id'|'web_origin'> {
 readonly purpose:'replacement-meeting-worker-binding-v1';readonly worker_path:'/v1/replacement/meetings/worker';
 readonly worker_id:string;readonly meeting_id:string;readonly effect_purpose:MeetingWorkerPurposeV1;
 readonly worker_config_sha256:string;readonly worker_peer_profile_sha256:string;readonly worker_admission_sha256:string;
 readonly provider_account:string;readonly provider_region:string;readonly provider_ca_file:string;readonly provider_ca_sha256:string;
 readonly provider_server_der_sha256:string;readonly provider_key_file:string;readonly provider_key_sha256:string;
 readonly operation_policy_sha256:string;readonly composer_program_sha256:string|null;
 readonly create_operation_id:string|null;readonly create_request_sha256:string|null;readonly stop_mapping_sha256:string|null;
 readonly retrieve_stage?:'pre-stop-consistency'|'post-stop-terminal';readonly retrieve_operation_id?:string;
 readonly capture_until:string;readonly stop_until:string;
 readonly receipt_root:string;readonly receipt_device:number;readonly receipt_inode:number;readonly receipt_uid:number;
 readonly receipt_initialization_file:string;readonly receipt_initialization_sha256:string;
}
const workerExtra=['worker_path','worker_id','meeting_id','effect_purpose','worker_config_sha256','worker_peer_profile_sha256','worker_admission_sha256','provider_account','provider_region','provider_ca_file','provider_ca_sha256','provider_server_der_sha256','provider_key_file','provider_key_sha256','operation_policy_sha256','composer_program_sha256','create_operation_id','create_request_sha256','stop_mapping_sha256','capture_until','stop_until','receipt_root','receipt_device','receipt_inode','receipt_uid','receipt_initialization_file','receipt_initialization_sha256'] as const;
export function validateMeetingWorkerBinding(value:unknown):Readonly<MeetingWorkerBinding>{
 const removed=['purpose','control_path','intake_appointment_sha256','peer_profile_sha256','project_url','auth_issuer','auth_user_id','employee_id','web_origin'];
 const keys=[...fields.filter(k=>!removed.includes(k)),'purpose',...workerExtra];
 if(value&&typeof value==='object'&&(Object.hasOwn(value,'retrieve_stage')||Object.hasOwn(value,'retrieve_operation_id')))keys.push('retrieve_stage','retrieve_operation_id');
 if(!exact(value,keys)||value.schema_version!==1||value.purpose!=='replacement-meeting-worker-binding-v1'||value.worker_path!=='/v1/replacement/meetings/worker')return unavailable();
 validateCommonBinding(value);
 if(Object.hasOwn(value,'retrieve_stage')&&(value.effect_purpose!=='capture-retrieve'||!['pre-stop-consistency','post-stop-terminal'].includes(String(value.retrieve_stage))||!canonicalUuid(value.retrieve_operation_id)))return unavailable();
 for(const k of ['worker_id','meeting_id'])if(!canonicalUuid(value[k]))return unavailable();
 if(typeof value.effect_purpose!=='string'||!['capture-create','capture-leave','capture-retrieve','participation-send'].includes(value.effect_purpose)||!text(value.provider_account,256)||!['us-west-2','us-east-1','eu-central-1','ap-northeast-1'].includes(String(value.provider_region)))return unavailable();
 if(typeof value.provider_region!=='string')return unavailable();
 for(const k of ['worker_config_sha256','worker_peer_profile_sha256','worker_admission_sha256','provider_ca_sha256','provider_server_der_sha256','provider_key_sha256','operation_policy_sha256','receipt_initialization_sha256'])if(!canonicalHash(value[k]))return unavailable();
 for(const k of ['provider_ca_file','provider_key_file','receipt_root','receipt_initialization_file'])if(!text(value[k])||!isAbsolute(value[k])||resolve(value[k])!==value[k])return unavailable();
 for(const k of ['receipt_device','receipt_inode','receipt_uid'])if(typeof value[k]!=='number'||!Number.isSafeInteger(value[k])||(value[k] as number)<(k==='receipt_inode'?1:0))return unavailable();
 if(value.provider_key_file===value.client_key_file||value.provider_ca_file===value.provider_key_file)return unavailable();
 if(value.effect_purpose==='capture-create'){
  if(!canonicalUuid(value.create_operation_id)||!canonicalHash(value.create_request_sha256)||value.composer_program_sha256!==null)return unavailable();
 }else if(value.create_operation_id!==null||value.create_request_sha256!==null)return unavailable();
 if(value.effect_purpose==='participation-send'){
  if(!canonicalHash(value.composer_program_sha256)||value.stop_mapping_sha256!==null)return unavailable();
 }else if(value.composer_program_sha256!==null)return unavailable();
 if(['capture-leave','capture-retrieve'].includes(value.effect_purpose)){
  if(!canonicalHash(value.stop_mapping_sha256))return unavailable();
 }else if(value.stop_mapping_sha256!==null)return unavailable();
 const capture=instant(value.capture_until),stop=instant(value.stop_until),expires=instant(value.expires_at),horizon=instant(value.original_horizon);
 if(capture>stop||stop>horizon||expires>(['capture-create','participation-send'].includes(value.effect_purpose)?capture:stop))return unavailable();
 return Object.freeze(value) as unknown as Readonly<MeetingWorkerBinding>;
}
export interface ConnectedAnswerBinding extends Omit<ServerBinding,'purpose'|'intake_appointment_sha256'|'peer_profile_sha256'|'control_path'> {
 readonly purpose:'qualified-connected-answer-web-binding-v1'|'qualified-connected-answer-mcp-binding-v1';
 readonly answer_path:'/v1/employee/answer'|'/v1/employee/mcp-answer';readonly answer_config_sha256:string;readonly answer_peer_sha256:string;readonly model_id:string;
}
export function validateConnectedAnswerBinding(v:unknown,channel:'web'|'mcp'):Readonly<ConnectedAnswerBinding>{
 const keys=[...fields.filter(k=>!['purpose','intake_appointment_sha256','peer_profile_sha256','control_path'].includes(k)),'purpose','answer_path','answer_config_sha256','answer_peer_sha256','model_id'];
 if(!exact(v,keys)||v.schema_version!==1||v.purpose!==(channel==='web'?'qualified-connected-answer-web-binding-v1':'qualified-connected-answer-mcp-binding-v1')||v.answer_path!==(channel==='web'?'/v1/employee/answer':'/v1/employee/mcp-answer')||!canonicalHash(v.answer_config_sha256)||!canonicalHash(v.answer_peer_sha256)||!canonicalUuid(v.model_id))return unavailable();
 validateCommonBinding(v);return Object.freeze(v) as unknown as Readonly<ConnectedAnswerBinding>;
}
export type ProtectedBinding=ServerBinding|ViewerBinding|UploadBinding|ModelReviewBinding|ConversationBinding|MeetingControlBinding|MeetingIngressBinding|MeetingWorkerBinding|ConnectedAnswerBinding;

export interface IdentitySnapshot { readonly configuredProjectUrl: string; readonly actualProjectUrl: string; readonly verifiedUserId: string; readonly employeeId: string; readonly disabledAt: unknown; }
/** Pure descriptive unit helper; production cannot inject this snapshot. */
export function matchesIdentity(binding: Readonly<Pick<ServerBinding,'project_url'|'auth_issuer'|'auth_user_id'|'employee_id'>>, snapshot: IdentitySnapshot): boolean {
  return snapshot.configuredProjectUrl === binding.project_url && snapshot.actualProjectUrl === binding.project_url && binding.auth_issuer === snapshot.actualProjectUrl + '/auth/v1' && snapshot.verifiedUserId === binding.auth_user_id && snapshot.employeeId === binding.employee_id && snapshot.disabledAt === null;
}

interface BindingCache { readonly path: string; readonly digest: string; readonly identity: string; readonly profile: Readonly<ProtectedBinding>; readonly files: readonly PinnedFile[] }
let installed:BindingCache|undefined, viewerInstalled:BindingCache|undefined, reviewInstalled:BindingCache|undefined, uploadInstalled:BindingCache|undefined,conversationInstalled:BindingCache|undefined,meetingInstalled:BindingCache|undefined,meetingIngressInstalled:BindingCache|undefined,meetingWorkerInstalled:BindingCache|undefined,answerInstalled:BindingCache|undefined,mcpAnswerInstalled:BindingCache|undefined;
type FixedWorkerLoader='meeting-worker-create'|'meeting-worker-leave'|'meeting-worker-pre-stop-retrieve'|'meeting-worker-post-stop-retrieve'|'meeting-worker-participation';
const fixedWorkerCaches=new Map<FixedWorkerLoader,BindingCache>();
const workerOrigins=new WeakMap<object,'meeting-worker'|FixedWorkerLoader>();
const fixedWorkerConfiguration={
 'meeting-worker-create':['ORACLE2_MEETING_CREATE_WORKER_BINDING','capture-create',null],
 'meeting-worker-leave':['ORACLE2_MEETING_LEAVE_WORKER_BINDING','capture-leave',null],
 'meeting-worker-pre-stop-retrieve':['ORACLE2_MEETING_PRE_STOP_RETRIEVE_WORKER_BINDING','capture-retrieve','pre-stop-consistency'],
 'meeting-worker-post-stop-retrieve':['ORACLE2_MEETING_POST_STOP_RETRIEVE_WORKER_BINDING','capture-retrieve','post-stop-terminal'],
 'meeting-worker-participation':['ORACLE2_MEETING_PARTICIPATION_WORKER_BINDING','participation-send',null],
} as const;
export interface InstalledBinding<P extends ProtectedBinding=ServerBinding> { readonly profile: Readonly<P>; readonly ca: Buffer; readonly cert: Buffer; readonly key: Buffer; }
/** Configuration selectors are read only from server configuration, once per instance.
 * File identity changes refuse even when the replacement has identical bytes.
 * The appointment/peer hashes require independent backend installation; this
 * consumer cannot prove their relationship merely by reading a supplied hash.
 */
function loadInstalledBinding(purpose:'control'|'viewer'|'upload'|'review'|'conversation'|'meeting'|'meeting-ingress'|'meeting-worker'|'answer'|'mcp-answer'|FixedWorkerLoader): InstalledBinding<ProtectedBinding> {
  const fixedWorker=Object.hasOwn(fixedWorkerConfiguration,purpose)?purpose as FixedWorkerLoader:undefined;
  const fixed=fixedWorker?fixedWorkerConfiguration[fixedWorker]:undefined;
  const answer=purpose==='answer',mcpAnswer=purpose==='mcp-answer';
  const viewer=purpose==='viewer',upload=purpose==='upload',review=purpose==='review',conversation=purpose==='conversation';
  const meeting=purpose==='meeting',ingress=purpose==='meeting-ingress',worker=purpose==='meeting-worker'||fixedWorker!==undefined;
  const prior=fixedWorker?fixedWorkerCaches.get(fixedWorker):answer?answerInstalled:mcpAnswer?mcpAnswerInstalled:worker?meetingWorkerInstalled:ingress?meetingIngressInstalled:meeting?meetingInstalled:conversation?conversationInstalled:review?reviewInstalled:upload?uploadInstalled:viewer?viewerInstalled:installed;
  const path = fixed?process.env[fixed[0]+'_FILE']:answer?process.env.ORACLE2_CONNECTED_ANSWER_BINDING_FILE:mcpAnswer?process.env.ORACLE2_MCP_ANSWER_BINDING_FILE:worker?process.env.ORACLE2_MEETING_WORKER_BINDING_FILE:ingress?process.env.ORACLE2_MEETING_INGRESS_BINDING_FILE:meeting?process.env.ORACLE2_MEETING_CONTROL_BINDING_FILE:conversation?process.env.ORACLE2_CONVERSATION_BINDING_FILE:review?process.env.ORACLE2_REPLACEMENT_REVIEW_BINDING_FILE:upload?process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE:viewer?process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_FILE:process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE;
  const digest = fixed?process.env[fixed[0]+'_SHA256']:answer?process.env.ORACLE2_CONNECTED_ANSWER_BINDING_SHA256:mcpAnswer?process.env.ORACLE2_MCP_ANSWER_BINDING_SHA256:worker?process.env.ORACLE2_MEETING_WORKER_BINDING_SHA256:ingress?process.env.ORACLE2_MEETING_INGRESS_BINDING_SHA256:meeting?process.env.ORACLE2_MEETING_CONTROL_BINDING_SHA256:conversation?process.env.ORACLE2_CONVERSATION_BINDING_SHA256:review?process.env.ORACLE2_REPLACEMENT_REVIEW_BINDING_SHA256:upload?process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_SHA256:viewer?process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_SHA256:process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256;
  if (!path || !digest || (prior && (path !== prior.path || digest !== prior.digest))) return unavailable();
  const pinned = protectedRead(path, digest);
  const profile = answer||mcpAnswer?validateConnectedAnswerBinding(parseClosedJson(pinned.bytes,16384),answer?'web':'mcp'):worker?validateMeetingWorkerBinding(parseClosedJson(pinned.bytes,65536)):ingress?validateMeetingBinding(parseClosedJson(pinned.bytes,16384),true):meeting?validateMeetingBinding(parseClosedJson(pinned.bytes,16384),false):conversation?validateConversationBinding(parseClosedJson(pinned.bytes,16384)):review?validateModelReviewBinding(parseClosedJson(pinned.bytes,16384)):upload?validateUploadBinding(parseClosedJson(pinned.bytes,16384)):viewer?validateViewerBinding(parseClosedJson(pinned.bytes,65536)):validateBinding(parseClosedJson(pinned.bytes,16384));
  if(fixed&&(profile.purpose!=='replacement-meeting-worker-binding-v1'||profile.effect_purpose!==fixed[1]||(profile.retrieve_stage??null)!==fixed[2]))return unavailable();
  const now = Date.now();
  if (now < instant(profile.valid_from) || now >= instant(profile.expires_at) || now >= instant(profile.original_horizon)) return unavailable();
  const files = [protectedRead(profile.server_ca_file,profile.server_ca_sha256),protectedRead(profile.client_certificate_file,profile.client_certificate_sha256),protectedRead(profile.client_key_file,profile.client_key_sha256)];
  if(profile.purpose==='replacement-meeting-worker-binding-v1')files.push(protectedRead(profile.provider_ca_file,profile.provider_ca_sha256),protectedRead(profile.provider_key_file,profile.provider_key_sha256),protectedRead(profile.receipt_initialization_file,profile.receipt_initialization_sha256));
  if(profile.purpose==='replacement-meeting-ingress-web-binding-v1')files.push(protectedRead(profile.verifier_secret_file,profile.verifier_secret_sha256));
  if (prior && (prior.identity !== pinned.identity || files.some((f,i) => f.identity !== prior.files[i]!.identity || f.path !== prior.files[i]!.path || f.digest !== prior.files[i]!.digest))) return unavailable();
  const cert = new X509Certificate(files[1]!.bytes);
  if (sha256(cert.raw) !== profile.client_certificate_der_sha256 || !cert.subjectAltName?.split(', ').includes('URI:' + profile.client_uri) || now < Date.parse(cert.validFrom) || now >= Date.parse(cert.validTo)) return unavailable();
  const others=[installed,viewerInstalled,reviewInstalled,uploadInstalled,conversationInstalled,meetingInstalled,meetingIngressInstalled,meetingWorkerInstalled,answerInstalled,mcpAnswerInstalled,...fixedWorkerCaches.values()].filter(other=>other&&other!==prior);
  if(others.some(other=>other&&(profile.client_certificate_der_sha256===other.profile.client_certificate_der_sha256||profile.client_uri===other.profile.client_uri||cert.publicKey.equals(new X509Certificate(other.files[1]!.bytes).publicKey))))return unavailable();
  const key = createPrivateKey(files[2]!.bytes);
  if (!cert.checkPrivateKey(key) || !createPublicKey(key).equals(cert.publicKey)) return unavailable();
  const cache=prior??{path,digest,identity:pinned.identity,profile,files};
  if(fixedWorker)fixedWorkerCaches.set(fixedWorker,cache);else if(answer)answerInstalled=cache;else if(mcpAnswer)mcpAnswerInstalled=cache;else if(worker)meetingWorkerInstalled=cache;else if(ingress)meetingIngressInstalled=cache;else if(meeting)meetingInstalled=cache;else if(conversation)conversationInstalled=cache;else if(review)reviewInstalled=cache;else if(upload)uploadInstalled=cache;else if(viewer)viewerInstalled=cache;else installed=cache;
  const result={profile:cache.profile,ca:files[0]!.bytes,cert:files[1]!.bytes,key:files[2]!.bytes};
  if(worker)workerOrigins.set(result,fixedWorker??'meeting-worker');return result;
}

/** Fail closed without exposing protected paths or key/parser diagnostics. */
export function readInstalledBinding(): InstalledBinding {
  try { return loadInstalledBinding('control') as InstalledBinding; } catch { return unavailable(); }
}

/** Separate independently installed viewer consumer; never control fallback. */
export function readInstalledViewerBinding():InstalledBinding<ViewerBinding>{
  try{return loadInstalledBinding('viewer') as InstalledBinding<ViewerBinding>;}catch{return unavailable();}
}

export function readInstalledUploadBinding():InstalledBinding<UploadBinding>{
 try{return loadInstalledBinding('upload') as InstalledBinding<UploadBinding>;}catch{return unavailable();}
}

export function readInstalledMeetingBinding():InstalledBinding<MeetingControlBinding>{
 try{return loadInstalledBinding('meeting') as InstalledBinding<MeetingControlBinding>;}catch{return unavailable();}
}
export function readInstalledMeetingIngressBinding():InstalledBinding<MeetingIngressBinding>{
 try{return loadInstalledBinding('meeting-ingress') as InstalledBinding<MeetingIngressBinding>;}catch{return unavailable();}
}
// Fixed ingress entry only. Reuses the exact protected-file owner; never returns
// installed credentials to a browser or caller-selected service/auth adapter.
export function verifyInstalledMeetingIngress(bytes:Uint8Array,headers:Headers):void{
 const installed=readInstalledMeetingIngressBinding(),p=installed.profile;
 const file=protectedRead(p.verifier_secret_file,p.verifier_secret_sha256);
 const secret=new TextDecoder('utf-8',{fatal:true}).decode(file.bytes);
 verifyReplacementRecallRequestV1({secret,headers,payload:new TextDecoder('utf-8',{fatal:true}).decode(bytes)});
 if(canonicalJson(readInstalledMeetingIngressBinding().profile)!==canonicalJson(p))return unavailable();
}
/** Separate installed model-review purpose using the same actual identity owner. */
export function readInstalledModelReviewBinding():InstalledBinding<ModelReviewBinding>{
  try{return loadInstalledBinding('review') as InstalledBinding<ModelReviewBinding>;}catch{return unavailable();}
}

export function readInstalledConversationBinding():InstalledBinding<ConversationBinding>{
 try{return loadInstalledBinding('conversation') as InstalledBinding<ConversationBinding>;}catch{return unavailable();}
}

/** Fixed separate service consumer. No employee adapter or caller selector. */
export function readInstalledMeetingWorkerBinding():InstalledBinding<MeetingWorkerBinding>{
 try{return loadInstalledBinding('meeting-worker') as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}
}

export function readInstalledConnectedAnswerBinding():InstalledBinding<ConnectedAnswerBinding>{
 try{return loadInstalledBinding('answer') as InstalledBinding<ConnectedAnswerBinding>;}catch{return unavailable();}
}
export function readInstalledMcpAnswerBinding():InstalledBinding<ConnectedAnswerBinding>{
 try{return loadInstalledBinding('mcp-answer') as InstalledBinding<ConnectedAnswerBinding>;}catch{return unavailable();}
}

/** Closed source-selected consumers; no HTTP or caller-selected profile path. */
export function readInstalledMeetingCaptureCreateWorkerBinding():InstalledBinding<MeetingWorkerBinding>{try{return loadInstalledBinding('meeting-worker-create') as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}}
export function readInstalledMeetingCaptureLeaveWorkerBinding():InstalledBinding<MeetingWorkerBinding>{try{return loadInstalledBinding('meeting-worker-leave') as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}}
export function readInstalledMeetingCapturePreStopRetrieveWorkerBinding():InstalledBinding<MeetingWorkerBinding>{try{return loadInstalledBinding('meeting-worker-pre-stop-retrieve') as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}}
export function readInstalledMeetingCapturePostStopRetrieveWorkerBinding():InstalledBinding<MeetingWorkerBinding>{try{return loadInstalledBinding('meeting-worker-post-stop-retrieve') as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}}
export function readInstalledMeetingParticipationWorkerBinding():InstalledBinding<MeetingWorkerBinding>{try{return loadInstalledBinding('meeting-worker-participation') as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}}
/** Only actual objects made by this owner carry their private loader identity. */
export function rereadInstalledMeetingWorkerBinding(initial:InstalledBinding<MeetingWorkerBinding>):InstalledBinding<MeetingWorkerBinding>{const origin=workerOrigins.get(initial);if(!origin)return unavailable();try{return loadInstalledBinding(origin) as InstalledBinding<MeetingWorkerBinding>;}catch{return unavailable();}}
