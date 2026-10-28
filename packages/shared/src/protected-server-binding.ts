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
  for (const k of (['replacement-meeting-ingress-web-binding-v1','replacement-meeting-worker-binding-v1','meeting-normalization-worker-v1','meeting-supervision-service-binding-v1','meeting-ingress-queue-worker-v1'].includes(String(v.purpose))?['principal_id','workspace_id']:['auth_user_id','employee_id','principal_id','workspace_id'])) if (!canonicalUuid(v[k])) return unavailable();
  for (const k of ['runtime_hash','registry_hash','server_certificate_der_sha256','server_ca_sha256','client_certificate_sha256','client_certificate_der_sha256','client_key_sha256'] as const) if (!canonicalHash(v[k])) return unavailable();
  if (!httpsOrigin(v.backend_origin)||(!['replacement-meeting-ingress-web-binding-v1','replacement-meeting-worker-binding-v1','meeting-normalization-worker-v1','meeting-supervision-service-binding-v1','meeting-ingress-queue-worker-v1'].includes(String(v.purpose))&&(!httpsOrigin(v.project_url)||v.auth_issuer!==v.project_url+'/auth/v1'||!httpsOrigin(v.web_origin)))) return unavailable();
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
export interface RecommendationBindingV1 extends Omit<ServerBinding,'purpose'|'intake_appointment_sha256'|'peer_profile_sha256'|'control_path'> {
 readonly purpose:'replacement-recommendation-actions-web-binding-v1';readonly recommendation_path:'/v1/replacement/recommendation-actions';
 readonly model_id:string;readonly recommendation_config_sha256:string;readonly recommendation_peer_profile_sha256:string;
}
export function validateRecommendationBindingV1(value:unknown):Readonly<RecommendationBindingV1>{
 const keys=[...fields.filter(k=>!['purpose','intake_appointment_sha256','peer_profile_sha256','control_path'].includes(k)),'purpose','recommendation_path','model_id','recommendation_config_sha256','recommendation_peer_profile_sha256'];
 if(!exact(value,keys)||value.schema_version!==1||value.purpose!=='replacement-recommendation-actions-web-binding-v1'||value.recommendation_path!=='/v1/replacement/recommendation-actions'||!canonicalUuid(value.model_id)||!canonicalHash(value.recommendation_config_sha256)||!canonicalHash(value.recommendation_peer_profile_sha256))return unavailable();
 validateCommonBinding(value);return Object.freeze(value) as unknown as Readonly<RecommendationBindingV1>;
}
export function readInstalledRecommendationBindingV1():InstalledBinding<RecommendationBindingV1>{
 try{return loadInstalledBinding('recommendation-actions') as InstalledBinding<RecommendationBindingV1>;}catch{return unavailable();}
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
/** Separately appointed processing service, never employee/provider authority. */
export interface MeetingNormalizationBinding extends Omit<ServerBinding,'purpose'|'control_path'|'intake_appointment_sha256'|'peer_profile_sha256'|'project_url'|'auth_issuer'|'auth_user_id'|'employee_id'|'web_origin'> {
 readonly purpose:'meeting-normalization-worker-v1';readonly normalization_path:'/v1/replacement/meetings/normalize';
 readonly meeting_id:string;readonly normalization_config_sha256:string;readonly normalization_peer_profile_sha256:string;
 readonly normalization_admission_sha256:string;readonly original_processing_horizon:string;
}
export function validateMeetingNormalizationBinding(v:unknown):Readonly<MeetingNormalizationBinding>{
 const removed=['purpose','control_path','intake_appointment_sha256','peer_profile_sha256','project_url','auth_issuer','auth_user_id','employee_id','web_origin'];
 const keys=[...fields.filter(k=>!removed.includes(k)),'purpose','normalization_path','meeting_id','normalization_config_sha256','normalization_peer_profile_sha256','normalization_admission_sha256','original_processing_horizon'];
 if(!exact(v,keys)||v.schema_version!==1||v.purpose!=='meeting-normalization-worker-v1'||v.normalization_path!=='/v1/replacement/meetings/normalize'||!canonicalUuid(v.meeting_id))return unavailable();
 validateCommonBinding(v);
 for(const k of ['normalization_config_sha256','normalization_peer_profile_sha256','normalization_admission_sha256'])if(!canonicalHash(v[k]))return unavailable();
 const horizon=instant(v.original_processing_horizon);
 if(horizon>instant(v.original_horizon)||instant(v.expires_at)>horizon)return unavailable();
 return Object.freeze(v) as unknown as Readonly<MeetingNormalizationBinding>;
}
/** Independently installed queue scope; no employee/capture/provider grant. */
export interface MeetingQueueBinding extends Omit<MeetingNormalizationBinding,'purpose'|'normalization_path'|'normalization_config_sha256'|'normalization_peer_profile_sha256'|'normalization_admission_sha256'> {
 readonly purpose:'meeting-ingress-queue-worker-v1';readonly queue_path:'/v1/replacement/meetings/queue';
 readonly queue_config_sha256:string;readonly queue_peer_profile_sha256:string;readonly queue_admission_sha256:string;
 readonly worker_id:string;readonly queue_project_ref:string;readonly queue_environment_id:string;readonly queue_account_id:string;
 readonly queue_task_id:'oracle2-meeting-ingress-normalize-v1';readonly queue_credential_sha256:string;
 readonly queue_installation_receipt_file:string;readonly queue_installation_receipt_sha256:string;
 readonly queue_target_descriptor_file:string;readonly queue_target_descriptor_sha256:string;
 readonly queue_key_file:string;readonly queue_ca_file:string;readonly queue_ca_sha256:string;readonly queue_server_der_sha256:string;
 readonly receipt_root:string;readonly receipt_device:number;readonly receipt_inode:number;readonly receipt_uid:number;
 readonly receipt_initialization_file:string;readonly receipt_initialization_sha256:string;
}
export function validateMeetingQueueBinding(v:unknown):Readonly<MeetingQueueBinding>{
 const removed=['purpose','control_path','intake_appointment_sha256','peer_profile_sha256','project_url','auth_issuer','auth_user_id','employee_id','web_origin'];
 const extra=['purpose','queue_path','meeting_id','queue_config_sha256','queue_peer_profile_sha256','queue_admission_sha256','original_processing_horizon','worker_id','queue_project_ref','queue_environment_id','queue_account_id','queue_task_id','queue_credential_sha256','queue_installation_receipt_file','queue_installation_receipt_sha256','queue_target_descriptor_file','queue_target_descriptor_sha256','queue_key_file','queue_ca_file','queue_ca_sha256','queue_server_der_sha256','receipt_root','receipt_device','receipt_inode','receipt_uid','receipt_initialization_file','receipt_initialization_sha256'];
 if(!exact(v,[...fields.filter(k=>!removed.includes(k)),...extra])||v.schema_version!==1||v.purpose!=='meeting-ingress-queue-worker-v1'||v.queue_path!=='/v1/replacement/meetings/queue'||v.queue_task_id!=='oracle2-meeting-ingress-normalize-v1')return unavailable();
 validateCommonBinding(v);
 for(const k of ['meeting_id','worker_id','issuer_actor','reviewer_actor'])if(!canonicalUuid(v[k]))return unavailable();
 for(const k of ['queue_config_sha256','queue_peer_profile_sha256','queue_admission_sha256','queue_credential_sha256','queue_installation_receipt_sha256','queue_target_descriptor_sha256','queue_ca_sha256','queue_server_der_sha256','receipt_initialization_sha256'])if(!canonicalHash(v[k]))return unavailable();
 for(const k of ['queue_project_ref','queue_environment_id','queue_account_id'])if(!text(v[k],256)||v[k]!==v[k].trim()||/[^\x21-\x7e]/.test(v[k]))return unavailable();
 for(const k of ['queue_installation_receipt_file','queue_target_descriptor_file','queue_key_file','queue_ca_file','receipt_root','receipt_initialization_file'])if(!text(v[k])||!isAbsolute(v[k])||resolve(v[k])!==v[k])return unavailable();
 for(const k of ['receipt_device','receipt_inode','receipt_uid'])if(typeof v[k]!=='number'||!Number.isSafeInteger(v[k])||v[k]<0)return unavailable();
 if(new Set(['queue_key_file','queue_ca_file','queue_installation_receipt_file','queue_target_descriptor_file','receipt_initialization_file','client_key_file','client_certificate_file','server_ca_file'].map(k=>v[k])).size!==8)return unavailable();
 if(instant(v.original_processing_horizon)>instant(v.original_horizon)||instant(v.expires_at)>instant(v.original_processing_horizon))return unavailable();
 return Object.freeze(v) as unknown as Readonly<MeetingQueueBinding>;
}
export type MeetingSupervisionPurposeV1='meeting-scheduler-process-v1'|'meeting-stop-worker-process-v1';
export interface MeetingSupervisionBinding extends Omit<MeetingNormalizationBinding,'purpose'|'normalization_path'|'normalization_config_sha256'|'normalization_peer_profile_sha256'|'normalization_admission_sha256'|'original_processing_horizon'> {
 readonly purpose:'meeting-supervision-service-binding-v1';readonly supervision_path:'/v1/replacement/meetings/supervision';
 readonly process_purpose:MeetingSupervisionPurposeV1;readonly supervision_config_sha256:string;readonly supervision_peer_profile_sha256:string;
 readonly scope_sha256:string;readonly process_runtime_sha256:string;readonly process_config_sha256:string;
 readonly capture_until:string;readonly stop_until:string;
}
export function validateMeetingSupervisionBinding(v:unknown):Readonly<MeetingSupervisionBinding>{
 const removed=['purpose','control_path','intake_appointment_sha256','peer_profile_sha256','project_url','auth_issuer','auth_user_id','employee_id','web_origin'];
 const keys=[...fields.filter(k=>!removed.includes(k)),'purpose','supervision_path','meeting_id','process_purpose','supervision_config_sha256','supervision_peer_profile_sha256','scope_sha256','process_runtime_sha256','process_config_sha256','capture_until','stop_until'];
 if(!exact(v,keys)||v.schema_version!==1||v.purpose!=='meeting-supervision-service-binding-v1'||v.supervision_path!=='/v1/replacement/meetings/supervision'||!canonicalUuid(v.meeting_id)||typeof v.process_purpose!=='string'||!['meeting-scheduler-process-v1','meeting-stop-worker-process-v1'].includes(v.process_purpose))return unavailable();
 validateCommonBinding(v);
 for(const k of ['supervision_config_sha256','supervision_peer_profile_sha256','scope_sha256','process_runtime_sha256','process_config_sha256'])if(!canonicalHash(v[k]))return unavailable();
 const capture=instant(v.capture_until),stop=instant(v.stop_until);
 if(capture>stop||stop>instant(v.original_horizon)||instant(v.expires_at)>(v.process_purpose==='meeting-scheduler-process-v1'?capture:stop))return unavailable();
 return Object.freeze(v) as unknown as Readonly<MeetingSupervisionBinding>;
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
export type ProtectedBinding=RecommendationBindingV1|ServerBinding|ViewerBinding|UploadBinding|ModelReviewBinding|ConversationBinding|MeetingControlBinding|MeetingIngressBinding|MeetingWorkerBinding|MeetingNormalizationBinding|MeetingQueueBinding|MeetingSupervisionBinding|ConnectedAnswerBinding;

export interface IdentitySnapshot { readonly configuredProjectUrl: string; readonly actualProjectUrl: string; readonly verifiedUserId: string; readonly employeeId: string; readonly disabledAt: unknown; }
/** Pure descriptive unit helper; production cannot inject this snapshot. */
export function matchesIdentity(binding: Readonly<Pick<ServerBinding,'project_url'|'auth_issuer'|'auth_user_id'|'employee_id'>>, snapshot: IdentitySnapshot): boolean {
  return snapshot.configuredProjectUrl === binding.project_url && snapshot.actualProjectUrl === binding.project_url && binding.auth_issuer === snapshot.actualProjectUrl + '/auth/v1' && snapshot.verifiedUserId === binding.auth_user_id && snapshot.employeeId === binding.employee_id && snapshot.disabledAt === null;
}

/** Independently installed finite recipient index. It selects separate existing
 * profiles; it never issues a backend grant or accepts a request/cookie actor.
 * Production callers must obtain this snapshot from real getUser + employee SQL
 * and reverify that identity around the existing protected transport.
 */
export type EmployeeBindingPurposeV1='control'|'viewer'|'upload'|'review'|'conversation'|'meeting'|'answer'|'mcp-answer'|'recommendation';
interface EmployeeBindingsV1 {control:ServerBinding;viewer:ViewerBinding;upload:UploadBinding;review:ModelReviewBinding;conversation:ConversationBinding;meeting:MeetingControlBinding;answer:ConnectedAnswerBinding;'mcp-answer':ConnectedAnswerBinding;recommendation:RecommendationBindingV1;}
interface RecipientEntryV1 {readonly project_url:string;readonly auth_issuer:string;readonly auth_user_id:string;readonly employee_id:string;readonly bindings:Readonly<Partial<Record<EmployeeBindingPurposeV1,Readonly<{path:string;sha256:string}>>>>;}
interface RecipientIndexV1 {readonly schema_version:1;readonly purpose:'replacement-employee-recipient-index-v1';readonly issuer_actor:string;readonly reviewer_actor:string;readonly valid_from:string;readonly expires_at:string;readonly original_horizon:string;readonly recipients:readonly Readonly<RecipientEntryV1>[];}
const employeePurposesV1=['control','viewer','upload','review','conversation','meeting','answer','mcp-answer','recommendation'] as const;
export function validateEmployeeRecipientIndexV1(value:unknown):Readonly<RecipientIndexV1>{
 if(!exact(value,['schema_version','purpose','issuer_actor','reviewer_actor','valid_from','expires_at','original_horizon','recipients'])||value.schema_version!==1||value.purpose!=='replacement-employee-recipient-index-v1'||!canonicalUuid(value.issuer_actor)||!canonicalUuid(value.reviewer_actor)||value.issuer_actor===value.reviewer_actor||!Array.isArray(value.recipients)||value.recipients.length<1||value.recipients.length>64)return unavailable();
 if(!(instant(value.valid_from)<instant(value.expires_at)&&instant(value.expires_at)<=instant(value.original_horizon)))return unavailable();
 const identities=new Set<string>(),paths=new Set<string>();
 for(const entry of value.recipients){
  if(!exact(entry,['project_url','auth_issuer','auth_user_id','employee_id','bindings'])||!httpsOrigin(entry.project_url)||entry.auth_issuer!==entry.project_url+'/auth/v1'||!canonicalUuid(entry.auth_user_id)||!canonicalUuid(entry.employee_id)||!entry.bindings||typeof entry.bindings!=='object'||Array.isArray(entry.bindings))return unavailable();
  const key=canonicalJson([entry.project_url,entry.auth_issuer,entry.auth_user_id]);if(identities.has(key))return unavailable();identities.add(key);
  const purposes=Object.keys(entry.bindings);if(purposes.length<1||purposes.length>9)return unavailable();
  for(const kind of purposes){
   if(!employeePurposesV1.includes(kind as EmployeeBindingPurposeV1))return unavailable();const pin=(entry.bindings as Record<string,unknown>)[kind];
   if(!exact(pin,['path','sha256'])||!text(pin.path,2048)||!isAbsolute(pin.path)||resolve(pin.path)!==pin.path||!canonicalHash(pin.sha256)||paths.has(pin.path))return unavailable();paths.add(pin.path);Object.freeze(pin);
  }
  Object.freeze(entry.bindings);Object.freeze(entry);
 }
 Object.freeze(value.recipients);return Object.freeze(value) as unknown as Readonly<RecipientIndexV1>;
}
let recipientIndexCacheV1:Readonly<{path:string;sha256:string;identity:string;index:Readonly<RecipientIndexV1>}>|undefined;
interface RecipientSelectionV1 {readonly key:string;readonly kind:EmployeeBindingPurposeV1;readonly entry:Readonly<RecipientEntryV1>;readonly index:Readonly<RecipientIndexV1>;readonly path:string;readonly digest:string;}
const recipientSelectionsV1=new WeakSet<object>();
const recipientBindingCachesV1=new Map<string,BindingCache>();
const recipientBindingOriginsV1=new WeakMap<object,RecipientSelectionV1>();
const recipientProfilesV1=new WeakSet<object>();
export function employeeRecipientIndexConfiguredV1():boolean{return process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE!==undefined||process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256!==undefined;}
function currentRecipientIndexV1():Readonly<RecipientIndexV1>{
 const path=process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE,digest=process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256,prior=recipientIndexCacheV1;
 if(!path||!digest||prior&&(prior.path!==path||prior.sha256!==digest))return unavailable();
 const file=protectedRead(path,digest),index=validateEmployeeRecipientIndexV1(parseClosedJson(file.bytes,65536));
 if(canonicalJson(index)!==file.bytes.toString('utf8')||prior&&prior.identity!==file.identity)return unavailable();
 const now=Date.now();if(now<instant(index.valid_from)||now>=Math.min(instant(index.expires_at),instant(index.original_horizon)))return unavailable();
 recipientIndexCacheV1=prior??Object.freeze({path,sha256:digest,identity:file.identity,index});return recipientIndexCacheV1.index;
}
/** Static origin restriction only: no auth, employee SQL, transport or key reads. */
function validateEmployeeProfileV1(kind:EmployeeBindingPurposeV1,bytes:Uint8Array):Readonly<EmployeeBindingsV1[EmployeeBindingPurposeV1]>{
 const value=parseClosedJson(bytes,kind==='viewer'?65536:16384);
 return kind==='recommendation'?validateRecommendationBindingV1(value):kind==='answer'||kind==='mcp-answer'?validateConnectedAnswerBinding(value,kind==='answer'?'web':'mcp'):kind==='meeting'?validateMeetingBinding(value,false):kind==='conversation'?validateConversationBinding(value):kind==='review'?validateModelReviewBinding(value):kind==='upload'?validateUploadBinding(value):kind==='viewer'?validateViewerBinding(value):validateBinding(value);
}
export function admitEmployeeRecipientOriginV1(kind:EmployeeBindingPurposeV1,configuredProjectUrl:string,requestOrigin:string|null,actualRequestURL:string):Readonly<{origin:string;validUntil:number}>{
 if(!employeePurposesV1.includes(kind)||!httpsOrigin(configuredProjectUrl)||!requestOrigin)return unavailable();
 const index=currentRecipientIndexV1();
 const entries=index.recipients.filter(entry=>entry.project_url===configuredProjectUrl&&entry.bindings[kind]);
 if(entries.length===0)return unavailable();
 let matched=false,validUntil=Math.min(instant(index.expires_at),instant(index.original_horizon));
 for(const entry of entries){
  const pin=entry.bindings[kind]!,file=protectedRead(pin.path,pin.sha256),profile=validateEmployeeProfileV1(kind,file.bytes),now=Date.now();
  if(canonicalJson(profile)!==file.bytes.toString('utf8')||!matchesIdentity(profile as ServerBinding,{configuredProjectUrl,actualProjectUrl:configuredProjectUrl,verifiedUserId:entry.auth_user_id,employeeId:entry.employee_id,disabledAt:null})||[index.issuer_actor,index.reviewer_actor].includes(profile.principal_id)||instant(profile.expires_at)>instant(index.expires_at)||instant(profile.original_horizon)>instant(index.original_horizon)||now<instant(profile.valid_from)||now>=Math.min(instant(profile.expires_at),instant(profile.original_horizon)))return unavailable();
  if(requestOrigin===profile.web_origin&&new URL(actualRequestURL).origin===profile.web_origin){matched=true;validUntil=Math.min(validUntil,instant(profile.expires_at),instant(profile.original_horizon));}
 }
 if(!matched||currentRecipientIndexV1()!==index)return unavailable();
 return Object.freeze({origin:requestOrigin,validUntil});
}
export function readInstalledEmployeeBindingV1<P extends EmployeeBindingPurposeV1>(kind:P,snapshot:IdentitySnapshot):InstalledBinding<EmployeeBindingsV1[P]>{
 if(!employeePurposesV1.includes(kind)||!snapshot||snapshot.disabledAt!==null||snapshot.actualProjectUrl!==snapshot.configuredProjectUrl||!canonicalUuid(snapshot.verifiedUserId)||!canonicalUuid(snapshot.employeeId))return unavailable();
 const index=currentRecipientIndexV1(),entries=index.recipients.filter(e=>matchesIdentity(e,snapshot));if(entries.length!==1)return unavailable();
 const entry=entries[0]!,pin=entry.bindings[kind];if(!pin)return unavailable();
 const selected=Object.freeze({key:canonicalJson([entry.project_url,entry.auth_user_id,entry.employee_id,kind]),kind,entry,index,path:pin.path,digest:pin.sha256});recipientSelectionsV1.add(selected);
 return loadInstalledBinding(kind,selected) as InstalledBinding<EmployeeBindingsV1[P]>;
}
export function rereadInstalledEmployeeBindingV1(initial:InstalledBinding<ProtectedBinding>):InstalledBinding<ProtectedBinding>|undefined{
 const selected=recipientBindingOriginsV1.get(initial);if(!selected){if(recipientProfilesV1.has(initial.profile))return unavailable();return undefined;}return loadInstalledBinding(selected.kind,selected);
}
export function installedEmployeeRecipientHorizonV1(initial:InstalledBinding<ProtectedBinding>):number{
 const selected=recipientBindingOriginsV1.get(initial);if(!selected)return Infinity;currentRecipientIndexV1();return Math.min(instant(selected.index.expires_at),instant(selected.index.original_horizon));
}

interface BindingCache { readonly path: string; readonly digest: string; readonly identity: string; readonly profile: Readonly<ProtectedBinding>; readonly files: readonly PinnedFile[] }
let adviceInstalled:BindingCache|undefined,installed:BindingCache|undefined, viewerInstalled:BindingCache|undefined, reviewInstalled:BindingCache|undefined, uploadInstalled:BindingCache|undefined,conversationInstalled:BindingCache|undefined,meetingInstalled:BindingCache|undefined,meetingIngressInstalled:BindingCache|undefined,meetingWorkerInstalled:BindingCache|undefined,answerInstalled:BindingCache|undefined,mcpAnswerInstalled:BindingCache|undefined,normalizationInstalled:BindingCache|undefined,queueInstalled:BindingCache|undefined;
const queueOrigins=new WeakSet<object>();
type FixedSupervisionLoader='meeting-supervision-scheduler'|'meeting-supervision-stop';
const supervisionCaches=new Map<FixedSupervisionLoader,BindingCache>();
const supervisionOrigins=new WeakMap<object,FixedSupervisionLoader>();
const supervisionConfiguration={
 'meeting-supervision-scheduler':['ORACLE2_MEETING_SCHEDULER_SUPERVISION_BINDING','meeting-scheduler-process-v1'],
 'meeting-supervision-stop':['ORACLE2_MEETING_STOP_SUPERVISION_BINDING','meeting-stop-worker-process-v1'],
} as const;
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
function loadInstalledBinding(purpose:'recommendation'|'recommendation-actions'|'control'|'viewer'|'upload'|'review'|'conversation'|'meeting'|'meeting-ingress'|'meeting-worker'|'answer'|'mcp-answer'|'meeting-normalization'|'meeting-queue'|FixedSupervisionLoader|FixedWorkerLoader,recipient?:RecipientSelectionV1): InstalledBinding<ProtectedBinding> {
  if(recipient){if(!recipientSelectionsV1.has(recipient)||recipient.kind!==purpose||currentRecipientIndexV1()!==recipient.index)return unavailable();}
  const supervision=Object.hasOwn(supervisionConfiguration,purpose)?purpose as FixedSupervisionLoader:undefined;
  const supervisionFixed=supervision?supervisionConfiguration[supervision]:undefined;
  const fixedWorker=Object.hasOwn(fixedWorkerConfiguration,purpose)?purpose as FixedWorkerLoader:undefined;
  const fixed=fixedWorker?fixedWorkerConfiguration[fixedWorker]:undefined;
  const advice=purpose==='recommendation-actions'||purpose==='recommendation';
  const answer=purpose==='answer',mcpAnswer=purpose==='mcp-answer',normalization=purpose==='meeting-normalization',queue=purpose==='meeting-queue';
  const viewer=purpose==='viewer',upload=purpose==='upload',review=purpose==='review',conversation=purpose==='conversation';
  const meeting=purpose==='meeting',ingress=purpose==='meeting-ingress',worker=purpose==='meeting-worker'||fixedWorker!==undefined;
  const prior=recipient?recipientBindingCachesV1.get(recipient.key):advice?adviceInstalled:queue?queueInstalled:supervision?supervisionCaches.get(supervision):normalization?normalizationInstalled:fixedWorker?fixedWorkerCaches.get(fixedWorker):answer?answerInstalled:mcpAnswer?mcpAnswerInstalled:worker?meetingWorkerInstalled:ingress?meetingIngressInstalled:meeting?meetingInstalled:conversation?conversationInstalled:review?reviewInstalled:upload?uploadInstalled:viewer?viewerInstalled:installed;
  const path = recipient?recipient.path:advice?process.env.ORACLE2_RECOMMENDATION_ACTIONS_BINDING_FILE:queue?process.env.ORACLE2_MEETING_QUEUE_BINDING_FILE:supervisionFixed?process.env[supervisionFixed[0]+'_FILE']:normalization?process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_FILE:fixed?process.env[fixed[0]+'_FILE']:answer?process.env.ORACLE2_CONNECTED_ANSWER_BINDING_FILE:mcpAnswer?process.env.ORACLE2_MCP_ANSWER_BINDING_FILE:worker?process.env.ORACLE2_MEETING_WORKER_BINDING_FILE:ingress?process.env.ORACLE2_MEETING_INGRESS_BINDING_FILE:meeting?process.env.ORACLE2_MEETING_CONTROL_BINDING_FILE:conversation?process.env.ORACLE2_CONVERSATION_BINDING_FILE:review?process.env.ORACLE2_REPLACEMENT_REVIEW_BINDING_FILE:upload?process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE:viewer?process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_FILE:process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE;
  const digest = recipient?recipient.digest:advice?process.env.ORACLE2_RECOMMENDATION_ACTIONS_BINDING_SHA256:queue?process.env.ORACLE2_MEETING_QUEUE_BINDING_SHA256:supervisionFixed?process.env[supervisionFixed[0]+'_SHA256']:normalization?process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_SHA256:fixed?process.env[fixed[0]+'_SHA256']:answer?process.env.ORACLE2_CONNECTED_ANSWER_BINDING_SHA256:mcpAnswer?process.env.ORACLE2_MCP_ANSWER_BINDING_SHA256:worker?process.env.ORACLE2_MEETING_WORKER_BINDING_SHA256:ingress?process.env.ORACLE2_MEETING_INGRESS_BINDING_SHA256:meeting?process.env.ORACLE2_MEETING_CONTROL_BINDING_SHA256:conversation?process.env.ORACLE2_CONVERSATION_BINDING_SHA256:review?process.env.ORACLE2_REPLACEMENT_REVIEW_BINDING_SHA256:upload?process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_SHA256:viewer?process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_SHA256:process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256;
  if (!path || !digest || (prior && (path !== prior.path || digest !== prior.digest))) return unavailable();
  const pinned = protectedRead(path, digest);
  const profile = recipient?validateEmployeeProfileV1(recipient.kind,pinned.bytes):advice?validateRecommendationBindingV1(parseClosedJson(pinned.bytes,16384)):queue?validateMeetingQueueBinding(parseClosedJson(pinned.bytes,16384)):supervision?validateMeetingSupervisionBinding(parseClosedJson(pinned.bytes,16384)):normalization?validateMeetingNormalizationBinding(parseClosedJson(pinned.bytes,16384)):answer||mcpAnswer?validateConnectedAnswerBinding(parseClosedJson(pinned.bytes,16384),answer?'web':'mcp'):worker?validateMeetingWorkerBinding(parseClosedJson(pinned.bytes,65536)):ingress?validateMeetingBinding(parseClosedJson(pinned.bytes,16384),true):meeting?validateMeetingBinding(parseClosedJson(pinned.bytes,16384),false):conversation?validateConversationBinding(parseClosedJson(pinned.bytes,16384)):review?validateModelReviewBinding(parseClosedJson(pinned.bytes,16384)):upload?validateUploadBinding(parseClosedJson(pinned.bytes,16384)):viewer?validateViewerBinding(parseClosedJson(pinned.bytes,65536)):validateBinding(parseClosedJson(pinned.bytes,16384));
  if(supervisionFixed&&(profile.purpose!=='meeting-supervision-service-binding-v1'||profile.process_purpose!==supervisionFixed[1]))return unavailable();
  if(fixed&&(profile.purpose!=='replacement-meeting-worker-binding-v1'||profile.effect_purpose!==fixed[1]||(profile.retrieve_stage??null)!==fixed[2]))return unavailable();
  if(recipient&&([recipient.index.issuer_actor,recipient.index.reviewer_actor].includes(profile.principal_id)||!matchesIdentity(profile as ServerBinding,{configuredProjectUrl:recipient.entry.project_url,actualProjectUrl:recipient.entry.project_url,verifiedUserId:recipient.entry.auth_user_id,employeeId:recipient.entry.employee_id,disabledAt:null})||instant(profile.expires_at)>instant(recipient.index.expires_at)||instant(profile.original_horizon)>instant(recipient.index.original_horizon)))return unavailable();
  const now = Date.now();
  if (now < instant(profile.valid_from) || now >= instant(profile.expires_at) || now >= instant(profile.original_horizon)) return unavailable();
  const files = [protectedRead(profile.server_ca_file,profile.server_ca_sha256),protectedRead(profile.client_certificate_file,profile.client_certificate_sha256),protectedRead(profile.client_key_file,profile.client_key_sha256)];
  if(profile.purpose==='replacement-meeting-worker-binding-v1')files.push(protectedRead(profile.provider_ca_file,profile.provider_ca_sha256),protectedRead(profile.provider_key_file,profile.provider_key_sha256),protectedRead(profile.receipt_initialization_file,profile.receipt_initialization_sha256));
  if(profile.purpose==='replacement-meeting-ingress-web-binding-v1')files.push(protectedRead(profile.verifier_secret_file,profile.verifier_secret_sha256));
  if (prior && (prior.identity !== pinned.identity || files.some((f,i) => f.identity !== prior.files[i]!.identity || f.path !== prior.files[i]!.path || f.digest !== prior.files[i]!.digest))) return unavailable();
  const cert = new X509Certificate(files[1]!.bytes);
  if (sha256(cert.raw) !== profile.client_certificate_der_sha256 || !cert.subjectAltName?.split(', ').includes('URI:' + profile.client_uri) || now < Date.parse(cert.validFrom) || now >= Date.parse(cert.validTo)) return unavailable();
  const others=[adviceInstalled,installed,viewerInstalled,reviewInstalled,uploadInstalled,conversationInstalled,meetingInstalled,meetingIngressInstalled,meetingWorkerInstalled,answerInstalled,mcpAnswerInstalled,normalizationInstalled,queueInstalled,...supervisionCaches.values(),...fixedWorkerCaches.values(),...recipientBindingCachesV1.values()].filter(other=>other&&other!==prior);
  if(others.some(other=>other&&(profile.client_certificate_der_sha256===other.profile.client_certificate_der_sha256||profile.client_uri===other.profile.client_uri||cert.publicKey.equals(new X509Certificate(other.files[1]!.bytes).publicKey))))return unavailable();
  const key = createPrivateKey(files[2]!.bytes);
  if (!cert.checkPrivateKey(key) || !createPublicKey(key).equals(cert.publicKey)) return unavailable();
  const cache=prior??{path,digest,identity:pinned.identity,profile,files};
  if(recipient)recipientBindingCachesV1.set(recipient.key,cache);else if(advice)adviceInstalled=cache;else if(queue)queueInstalled=cache;else if(supervision)supervisionCaches.set(supervision,cache);else if(normalization)normalizationInstalled=cache;else if(fixedWorker)fixedWorkerCaches.set(fixedWorker,cache);else if(answer)answerInstalled=cache;else if(mcpAnswer)mcpAnswerInstalled=cache;else if(worker)meetingWorkerInstalled=cache;else if(ingress)meetingIngressInstalled=cache;else if(meeting)meetingInstalled=cache;else if(conversation)conversationInstalled=cache;else if(review)reviewInstalled=cache;else if(upload)uploadInstalled=cache;else if(viewer)viewerInstalled=cache;else installed=cache;
  const result={profile:cache.profile,ca:files[0]!.bytes,cert:files[1]!.bytes,key:files[2]!.bytes};
  if(recipient){recipientProfilesV1.add(cache.profile);recipientBindingOriginsV1.set(result,recipient);}
  if(queue)queueOrigins.add(result);if(supervision)supervisionOrigins.set(result,supervision);if(normalization)normalizationOrigins.add(result);if(worker)workerOrigins.set(result,fixedWorker??'meeting-worker');return result;
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

const normalizationOrigins=new WeakSet<object>();
export function readInstalledMeetingNormalizationBinding():InstalledBinding<MeetingNormalizationBinding>{try{return loadInstalledBinding('meeting-normalization') as InstalledBinding<MeetingNormalizationBinding>;}catch{return unavailable();}}
export function rereadInstalledMeetingNormalizationBinding(initial:InstalledBinding<MeetingNormalizationBinding>):InstalledBinding<MeetingNormalizationBinding>{if(!normalizationOrigins.has(initial))return unavailable();return readInstalledMeetingNormalizationBinding();}

export function readInstalledMeetingSchedulerSupervisionBinding():InstalledBinding<MeetingSupervisionBinding>{try{return loadInstalledBinding('meeting-supervision-scheduler') as InstalledBinding<MeetingSupervisionBinding>;}catch{return unavailable();}}
export function readInstalledMeetingStopSupervisionBinding():InstalledBinding<MeetingSupervisionBinding>{try{return loadInstalledBinding('meeting-supervision-stop') as InstalledBinding<MeetingSupervisionBinding>;}catch{return unavailable();}}
export function rereadInstalledMeetingSupervisionBinding(initial:InstalledBinding<MeetingSupervisionBinding>):InstalledBinding<MeetingSupervisionBinding>{const kind=supervisionOrigins.get(initial);if(!kind)return unavailable();try{return loadInstalledBinding(kind) as InstalledBinding<MeetingSupervisionBinding>;}catch{return unavailable();}}

/** Fixed local STOP-process runtime configuration; contains no self hash/scope.
 * Independently installed profile/SQL relations later pin these actual bytes.
 * This descriptor does not install a process, grant effects or create a window.
 */
export interface MeetingStopProcessConfigV1 {
 readonly schema_version:1;readonly purpose:'meeting-stop-process-runtime-v1';readonly workspace_id:string;readonly meeting_id:string;readonly provider_account:string;
 readonly create_operation_id:string;readonly create_request_sha256:string;readonly capture_until:string;readonly stop_valid_from:string;readonly stop_until:string;readonly original_horizon:string;
 readonly scheduler_poll_seconds:number;readonly stop_request_seconds:number;readonly safety_allowance_seconds:number;readonly stop_margin_seconds:number;
 readonly socket_file:string;readonly observer_uid:number;readonly valid_from:string;readonly expires_at:string;readonly readonly_wait_count:number;readonly readonly_wait_milliseconds:number;readonly post_stop_delay_milliseconds:number;readonly issuer_actor:string;readonly reviewer_actor:string;
}
function stopProcessConfigV1(v:unknown):Readonly<MeetingStopProcessConfigV1>{
 const keys=['schema_version','purpose','workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','capture_until','stop_valid_from','stop_until','original_horizon','scheduler_poll_seconds','stop_request_seconds','safety_allowance_seconds','stop_margin_seconds','socket_file','observer_uid','valid_from','expires_at','readonly_wait_count','readonly_wait_milliseconds','post_stop_delay_milliseconds','issuer_actor','reviewer_actor'];
 if(!exact(v,keys)||v.schema_version!==1||v.purpose!=='meeting-stop-process-runtime-v1'||!canonicalUuid(v.workspace_id)||!canonicalUuid(v.meeting_id)||!canonicalUuid(v.create_operation_id)||!canonicalHash(v.create_request_sha256)||!text(v.provider_account,256)||!text(v.socket_file,103)||!isAbsolute(v.socket_file)||resolve(v.socket_file)!==v.socket_file||!text(v.issuer_actor,256)||!text(v.reviewer_actor,256)||v.issuer_actor===v.reviewer_actor)return unavailable();
 const integer=(x:unknown,a:number,b:number)=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=a&&x<=b;
 if(!integer(v.observer_uid,0,2147483647)||!integer(v.scheduler_poll_seconds,1,30)||!integer(v.stop_request_seconds,1,30)||!integer(v.safety_allowance_seconds,1,60)||!integer(v.stop_margin_seconds,3,120)||!integer(v.readonly_wait_count,1,30)||!integer(v.readonly_wait_milliseconds,1,1000)||!integer(v.post_stop_delay_milliseconds,0,5000))return unavailable();
 const start=instant(v.stop_valid_from),capture=instant(v.capture_until),stop=instant(v.stop_until),horizon=instant(v.original_horizon),from=instant(v.valid_from),until=instant(v.expires_at);
 if(!(start<=from&&from<capture&&capture<=stop&&stop<=horizon&&until<=stop&&from<until)||(v.stop_margin_seconds as number)<(v.scheduler_poll_seconds as number)+(v.stop_request_seconds as number)+(v.safety_allowance_seconds as number))return unavailable();
 return Object.freeze(v) as unknown as Readonly<MeetingStopProcessConfigV1>;
}
const localStopConfigurations=new WeakMap<object,PinnedFile>();
export function readInstalledMeetingStopProcessConfigV1():Readonly<MeetingStopProcessConfigV1>{
 const path=process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_FILE,hash=process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_SHA256;if(!path||!hash)return unavailable();
 const file=protectedRead(path,hash),value=parseClosedJson(file.bytes,16384);if(canonicalJson(value)!==file.bytes.toString('utf8'))return unavailable();const result=stopProcessConfigV1(value);localStopConfigurations.set(result,file);return result;
}
export function currentInstalledMeetingStopProcessConfigV1(config:Readonly<MeetingStopProcessConfigV1>):void{
 const file=localStopConfigurations.get(config);if(!file||process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_FILE!==file.path||process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_SHA256!==file.digest)return unavailable();
 const actual=protectedRead(file.path,file.digest);if(actual.identity!==file.identity||canonicalJson(config)!==actual.bytes.toString('utf8')||!(instant(config.valid_from)<=Date.now()&&Date.now()<Math.min(instant(config.expires_at),instant(config.stop_until),instant(config.original_horizon))))return unavailable();
}

/** Fixed source process only; no caller-selected file/hash or liveness grant. */
export function currentInstalledMeetingStopProcessRuntimeV1(config:Readonly<MeetingStopProcessConfigV1>):void{
 currentInstalledMeetingStopProcessConfigV1(config);const file=localStopConfigurations.get(config);if(!file||process.platform!=='linux'||process.argv.length!==3||process.argv[2]!==file.path||process.getuid?.()!==config.observer_uid)return unavailable();
 const installed=readInstalledMeetingStopSupervisionBinding(),p=installed.profile;
 if(p.process_purpose!=='meeting-stop-worker-process-v1'||p.process_config_sha256!==file.digest||p.workspace_id!==config.workspace_id||p.meeting_id!==config.meeting_id||instant(p.capture_until)!==instant(config.capture_until)||instant(p.stop_until)!==instant(config.stop_until)||instant(p.original_horizon)>instant(config.original_horizon))return unavailable();
 protectedRead(process.argv[1]!,p.process_runtime_sha256);rereadInstalledMeetingSupervisionBinding(installed);
}

export function readInstalledMeetingQueueBinding():InstalledBinding<MeetingQueueBinding>{try{return loadInstalledBinding('meeting-queue') as InstalledBinding<MeetingQueueBinding>;}catch{return unavailable();}}
export function rereadInstalledMeetingQueueBinding(initial:InstalledBinding<MeetingQueueBinding>):InstalledBinding<MeetingQueueBinding>{if(!queueOrigins.has(initial))return unavailable();return readInstalledMeetingQueueBinding();}
