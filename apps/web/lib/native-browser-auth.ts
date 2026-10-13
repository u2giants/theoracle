// Dedicated native invented sessions. Existing pilot auth stays unchanged.
import { randomUUID, createHash, timingSafeEqual } from 'node:crypto';
import { pilotToken, pilotActors } from './oracle2-pilot-auth';
import { canonical, currentNativeJob, loadSettings, verifyNativeIdentity, type NativeSettings } from './native-acceptance';

export const NATIVE_COOKIE='oracle2_native_invented_session';
export const NATIVE_COOKIE_PATH='/api/consultant/native-acceptance';
const TTL_SECONDS=300,MAX_SESSIONS=32;
const fingerprint=(value:string)=>createHash('sha256').update(value).digest('hex');
type Auth={ok:true;actorId:string;sessionId:string}|{ok:false;status:number;error:string};
type Session={sessionId:string;actorId:string;expiresAt:number;settingsFingerprint:string;tokenFingerprint:string};
export type NativeSessionDependencies={token:()=>string|undefined;actors:()=>Set<string>;settings:(now:number)=>NativeSettings;
  identity:(c:NativeSettings,now:number)=>void;current:(c:NativeSettings,actor:string)=>Promise<{expiresAt:number}>;clock:()=>number};

export function nativeSessions(deps:NativeSessionDependencies){
  const sessions=new Map<string,Session>();
  function prune(now:number){for(const [key,value] of sessions)if(value.expiresAt<=now)sessions.delete(key);}
  async function current(){
    const now=deps.clock(),expected=deps.token();
    if(!expected||Buffer.byteLength(expected)>4096)throw Error('Native issuer identity unavailable');
    const config=deps.settings(now);
    if(config.purpose!=='public-invented-native-browser'||!deps.actors().has(config.actor_id))throw Error('Native actor unavailable');
    deps.identity(config,now);
    const snapshot=await deps.current(config,config.actor_id);
    const end=deps.clock();
    const expires=Math.min(snapshot.expiresAt,config.job_expires_at,config.source_authority_expires_at,config.worker_permit_expires_at);
    if(end>=expires||!deps.actors().has(config.actor_id)||fingerprint(deps.token()??'')!==fingerprint(expected)||canonical(deps.settings(end))!==canonical(config))throw Error('Native authority changed');
    deps.identity(config,end);
    return {now:end,config,expires,tokenFingerprint:fingerprint(expected),settingsFingerprint:fingerprint(canonical(config))};
  }
  async function create(token:string):Promise<Auth>{
    try{
      const expected=deps.token();
      if(typeof token!=='string'||!token||Buffer.byteLength(token)>4096||!expected
        ||!timingSafeEqual(Buffer.from(fingerprint(token),'hex'),Buffer.from(fingerprint(expected),'hex')))
        return {ok:false,status:401,error:'Native issuer token required'};
      const state=await current();if(state.tokenFingerprint!==fingerprint(token))return {ok:false,status:403,error:'Native issuer token changed'};prune(state.now);
      if(sessions.size>=MAX_SESSIONS)return {ok:false,status:429,error:'Native session limit reached'};
      const sessionId=randomUUID();sessions.set(sessionId,{sessionId,actorId:state.config.actor_id,
        expiresAt:Math.min(state.now+TTL_SECONDS,state.expires),settingsFingerprint:state.settingsFingerprint,tokenFingerprint:state.tokenFingerprint});
      return {ok:true,actorId:state.config.actor_id,sessionId};
    }catch{return {ok:false,status:403,error:'Current native source authority unavailable'};}
  }
  async function authorize(headers:Headers):Promise<Auth>{
    let sessionId:string|undefined;
    try{
      const matches=(headers.get('cookie')??'').split(';').map(x=>x.trim()).filter(x=>x.startsWith(NATIVE_COOKIE+'='));
      if(matches.length!==1)return {ok:false,status:401,error:'Native session required'};
      sessionId=decodeURIComponent(matches[0]!.slice(NATIVE_COOKIE.length+1));
      const session=sessions.get(sessionId);const now=deps.clock();prune(now);
      if(!session||now>=session.expiresAt)return {ok:false,status:401,error:'Native session expired'};
      const state=await current();
      if(state.now>=session.expiresAt||state.config.actor_id!==session.actorId||state.tokenFingerprint!==session.tokenFingerprint
        ||state.settingsFingerprint!==session.settingsFingerprint){sessions.delete(sessionId);return {ok:false,status:403,error:'Native session withdrawn'};}
      return {ok:true,actorId:session.actorId,sessionId};
    }catch{if(sessionId)sessions.delete(sessionId);return {ok:false,status:403,error:'Current native source authority unavailable'};}
  }
  return {create,authorize,destroy:(id:string)=>sessions.delete(id)};
}

const owned=nativeSessions({token:pilotToken,actors:pilotActors,settings:loadSettings,identity:verifyNativeIdentity,current:currentNativeJob,clock:()=>Math.floor(Date.now()/1000)});
export const createNativeSession=owned.create;
export const authorizeNativeRequest=owned.authorize;
export const destroyNativeSession=owned.destroy;
export const nativeCookie=(id:string)=>`${NATIVE_COOKIE}=${encodeURIComponent(id)}; Path=${NATIVE_COOKIE_PATH}; HttpOnly; Secure; SameSite=Strict; Max-Age=${TTL_SECONDS}`;
export const clearNativeCookie=()=>`${NATIVE_COOKIE}=; Path=${NATIVE_COOKIE_PATH}; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;
