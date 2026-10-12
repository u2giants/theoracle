import { NextResponse,type NextRequest } from 'next/server';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import { createEventAction,readEventAction } from '@/lib/operating-action-store';
export const dynamic='force-dynamic';
const limit=4*1024*1024;
export async function POST(req:NextRequest,{params}:{params:Promise<{id:string}>}){
 const auth=await authorizePilotRequest(req.headers);if(!auth.ok)return NextResponse.json({error:auth.error},{status:auth.status});
 try{
  if(!req.body)return NextResponse.json({error:'Export body required'},{status:400});
  const reader=req.body.getReader();const chunks:Uint8Array[]=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>limit){await reader.cancel();return NextResponse.json({error:'This upload exceeds the web transport limit'},{status:413});}chunks.push(value);}
  const input=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if(!input||typeof input.raw_export_base64!=='string'||!['csv','xes'].includes(input.format)||typeof input.window_start!=='string'||typeof input.window_end!=='string')return NextResponse.json({error:'Exact export, mapping and window required'},{status:400});
  const {id}=await params;const job=await createEventAction(auth.actorId,id,input);
  const key=process.env.ORACLE2_OPERATING_TRIGGER_SECRET_KEY;
  if(key){const {tasks}=await import('@trigger.dev/sdk/v3');await tasks.trigger('oracle2-operating-event-import',job,undefined,{clientConfig:{accessToken:key}});}
  return NextResponse.json({state:'pending',runId:job.runId},{status:202});
 }catch{return NextResponse.json({error:'Event import unavailable or denied'},{status:409});}
}
export async function GET(req:NextRequest,{params}:{params:Promise<{id:string}>}){
 const auth=await authorizePilotRequest(req.headers);if(!auth.ok)return NextResponse.json({error:auth.error},{status:auth.status});
 try{const {id}=await params;const runId=req.nextUrl.searchParams.get('runId');if(!runId||! /^[0-9a-f-]{36}$/i.test(runId))return NextResponse.json({error:'Opaque import identity required'},{status:400});return NextResponse.json(await readEventAction(auth.actorId,id,runId));}
 catch{return NextResponse.json({error:'Current event import unavailable'},{status:409});}
}
