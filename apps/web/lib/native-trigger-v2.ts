import identity from '../../../dev/oracle2/native-v2-fixed-identities.json';
// New separately authorized invented test. Existing mTLS/browser adapter stays intact.
import { createHash,randomUUID,timingSafeEqual } from 'node:crypto';
import { mkdtempSync,writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { tasks,runs,auth as triggerAuth } from '@trigger.dev/sdk/v3';
import { pilotPostgres } from './oracle2-postgres';
import { NATIVE_COOKIE } from './native-browser-auth';

const JOB=identity.run;
const WORKSPACE=identity.workspace;
const ACTOR=identity.actor;
const TASK=identity.task;
const PURPOSE=identity.purpose;
const GRAPH=identity.graph_name;
const HASH=/^[a-f0-9]{64}$/;
const sha=(v:string|Uint8Array)=>createHash('sha256').update(v).digest('hex');
const exact=(v:unknown,keys:string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===keys.sort().join('|');
function deny():never{throw Error('New native test unavailable');}
export const nativeTriggerV2Enabled=()=>process.env.ORACLE2_NATIVE_TRIGGER_MODE==='v2';
const SOURCE_ROWS:Array<[string,string]>=[[identity.source_a,identity.source_texts[0]!],[identity.source_b,identity.source_texts[1]!]];
const SOURCES=SOURCE_ROWS.map(([source_id,text])=>({schema_version:1,workspace_id:WORKSPACE,source_id,revision:1,original_sha256:sha(text),reading_sha256:sha(text),parser_id:sha(identity.parser_label)}));
function canonical(v:unknown):string{if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical((v as Record<string,unknown>)[k])).join(',')+'}';}
type Settings={schema_version:1;purpose:typeof PURPOSE;issued_at:number;expires_at:number;runtime_hash:string;review_hash:string;release_hash:string;admission_hash:string;files:{database_url:string;database_ca:string}};
let cached:{seal:string;url:string}|undefined;
export function triggerV2Settings(now=Math.floor(Date.now()/1000)){
 if(['ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY','ZHIPU_API_KEY','AZURE_OPENAI_API_KEY','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL','ORACLE2_PREVIEW_ADMIN_URL','ORACLE_NATIVE_ADMIN_URL','ORACLE2_NATIVE_TRIGGER_BUNDLE','ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256'].some(k=>process.env[k]!==undefined))deny();
 const raw=process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE;const seal=process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE_SHA256;
 if(!raw||Buffer.byteLength(raw)>65536||!seal||!HASH.test(seal)||sha(raw)!==seal)deny();
 const value:unknown=JSON.parse(raw!);
 if(!exact(value,['schema_version','purpose','issued_at','expires_at','runtime_hash','review_hash','release_hash','admission_hash','files']))deny();
 const c=value as unknown as Settings;
 if(c.schema_version!==1||c.purpose!==PURPOSE||!Number.isSafeInteger(c.issued_at)||!Number.isSafeInteger(c.expires_at)||c.issued_at>now||now>=c.expires_at||c.expires_at>c.issued_at+3600||![c.runtime_hash,c.review_hash,c.release_hash,c.admission_hash].every(v=>typeof v==='string'&&HASH.test(v))||c.admission_hash!==sha(identity.parser_label)||!exact(c.files,['database_url','database_ca']))deny();
 if(cached?.seal!==seal){
  const dir=mkdtempSync(join(tmpdir(),'oracle-native-web-'));const ca=join(dir,'database-ca.crt');
  for(const v of Object.values(c.files))if(typeof v!=='string'||v.length>40000||!v.length||!/^[A-Za-z0-9+/]+={0,2}$/.test(v))deny();
  writeFileSync(ca,Buffer.from(c.files.database_ca,'base64'),{mode:0o600});
  const u=new URL(Buffer.from(c.files.database_url,'base64').toString('utf8'));
  if(u.protocol!=='postgresql:'||u.hostname!=='aws-0-us-east-1.pooler.supabase.com'||u.port!=='5432'||u.pathname!=='/oracle_native_proof_v2'||decodeURIComponent(u.username)!=='oracle_native_v2_gateway.wfdrklofsczspazshaib'||!u.password||u.search||u.hash)deny();
  u.searchParams.set('sslmode','verify-full');u.searchParams.set('sslrootcert',ca);cached={seal:seal!,url:u.toString()};
 }
 return {c,url:cached!.url,seal:seal!};
}
export function nativeTriggerV2CompletionMatches(output:unknown,expected:{runtimeHash:string;releaseHash:string;artifactHash:string;resultSha256:string;expiresAt:number}){
 return exact(output,['schema_version','state','job_id','workspace_id','runtime_hash','release_hash','artifact_hash','result_sha256','sdk_version','graph_name','expires_at'])&&output.schema_version===1&&output.state==='completed'&&output.job_id===JOB&&output.workspace_id===WORKSPACE&&output.runtime_hash===expected.runtimeHash&&output.release_hash===expected.releaseHash&&output.artifact_hash===expected.artifactHash&&output.result_sha256===expected.resultSha256&&output.sdk_version==='1.4.0'&&output.graph_name===GRAPH&&output.expires_at===expected.expiresAt;
}
async function metadata(){
 const {c,url,seal}=triggerV2Settings();const sql=pilotPostgres(url);
 try{return await sql.begin(async tx=>{
  await tx`SET LOCAL statement_timeout='5s'`;await tx`SET LOCAL lock_timeout='2s'`;
  const [login]=await tx`SELECT session_user AS login,current_database() AS database,current_user AS role,rolcanlogin,rolinherit,rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls OR rolreplication AS powerful FROM pg_roles WHERE rolname=session_user`;
  if(login?.login!=='oracle_native_v2_gateway'||login.database!==identity.database||login.role!==identity.groups.gateway||login.rolcanlogin!==true||login.rolinherit!==false||login.powerful!==false)deny();
  const membership=await tx`WITH RECURSIVE members(oid) AS (SELECT roleid FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=session_user) UNION SELECT a.roleid FROM pg_auth_members a JOIN members m ON a.member=m.oid) SELECT rolname FROM pg_roles WHERE oid IN (SELECT oid FROM members) ORDER BY rolname`;
  if(membership.length!==1||membership[0]?.rolname!=='oracle_native_v2_gateway_metadata')deny();
  const [admin]=await tx`SELECT count(*)::int AS count FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=session_user) AND admin_option`;
  if(admin?.count!==0)deny();
  await tx`SET LOCAL ROLE oracle_native_v2_gateway_metadata`;
  const [role]=await tx`SELECT rolcanlogin,rolinherit,rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls OR rolreplication AS powerful FROM pg_roles WHERE rolname=current_user`;
  if(role?.rolcanlogin!==false||role.rolinherit!==false||role.powerful!==false)deny();
  const rows=await tx`SELECT v.workspace_id,v.actor_id,v.release_hash,v.expires_at,m.payload FROM oracle2.operating_view_runs v JOIN oracle2.operating_release_selectors s ON s.workspace_id=v.workspace_id AND s.release_id=v.release_id JOIN oracle2.operating_release_manifests m ON m.workspace_id=v.workspace_id AND m.release_id=v.release_id AND m.content_hash=v.release_hash WHERE v.run_id=${JOB}::uuid AND v.workspace_id=${WORKSPACE}::uuid AND v.actor_id=${ACTOR}::uuid AND v.expires_at>clock_timestamp()`;
  if(rows.length!==1)deny();const row=rows[0]!;
  if(row.release_hash!==c.release_hash||row.payload.runtime_digest!==c.runtime_hash||row.payload.independent_review_hash!==c.review_hash||row.payload.acceptance_state!=='synthetic'||canonical(row.payload.source_refs)!==canonical(SOURCES)||Math.floor(new Date(row.expires_at).getTime()/1000)!==c.expires_at)deny();
  const [pack]=await tx`SELECT * FROM oracle2.gateway_view_result(${JOB}::uuid,${c.runtime_hash},${c.admission_hash})`;
  const [run]=await tx`SELECT oracle2.native_trigger_run(${JOB}::uuid) AS id`;
  if(!pack||!['pending','completed'].includes(pack.result_status))deny();
  triggerV2Settings();return {c,url,seal,artifactHash:row.payload.artifact_content_hash as string,status:pack.result_status as 'pending'|'completed',bytes:pack.canonical_pack===null?null:Buffer.from(pack.canonical_pack),triggerId:run?.id as string|null};
 });}finally{await sql.end({timeout:1});}
}
async function withSql<T>(fn:(sql:ReturnType<typeof pilotPostgres>)=>Promise<T>){const {url}=triggerV2Settings();const sql=pilotPostgres(url);try{return await fn(sql);}finally{await sql.end({timeout:1});}}
const cookieId=(headers:Headers)=>{const values=(headers.get('cookie')??'').split(';').map(s=>s.trim()).filter(s=>s.startsWith(NATIVE_COOKIE+'='));if(values.length!==1)return null;const v=decodeURIComponent(values[0]!.slice(NATIVE_COOKIE.length+1));return /^[a-f0-9-]{36}$/.test(v)?v:null;};
type Auth={ok:true;actorId:string;sessionId:string}|{ok:false;status:number;error:string};
const token=()=>process.env.ORACLE2_NATIVE_TRIGGER_TOKEN;
export async function createTriggerNativeV2Session(provided:string):Promise<Auth>{try{
 const expected=token();if(!expected||!provided||Buffer.byteLength(provided)>4096||!timingSafeEqual(Buffer.from(sha(expected),'hex'),Buffer.from(sha(provided),'hex')))return {ok:false,status:401,error:'Native issuer token required'};
 const before=await metadata();const sessionId=randomUUID();await withSql(async sql=>{await sql`SELECT oracle2.native_trigger_session_create(${sha(sessionId)},${before.seal},${sha(expected)})`;});
 if(token()!==expected||triggerV2Settings().seal!==before.seal)deny();return {ok:true,actorId:ACTOR,sessionId};
 }catch{return {ok:false,status:403,error:'Current new native permission unavailable'};}}
export async function authorizeTriggerNativeV2Request(headers:Headers):Promise<Auth>{try{
 const id=cookieId(headers),expected=token();if(!id||!expected)return {ok:false,status:401,error:'Native session required'};
 const m=await metadata();const live=await withSql(async sql=>{const [r]=await sql`SELECT oracle2.native_trigger_session_live(${sha(id)},${m.seal},${sha(expected)}) AS live`;return r?.live;});
 if(live!==true||token()!==expected||triggerV2Settings().seal!==m.seal)deny();return {ok:true,actorId:ACTOR,sessionId:id};
 }catch{return {ok:false,status:403,error:'Current new native permission unavailable'};}}
export async function destroyTriggerNativeV2Session(id:string){await withSql(async sql=>{await sql`SELECT oracle2.native_trigger_session_revoke(${sha(id)})`;});}
const error=(status:number)=>Response.json({error:'Hosted invented-data test unavailable'},{status,headers:{'Cache-Control':'no-store'}});
export async function nativeTriggerV2HasEmptyBody(req:Request,timeoutMs=1000):Promise<boolean>{
 if(req.headers.has('transfer-encoding')||(req.headers.has('content-length')&&req.headers.get('content-length')!=='0'))return false;
 if(req.method==='GET')return req.body===null;
 if(req.body===null)return true;
 if(!Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>1000)return false;
 try{
  const stream=Readable.fromWeb(req.body as Parameters<typeof Readable.fromWeb>[0],{highWaterMark:1});
  return await new Promise<boolean>(resolve=>{
   let settled=false;
   const finish=(empty:boolean)=>{if(settled)return;settled=true;clearTimeout(timer);stream.destroy();resolve(empty);};
   const timer=setTimeout(()=>finish(false),timeoutMs);
   stream.once('end',()=>finish(true));stream.once('error',()=>finish(false));stream.once('close',()=>finish(false));
   stream.on('readable',()=>{if(!settled&&stream.read(1)!==null)finish(false);});
   if(stream.read(1)!==null)finish(false);
  });
 }catch{return false;}
}
export type NativeV2TransportDependencies={
 authorize:typeof authorizeTriggerNativeV2Request;metadata:typeof metadata;
 dispatch:(m:Awaited<ReturnType<typeof metadata>>)=>Promise<void>;
 trigger:(key:string)=>Promise<{id:string}>;bind:(id:string)=>Promise<void>;
 retrieve:(key:string,id:string)=>Promise<{status:string;output?:unknown}>;
};
export function nativeTriggerV2Handlers(deps:NativeV2TransportDependencies){return async(req:Request,operation:'admit'|'result')=>{
 try{
  const u=new URL(req.url);if(u.search||(operation==='admit'&&(req.method!=='POST'||req.headers.get('origin')!==u.origin||req.headers.get('sec-fetch-site')==='cross-site'))||(operation==='result'&&req.method!=='GET')||!(await nativeTriggerV2HasEmptyBody(req)))return error(400);
  const auth=await deps.authorize(req.headers);if(!auth.ok)return error(auth.status);
  const m=await deps.metadata();const key=process.env.ORACLE2_NATIVE_TRIGGER_SECRET_KEY;if(!key)deny();
  if(operation==='admit'){
   if(m.status!=='pending'||m.triggerId)return error(409);
   await deps.dispatch(m);
   const handle=await deps.trigger(key);
   await deps.bind(handle.id);
   if(!(await deps.authorize(req.headers)).ok)deny();return new Response('{"state":"accepted"}',{status:202,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  }
  if(!m.triggerId||m.status==='pending')return new Response('{"state":"pending"}',{status:202,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  const run=await deps.retrieve(key,m.triggerId!);
  const output:unknown=run.output;
  if(run.status!=='COMPLETED'||!m.bytes||!nativeTriggerV2CompletionMatches(output,{runtimeHash:m.c.runtime_hash,releaseHash:m.c.release_hash,artifactHash:m.artifactHash,resultSha256:sha(m.bytes),expiresAt:m.c.expires_at}))deny();
  const after=await deps.metadata();if(after.triggerId!==m.triggerId||!after.bytes?.equals(m.bytes!)||!(await deps.authorize(req.headers)).ok)deny();
  return new Response(m.bytes!,{headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Oracle-Native-Result-Sha256':sha(m.bytes!)}});
 }catch{return error(403);}
}};
export const triggerNativeV2Handler=nativeTriggerV2Handlers({
 authorize:authorizeTriggerNativeV2Request,metadata,
 dispatch:async m=>{await withSql(async sql=>{await sql`SELECT oracle2.native_trigger_dispatch(${JOB}::uuid,${m.c.runtime_hash},${m.c.admission_hash})`;});},
 trigger:async key=>tasks.trigger(TASK,{jobId:JOB,workspaceId:WORKSPACE},{idempotencyKey:'native-invented-v2-'+JOB},{clientConfig:{accessToken:key}}),
 bind:async id=>{await withSql(async sql=>{await sql`SELECT oracle2.native_trigger_bind(${JOB}::uuid,${id})`;});},
 retrieve:async(key,id)=>triggerAuth.withAuth({accessToken:key},async()=>runs.retrieve(id)),
});
