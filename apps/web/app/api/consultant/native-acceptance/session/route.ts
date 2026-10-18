import {nativeTriggerV2Enabled,createTriggerNativeV2Session,authorizeTriggerNativeV2Request,destroyTriggerNativeV2Session} from '@/lib/native-trigger-v2';
import {nativeTriggerEnabled,createTriggerNativeSession,authorizeTriggerNativeRequest,destroyTriggerNativeSession} from '@/lib/native-trigger';
import { nativeRequestOrigin } from '@/lib/native-acceptance';
import { createNativeSession, authorizeNativeRequest, destroyNativeSession, nativeCookie, clearNativeCookie } from '@/lib/native-browser-auth';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const denied=(status:number)=>Response.json({error:'Hosted invented-data sign-in unavailable'},{status,headers:{'Cache-Control':'no-store'}});
const sameOrigin=nativeRequestOrigin;
export async function POST(req:Request){
  try{
    if(!sameOrigin(req)||req.headers.get('content-type')!=='application/json'||req.headers.get('transfer-encoding'))return denied(400);
    const length=req.headers.get('content-length');if(length&&(!/^\d{1,5}$/.test(length)||Number(length)>8192))return denied(400);
    if(!req.body)return denied(400);
    const reader=req.body.getReader();const chunks:Uint8Array[]=[];let size=0;
    try{while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>8192){await reader.cancel();return denied(400);}chunks.push(part.value);}}finally{reader.releaseLock();}
    const raw=Buffer.concat(chunks).toString('utf8');
    const body:unknown=JSON.parse(raw);
    if(!body||typeof body!=='object'||Array.isArray(body)||Object.keys(body).join('|')!=='token'||typeof (body as {token:unknown}).token!=='string')return denied(400);
    const auth=await (nativeTriggerV2Enabled()?createTriggerNativeV2Session:nativeTriggerEnabled()?createTriggerNativeSession:createNativeSession)((body as {token:string}).token);if(!auth.ok)return denied(auth.status);
    return Response.json({actorId:auth.actorId},{headers:{'Cache-Control':'no-store','Set-Cookie':nativeCookie(auth.sessionId)}});
  }catch{return denied(403);}
}
export async function DELETE(req:Request){
  if(!sameOrigin(req))return denied(400);
  const auth=await (nativeTriggerV2Enabled()?authorizeTriggerNativeV2Request:nativeTriggerEnabled()?authorizeTriggerNativeRequest:authorizeNativeRequest)(req.headers);if(auth.ok){if(nativeTriggerV2Enabled())await destroyTriggerNativeV2Session(auth.sessionId);else if(nativeTriggerEnabled())await destroyTriggerNativeSession(auth.sessionId);else destroyNativeSession(auth.sessionId);}
  return Response.json({ok:true},{headers:{'Cache-Control':'no-store','Set-Cookie':clearNativeCookie()}});
}
