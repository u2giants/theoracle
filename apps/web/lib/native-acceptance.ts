// Server-owned, public-invented native acceptance only. No provider/generation path.
import { constants, openSync, fstatSync, readFileSync, closeSync } from 'node:fs';
import { createHash, createHmac, randomUUID, X509Certificate, createPrivateKey } from 'node:crypto';
import { request as httpsRequest } from 'node:https';
import { checkServerIdentity } from 'node:tls';
import { pilotPostgres } from './oracle2-postgres';

const HASH=/^[a-f0-9]{64}$/;
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const LIMIT=131072;
export const sha=(raw:Uint8Array)=>createHash('sha256').update(raw).digest('hex');
type SourceRef={schema_version:1;workspace_id:string;source_id:string;revision:number;original_sha256:string;reading_sha256:string;parser_id:string};
type FilePin={path:string;sha256:string};
export type NativeSettings={schema_version:1;purpose:'public-invented-native-browser';namespace:string;hostname:string;origin:string;
  actor_id:string;workspace_id:string;job_id:string;runtime_hash:string;admission_hash:string;release_hash:string;permission_hash:string;
  worker_uri:string;source_authority_expires_at:number;worker_permit_expires_at:number;job_expires_at:number;source_refs:SourceRef[];metadata_role:string;
  database_url:FilePin;database_ca:FilePin;client_cert:FilePin;client_key:FilePin;server_ca:FilePin;hmac_key:FilePin};
const FIELDS=['schema_version','purpose','namespace','hostname','origin','actor_id','workspace_id','job_id','runtime_hash','admission_hash',
  'release_hash','permission_hash','worker_uri','source_authority_expires_at','worker_permit_expires_at','job_expires_at','source_refs','metadata_role',
  'database_url','database_ca','client_cert','client_key','server_ca','hmac_key'];
function exact(value:unknown,fields:string[]):value is Record<string,unknown>{
  return !!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join('|')===fields.slice().sort().join('|');
}
export function canonical(value:unknown):string{
  if(value===null||typeof value!=='object')return JSON.stringify(value);
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical((value as Record<string,unknown>)[k])).join(',')+'}';
}
export function protectedBytes(path:string,limit=1_000_000):Buffer{
  const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);
  try{const info=fstatSync(fd);if(!info.isFile()||(info.mode&0o077)||info.size>limit)throw Error('Protected input unavailable');
    const raw=readFileSync(fd);if(raw.length>limit)throw Error('Protected input unavailable');return raw;
  }finally{closeSync(fd);}
}
export function parseSettings(raw:Buffer,seal:string,now:number):NativeSettings{
  if(!HASH.test(seal)||sha(raw)!==seal)throw Error('Native acceptance unavailable');
  const value:unknown=JSON.parse(raw.toString('utf8'));
  if(!exact(value,FIELDS)||canonical(value)!==raw.toString('utf8'))throw Error('Native acceptance unavailable');
  const c=value as unknown as NativeSettings;
  if(c.schema_version!==1||c.purpose!=='public-invented-native-browser'||!/^[a-z0-9-]{1,100}$/.test(c.namespace)
    ||!c.worker_uri.startsWith('spiffe://oracle/')||!/^oracle2_[a-z0-9_]+$/.test(c.metadata_role))throw Error('Native acceptance unavailable');
  for(const key of ['actor_id','workspace_id','job_id'] as const)if(!UUID.test(c[key]))throw Error('Native acceptance unavailable');
  for(const key of ['runtime_hash','admission_hash','release_hash','permission_hash'] as const)if(!HASH.test(c[key]))throw Error('Native acceptance unavailable');
  const target=new URL(c.origin);
  if(target.protocol!=='https:'||target.hostname!==c.hostname||target.origin!==c.origin||target.pathname!=='/'
    ||target.username||target.password||target.search||target.hash||target.hostname==='oracle.designflow.app')throw Error('Native acceptance unavailable');
  for(const expiry of [c.source_authority_expires_at,c.worker_permit_expires_at,c.job_expires_at])if(!Number.isSafeInteger(expiry)||expiry<=now)throw Error('Native acceptance expired');
  if(!Array.isArray(c.source_refs)||!c.source_refs.length||new Set(c.source_refs.map(r=>r.source_id)).size!==c.source_refs.length)throw Error('Native sources unavailable');
  for(const ref of c.source_refs){
    if(!exact(ref,['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id'])
      ||ref.schema_version!==1||ref.workspace_id!==c.workspace_id||!UUID.test(ref.source_id)||!Number.isSafeInteger(ref.revision)||ref.revision<1
      ||!HASH.test(ref.original_sha256)||!HASH.test(ref.reading_sha256)||!HASH.test(ref.parser_id))throw Error('Native sources unavailable');
  }
  for(const key of ['database_url','database_ca','client_cert','client_key','server_ca','hmac_key'] as const){const pin=c[key];
    if(!exact(pin,['path','sha256'])||typeof pin.path!=='string'||!pin.path.startsWith('/')||!HASH.test(pin.sha256))throw Error('Protected input unavailable');}
  return c;
}
export function loadSettings(now:number):NativeSettings{
  const path=process.env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS;
  const seal=process.env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256;
  if(!path||!seal)throw Error('Native acceptance unavailable');
  return parseSettings(protectedBytes(path),seal,now);
}
function pinned(pin:FilePin,limit=1_000_000):Buffer{
  const raw=protectedBytes(pin.path,limit);if(sha(raw)!==pin.sha256)throw Error('Protected input changed');return raw;
}
export function checkCertificate(cert:Buffer,key:Buffer,workerUri:string,now:number):void{
  const leaf=new X509Certificate(cert);
  if(!(Date.parse(leaf.validFrom)<=now*1000&&now*1000<Date.parse(leaf.validTo))
    ||leaf.subjectAltName!==`URI:${workerUri}`||!leaf.checkPrivateKey(createPrivateKey(key)))throw Error('Native client identity expired or changed');
}
export function opaqueRequest(c:NativeSettings,operation:'admit'|'result',now:number,nonce:string=randomUUID()){
  const expires_at=Math.min(now+60,c.source_authority_expires_at,c.worker_permit_expires_at,c.job_expires_at);
  if(!UUID.test(nonce)||expires_at<=now)throw Error('Native acceptance expired');
  const path=`/v1/jobs/${operation}`;
  const body=Buffer.from(canonical({job_id:c.job_id,runtime_hash:c.runtime_hash,admission_hash:c.admission_hash,nonce,expires_at}));
  return {path,body};
}
export function signature(path:string,body:Buffer,key:Buffer):string{
  if(!['/v1/jobs/admit','/v1/jobs/result'].includes(path)||key.length<32)throw Error('Native authentication unavailable');
  return createHmac('sha256',key).update(Buffer.concat([Buffer.from(`POST\n${path}\n`),body])).digest('hex');
}
type NativeResponse={status:200|202;body:Buffer};
export async function nativeTransport(c:NativeSettings,operation:'admit'|'result',now:number):Promise<NativeResponse>{
  const cert=pinned(c.client_cert),key=pinned(c.client_key),ca=pinned(c.server_ca),hmac=pinned(c.hmac_key,8192);
  checkCertificate(cert,key,c.worker_uri,now);
  const envelope=opaqueRequest(c,operation,now),url=new URL(envelope.path,c.origin);
  const authSignature=signature(envelope.path,envelope.body,hmac);
  return new Promise((resolve,reject)=>{
    let finished=false;
    const fail=()=>{if(!finished){finished=true;reject(Error('Native request unavailable; no retry admitted'));}};
    let req:ReturnType<typeof httpsRequest>|undefined;
    const timer=setTimeout(()=>{req?.destroy();fail();},5000);
    req=httpsRequest(url,{method:'POST',agent:false,cert,key,ca,minVersion:'TLSv1.3',rejectUnauthorized:true,
      checkServerIdentity:(name,certificate)=>checkServerIdentity(c.hostname,certificate),
      headers:{'Content-Type':'application/json','Content-Length':envelope.body.length,'X-Oracle-Job-Signature':authSignature,
        'Accept-Encoding':'identity','Cache-Control':'no-store'}},res=>{
      const length=res.headers['content-length'];const limit=operation==='result'?LIMIT:2048;
      if((res.statusCode!==200&&res.statusCode!==202)||res.headers['content-type']!=='application/json'
        ||res.headers['cache-control']!=='no-store'||res.headers['transfer-encoding']||res.headers['content-encoding']
        ||typeof length!=='string'||!/^\d+$/.test(length)||Number(length)>limit){res.destroy();clearTimeout(timer);fail();return;}
      const chunks:Buffer[]=[];let size=0;
      res.on('data',(chunk:Buffer)=>{size+=chunk.length;if(size>limit){res.destroy();clearTimeout(timer);fail();}else chunks.push(chunk);});
      res.on('error',()=>{clearTimeout(timer);fail();});
      res.on('end',()=>{clearTimeout(timer);if(finished)return;
        if(size!==Number(length)){fail();return;}
        try{
          for(const pin of [c.client_cert,c.client_key,c.server_ca,c.hmac_key])pinned(pin);
          checkCertificate(cert,key,c.worker_uri,Math.floor(Date.now()/1000));
          const body=Buffer.concat(chunks);
          if(operation==='admit'){
            const receipt:unknown=JSON.parse(body.toString('utf8'));
            if(res.statusCode!==202||!exact(receipt,['job_id','request_hash','state'])||receipt.job_id!==c.job_id
              ||receipt.request_hash!==sha(envelope.body)||receipt.state!=='accepted')throw Error('Native admission response changed');
          }else if(res.statusCode===202&&!body.equals(Buffer.from('{"state":"pending"}')))throw Error('Native pending response changed');
          finished=true;resolve({status:res.statusCode as 200|202,body});
        }catch{fail();}
      });
    });
    req.on('error',()=>{clearTimeout(timer);fail();});req.end(envelope.body);
  });
}
type Snapshot={status:'pending'|'completed';canonical:Buffer|null;expiresAt:number};
export async function currentNativeJob(c:NativeSettings,actorId:string):Promise<Snapshot>{
  if(actorId!==c.actor_id)throw Error('Native actor denied');
  const url=pinned(c.database_url,8192).toString('utf8').trim();const parsed=new URL(url);
  pinned(c.database_ca);
  if(parsed.searchParams.get('sslmode')!=='verify-full'||parsed.searchParams.get('sslrootcert')!==c.database_ca.path
    ||decodeURIComponent(parsed.username)!==c.metadata_role)throw Error('Native metadata identity unavailable');
  const sql=pilotPostgres(url);
  try{return await sql.begin(async tx=>{
    await tx`SET LOCAL statement_timeout='5s'`;await tx`SET LOCAL lock_timeout='2s'`;
    const [identity]=await tx`SELECT current_user AS role,rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls AS powerful FROM pg_roles WHERE rolname=current_user`;
    if(identity?.role!==c.metadata_role||identity.powerful)throw Error('Native metadata identity unavailable');
    const [writes]=await tx`SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='oracle2' AND c.relkind IN ('r','p') AND (has_table_privilege(current_user,c.oid,'INSERT')
      OR has_table_privilege(current_user,c.oid,'UPDATE') OR has_table_privilege(current_user,c.oid,'DELETE'))) AS allowed`;
    if(writes?.allowed!==false)throw Error('Native metadata identity can write');
    const rows=await tx`SELECT v.workspace_id,v.actor_id,v.release_hash,v.expires_at,m.payload FROM oracle2.operating_view_runs v
      JOIN oracle2.operating_release_selectors s ON s.workspace_id=v.workspace_id AND s.release_id=v.release_id
      JOIN oracle2.operating_release_manifests m ON m.workspace_id=v.workspace_id AND m.release_id=v.release_id AND m.content_hash=v.release_hash
      WHERE v.run_id=${c.job_id}::uuid AND v.workspace_id=${c.workspace_id}::uuid AND v.actor_id=${actorId}::uuid AND v.expires_at>clock_timestamp()`;
    if(rows.length!==1)throw Error('Native current job unavailable');
    const row=rows[0]!,manifest=row.payload;
    if(row.release_hash!==c.release_hash||manifest.acceptance_state!=='synthetic'||manifest.permission_digest!==c.permission_hash
      ||canonical(manifest.source_refs)!==canonical(c.source_refs))throw Error('Native release changed');
    const [pack]=await tx`SELECT * FROM oracle2.gateway_view_result(${c.job_id}::uuid,${c.runtime_hash},${c.admission_hash})`;
    if(!pack||!['pending','completed'].includes(pack.result_status))throw Error('Native source authority unavailable');
    const expiresAt=Math.floor(new Date(row.expires_at).getTime()/1000);
    if(expiresAt!==c.job_expires_at)throw Error('Native job authority changed');
    return {status:pack.result_status,canonical:pack.canonical_pack===null?null:Buffer.from(pack.canonical_pack),expiresAt};
  });}finally{await sql.end({timeout:1});}
}
type Auth={ok:true;actorId:string;sessionId:string}|{ok:false;status:number;error:string};
export type NativeDependencies={authorize:(headers:Headers)=>Promise<Auth>;workspace:()=>string;settings:(now:number)=>NativeSettings;
  current:(settings:NativeSettings,actor:string)=>Promise<Snapshot>;transport:(settings:NativeSettings,operation:'admit'|'result',now:number)=>Promise<NativeResponse>;clock:()=>number};
const error=(status:number)=>Response.json({error:'Hosted invented-data test unavailable'},{status,headers:{'Cache-Control':'no-store'}});
export function nativeHandlers(deps:NativeDependencies){
  return async(req:Request,operation:'admit'|'result'):Promise<Response>=>{
    try{
      const auth=await deps.authorize(req.headers);if(!auth.ok)return error(auth.status);
      const url=new URL(req.url);
      if(url.search||req.headers.get('transfer-encoding')||req.headers.get('content-length')&&req.headers.get('content-length')!=='0'
        ||req.body!==null&&req.headers.get('content-length')!=='0'
        ||(operation==='admit'&&(req.headers.get('origin')!==url.origin||req.headers.get('sec-fetch-site')==='cross-site'))
        ||(operation==='result'?req.method!=='GET':req.method!=='POST'))return error(400);
      const now=deps.clock(),c=deps.settings(now);
      if(auth.actorId!==c.actor_id||deps.workspace()!==c.workspace_id)return error(403);
      const before=await deps.current(c,auth.actorId);
      if(now>=before.expiresAt||now>=Math.min(c.source_authority_expires_at,c.worker_permit_expires_at)
        ||operation==='admit'&&before.status!=='pending')return error(409);
      const response=await deps.transport(c,operation,now);
      const currentAuth=await deps.authorize(req.headers);
      if(!currentAuth.ok||currentAuth.actorId!==auth.actorId||currentAuth.sessionId!==auth.sessionId)return error(403);
      const after=await deps.current(c,auth.actorId);const end=deps.clock();
      if(end>=after.expiresAt||end>=Math.min(c.source_authority_expires_at,c.worker_permit_expires_at))return error(409);
      // Re-read sealed settings; their movement/withdrawal invalidates delivery.
      if(canonical(deps.settings(end))!==canonical(c))return error(409);
      if(operation==='result'&&(response.status===200?(after.status!=='completed'||!after.canonical?.equals(response.body))
        :(after.status!=='pending'||!response.body.equals(Buffer.from('{"state":"pending"}')))))return error(409);
      if(operation==='result'&&before.status==='completed'&&!before.canonical?.equals(response.body))return error(409);
      return new Response(new Uint8Array(response.body),{status:response.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    }catch{return error(409);}
  };
}
