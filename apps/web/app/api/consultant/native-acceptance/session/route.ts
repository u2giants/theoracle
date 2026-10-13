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
    const auth=await createNativeSession((body as {token:string}).token);if(!auth.ok)return denied(auth.status);
    return Response.json({actorId:auth.actorId},{headers:{'Cache-Control':'no-store','Set-Cookie':nativeCookie(auth.sessionId)}});
  }catch{return denied(403);}
}
export async function DELETE(req:Request){
  if(!sameOrigin(req))return denied(400);
  const auth=await authorizeNativeRequest(req.headers);if(auth.ok)destroyNativeSession(auth.sessionId);
  return Response.json({ok:true},{headers:{'Cache-Control':'no-store','Set-Cookie':clearNativeCookie()}});
}
