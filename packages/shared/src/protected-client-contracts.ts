/** Closed protected service payloads; no identity or permission issuer. */
import {canonicalHash,canonicalJson,canonicalUuid,instant,parseClosedJson,sha256,MAX_ORIGINAL_BYTES} from './protected-server-binding';
import {UPLOAD_CHUNK_BYTES,UPLOAD_MAX_REQUEST_BYTES,type UploadResponse} from './protected-upload-contract';
const failure=():never=>{throw new Error('Replacement control unavailable');};
const exact=(v:unknown,fields:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===fields.length&&fields.every(k=>Object.hasOwn(v,k));
const integer=(v:unknown):v is number=>typeof v==='number'&&Number.isInteger(v)&&v>=1&&v<=2147483647;

const states = new Set(['pending','processing','delivered','revision_pending','cancelled','error','awaiting-external-authority','missing-evidence','cancel-requested','failed','UNKNOWN']);

export interface ControlMetadata {
  readonly runId: string; readonly journeyRevision: number; readonly controlState: 'pending'|'processing'|'delivered'|'revision_pending'|'cancelled'|'error'|'awaiting-external-authority'|'missing-evidence'|'cancel-requested'|'failed'|'UNKNOWN';
  readonly populationSha256: string; readonly cancelRequested: boolean; readonly remoteStopProven: false; readonly resultAvailable: false;
}

/** Descriptive wire validation; a valid DTO grants no access. */
export function parseControlMetadata(bytes: Uint8Array): Readonly<ControlMetadata> {
  const v = parseClosedJson(bytes,4096);
  if (canonicalJson(v) !== Buffer.from(bytes).toString('utf8') || !exact(v,['runId','journeyRevision','controlState','populationSha256','cancelRequested','remoteStopProven','resultAvailable']) || !canonicalUuid(v.runId) || !integer(v.journeyRevision) || typeof v.controlState !== 'string' || !states.has(v.controlState) || !canonicalHash(v.populationSha256) || typeof v.cancelRequested !== 'boolean' || v.remoteStopProven !== false || v.resultAvailable !== false) return failure();
  return Object.freeze(v) as unknown as Readonly<ControlMetadata>;
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


export interface OriginalPacket {readonly data:Buffer;readonly validUntil:string;}


export interface ModelReviewPacket {readonly review:Readonly<Record<string,unknown>>;readonly validUntil:string;}

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

/** Closed original-view wire: exact Python post-validation datetime rendering. */
export function validateOriginalViewRequest(bytes:Uint8Array):Readonly<Record<string,unknown>>{
  const v=parseClosedJson(bytes,4096);
  if(!exact(v,['schema_version','source_id','revision','caller_deadline'])||v.schema_version!==1||!canonicalUuid(v.source_id)||typeof v.revision!=='number'||!Number.isSafeInteger(v.revision)||v.revision<1||typeof v.caller_deadline!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(?!000000)[0-9]{6})?Z$/.test(v.caller_deadline)||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return failure();
  instant(v.caller_deadline);return Object.freeze(v);
}

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


export interface MeetingMetadata {
 readonly schema_version:1;readonly meeting_id:string;readonly version:number;readonly state:string;
 readonly event_id:string|null;readonly ingress_id:string|null;readonly pending_count:number;readonly valid_until:string;
 readonly qualification:false;readonly remote_stop_proven:false;readonly observation_only:true;
}

export function parseMeetingMetadata(bytes:Uint8Array):Readonly<MeetingMetadata>{
 const v=parseClosedJson(bytes,16384);
 if(!exact(v,['schema_version','meeting_id','version','state','event_id','ingress_id','pending_count','valid_until','qualification','remote_stop_proven','observation_only'])||canonicalJson(v)!==Buffer.from(bytes).toString('utf8')||v.schema_version!==1||!canonicalUuid(v.meeting_id)||!Number.isSafeInteger(v.version)||(v.version as number)<0||(v.version as number)>16384||typeof v.state!=='string'||!['not_invited','invited','joining','pending_mapping','waiting_room','recording_permission_pending','recording_permission_denied','capturing','capture_ended','capture_status_unknown','processing','final_artifact_pending','review','failed','UNKNOWN','cancelled'].includes(v.state)||(v.event_id!==null&&!canonicalUuid(v.event_id))||(v.ingress_id!==null&&!canonicalUuid(v.ingress_id))||!Number.isSafeInteger(v.pending_count)||(v.pending_count as number)<0||(v.pending_count as number)>4096||v.qualification!==false||v.remote_stop_proven!==false||v.observation_only!==true)return failure();
 instant(v.valid_until);return Object.freeze(v) as unknown as Readonly<MeetingMetadata>;
}

export function validateMeetingControl(bytes:Uint8Array):Readonly<Record<string,unknown>>{
 const v=parseClosedJson(bytes,16384);
 if(!exact(v,['schema_version','operation','meeting_id','expected_head','operation_id','payload','caller_deadline'])||v.schema_version!==1||typeof v.operation!=='string'||!['invite','status','cancel','review'].includes(v.operation)||!canonicalUuid(v.meeting_id)||!Number.isSafeInteger(v.expected_head)||(v.expected_head as number)<0||(v.expected_head as number)>16384||!canonicalUuid(v.operation_id)||!v.payload||typeof v.payload!=='object'||Array.isArray(v.payload)||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return failure();
 instant(v.caller_deadline);return Object.freeze(v);
}


export function reviewEnum(value:unknown,choices:readonly string[]):boolean{return typeof value==='string'&&choices.includes(value);}

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

/** Same closed quote owner for qualified read-only presentation protocols. */
export function validateQualifiedEvidenceV1(value:unknown,workspace:string):Readonly<Record<string,unknown>>{
 if(!canonicalUuid(workspace)||!reviewEvidence(value))return failure();
 const evidence=value as Record<string,{ref:{workspace_id:string}}[]>;
 if(Object.values(evidence).some(group=>group.some(q=>q.ref.workspace_id!==workspace)))return failure();
 return value as Readonly<Record<string,unknown>>;
}

function reviewScope(v:unknown):boolean{
 if(!exact(v,['schema_version','process','customer','product','region'])||v.schema_version!==1)return false;
 return ['process','customer','product','region'].every(k=>{const d=v[k];return exact(d,['schema_version','mode','identities'])&&d.schema_version===1&&reviewEnum(d.mode,['unknown','all','exact'])&&Array.isArray(d.identities)&&d.identities.length<=64&&d.identities.every(canonicalUuid)&&new Set(d.identities).size===d.identities.length&&(d.mode==='exact')===(d.identities.length>0)&&canonicalJson(d.identities)===canonicalJson([...d.identities].sort());});
}

export interface ConnectedAnswerPacket {
 readonly protocol:'qualified-connected-answer-v1';readonly principal_id:string;readonly workspace_id:string;readonly model_id:string;
 readonly channel:'web'|'mcp';readonly query_sha256:string;readonly checked_at:string;readonly expires_at:string;readonly answer:Readonly<Record<string,unknown>>;
}
export function validateConnectedAnswerQuery(v:unknown):Readonly<Record<string,unknown>>{
 if(!exact(v,['schema_version','question','mode','scope','process_ids','valid_at','known_at','expected_version','max_records','max_bytes','page'])||v.schema_version!==1||typeof v.question!=='string'||!v.question.trim()||v.question.includes('\0')||Buffer.byteLength(v.question,'utf8')>4000||!reviewEnum(v.mode,['local','connected','historical','global'])||(v.scope!==null&&!reviewScope(v.scope))||!Array.isArray(v.process_ids)||v.process_ids.length>32||v.process_ids.some(p=>typeof p!=='string'||!p||p.length>200||p.trim()!==p||p.includes('\0'))||new Set(v.process_ids).size!==v.process_ids.length||(v.expected_version!==null&&!integer(v.expected_version))||!integer(v.max_records)||v.max_records>64||!integer(v.max_bytes)||v.max_bytes<4096||v.max_bytes>131072||typeof v.page!=='number'||!Number.isSafeInteger(v.page)||v.page<0||v.page>2047)return failure();
 if(v.mode==='historical'){instant(v.valid_at);instant(v.known_at);}else if(v.valid_at!==null||v.known_at!==null)return failure();
 return Object.freeze(v);
}
function answerFindings(v:unknown,workspace:string):boolean{
 if(!Array.isArray(v)||v.length>1000)return false;
 return v.every(f=>{
  if(!exact(f,['schema_version','finding_id','kind','workspace_id','source_refs','affected_object_ids','process_id','scope','text','status','origin','evidence_refs','coverage_ref','supersedes','opposed_assertions','schema_revision'])||f.schema_version!==1||f.schema_revision!==1||f.workspace_id!==workspace||typeof f.finding_id!=='string'||!f.finding_id||typeof f.text!=='string'||!f.text||typeof f.scope!=='string'||!f.scope||!reviewEnum(f.kind,['missing_information','source_conflict','model_incomplete'])||!reviewEnum(f.status,['unresolved','superseded','withdrawn','needs_evidence'])||!reviewEnum(f.origin,['source_reported','reported_conflict_unverified','coverage_inference','legacy_unverified','structural_diagnostic'])||!Array.isArray(f.source_refs)||!Array.isArray(f.affected_object_ids)||!Array.isArray(f.supersedes)||!Array.isArray(f.opposed_assertions)||!reviewEvidence({supporting:[],opposing:[],unknown:f.evidence_refs,temporal:[]}))return false;
  if(f.source_refs.some(r=>!exact(r,['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id'])||r.schema_version!==1||r.workspace_id!==workspace||!canonicalUuid(r.source_id)||!integer(r.revision)||!canonicalHash(r.original_sha256)||!canonicalHash(r.reading_sha256)||typeof r.parser_id!=='string'||!r.parser_id))return false;
  if(f.coverage_ref!==null&&(!exact(f.coverage_ref,['inventory_id','inventory_hash','required_slot'])||typeof f.coverage_ref.inventory_id!=='string'||!canonicalHash(f.coverage_ref.inventory_hash)||typeof f.coverage_ref.required_slot!=='string'))return false;
  return f.opposed_assertions.every(o=>exact(o,['question_key','asserted_value','evidence'])&&typeof o.question_key==='string'&&typeof o.asserted_value==='string'&&reviewEvidence({supporting:[],opposing:[o.evidence],unknown:[],temporal:[]}));
 });
}
export function parseConnectedAnswerResponse(bytes:Uint8Array):ConnectedAnswerPacket{
 const v=parseClosedJson(bytes,262144);
 if(!exact(v,['schema_version','protocol','principal_id','workspace_id','model_id','channel','query_sha256','answer','checked_at','expires_at','current_read_lease_only','retained_receipt_body_sha256','retained_delivered_at','retained_receipt_recorded_at','retained_projection_lease_until'])||canonicalJson(v)!==Buffer.from(bytes).toString('utf8')||v.schema_version!==1||v.protocol!=='qualified-connected-answer-v1'||!canonicalUuid(v.principal_id)||!canonicalUuid(v.workspace_id)||!canonicalUuid(v.model_id)||!reviewEnum(v.channel,['web','mcp'])||!canonicalHash(v.query_sha256)||v.current_read_lease_only!==true||!canonicalHash(v.retained_receipt_body_sha256))return failure();
 const checked=instant(v.checked_at),expires=instant(v.expires_at);
 if(checked>=expires||instant(v.retained_delivered_at)>checked||instant(v.retained_receipt_recorded_at)>checked||instant(v.retained_delivered_at)>=instant(v.retained_projection_lease_until))return failure();
 validateDocumentaryAnswerV1(v.answer,{workspace_id:v.workspace_id as string,checked_at:v.checked_at as string});
 return Object.freeze(v) as unknown as ConnectedAnswerPacket;
}

/** SAME closed body validation for old and natural envelopes; no authority. */
export function validateDocumentaryAnswerV1(a:unknown,v:{readonly workspace_id:string;readonly checked_at:string}):Readonly<Record<string,unknown>>{
 if(!canonicalUuid(v.workspace_id))return failure();const checked=instant(v.checked_at);
 if(!exact(a,['schema_version','state','answer_text','model_version','model_content_hash','selection','mode','valid_at','known_at','records','findings','coverage','continuation_page','plan_sha256','caveats','provider_generation_used','query_embedding_used','business_accepted','business_decisions_as_of','process_choices'])||a.schema_version!==1||!reviewEnum(a.state,['answered','partial','missing','clarification','coverage_incomplete'])||typeof a.answer_text!=='string'||!integer(a.model_version)||!canonicalHash(a.model_content_hash)||a.selection!=='deterministic-qualified-records-v1'||!reviewEnum(a.mode,['local','connected','historical','global'])||a.provider_generation_used!==false||a.query_embedding_used!==false||a.business_accepted!==false||!canonicalHash(a.plan_sha256)||!Array.isArray(a.records)||a.records.length>64||!Array.isArray(a.caveats)||a.caveats.some(c=>typeof c!=='string')||!answerFindings(a.findings,v.workspace_id)||(a.continuation_page!==null&&(!integer(a.continuation_page)||a.continuation_page>2047)))return failure();
 if(!Array.isArray(a.process_choices)||a.process_choices.length>1000||a.process_choices.some(p=>!exact(p,['schema_version','process_id','label'])||p.schema_version!==1||typeof p.process_id!=='string'||!p.process_id||typeof p.label!=='string'||!p.label))return failure();
 instant(a.valid_at);if(a.mode==='historical'){if(instant(a.known_at)>checked)return failure();}else if(a.known_at!==null)return failure();
 for(const r of a.records){
  if(!exact(r,['schema_version','assertion','evidence','applicability','authority','company_policy_confirmed'])||r.schema_version!==1||!reviewAssertion(r.assertion)||!reviewEnum(r.applicability,['applicable','unknown'])||r.authority!=='reported'||r.company_policy_confirmed!==false||!exact(r.evidence,['schema_version','supporting','opposing','unknown','temporal'])||r.evidence.schema_version!==1||!reviewEvidence({supporting:r.evidence.supporting,opposing:r.evidence.opposing,unknown:r.evidence.unknown,temporal:r.evidence.temporal}))return failure();
 }
 const c=a.coverage;
 if(!exact(c,['schema_version','declared_population','declared_process_count','represented_process_ids','declared_assertion_count','selected_assertion_count','returned_assertion_count','complete_within_declared_model','entire_company_verified'])||c.schema_version!==1||typeof c.declared_population!=='string'||!integer(c.declared_process_count)||!integer(c.declared_assertion_count)||!Array.isArray(c.represented_process_ids)||c.represented_process_ids.some(p=>typeof p!=='string')||typeof c.complete_within_declared_model!=='boolean'||c.entire_company_verified!==false||c.returned_assertion_count!==a.records.length||typeof c.selected_assertion_count!=='number'||!Number.isSafeInteger(c.selected_assertion_count)||c.selected_assertion_count<c.returned_assertion_count)return failure();
 if(!Array.isArray(a.business_decisions_as_of)||a.business_decisions_as_of.length>128||(a.mode!=='historical'&&a.business_decisions_as_of.length))return failure();
 for(const d of a.business_decisions_as_of){if(!exact(d,['event_id','recorded_at','decision_kind','scope_sha256','assertions','challenged_as_of','withdrawn_as_of'])||!canonicalUuid(d.event_id)||instant(d.recorded_at)>instant(a.known_at)||!reviewEnum(d.decision_kind,['employee-account','process-policy','company-policy'])||!canonicalHash(d.scope_sha256)||typeof d.challenged_as_of!=='boolean'||typeof d.withdrawn_as_of!=='boolean'||!Array.isArray(d.assertions)||!d.assertions.length||d.assertions.length>2048||d.assertions.some(i=>!exact(i,['assertion_id','revision'])||!canonicalUuid(i.assertion_id)||!integer(i.revision)))return failure();}
 return Object.freeze(a) as Readonly<Record<string,unknown>>;
}
