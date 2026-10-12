import { NextResponse, type NextRequest } from 'next/server';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import { createView,readView } from '@/lib/operating-model-store';
export const dynamic='force-dynamic';
export async function view(req:NextRequest,processId?:string){
  const auth=await authorizePilotRequest(req.headers);
  if(!auth.ok)return NextResponse.json({error:auth.error},{status:auth.status});
  try{
    const pageText=req.nextUrl.searchParams.get('page')??'0';
    if(!/^(0|[1-9][0-9]{0,4})$/.test(pageText))return NextResponse.json({error:'Invalid overview page'},{status:400});
    const page=Number(pageText);
    if(processId&&page)return NextResponse.json({error:'Process views cannot be paged'},{status:400});
    const runId=req.nextUrl.searchParams.get('runId');
    if(runId){if(!/^[0-9a-f-]{36}$/i.test(runId))return NextResponse.json({error:'Invalid view'},{status:400});return NextResponse.json(await readView(auth.actorId,runId,{processId,page,connected:req.nextUrl.searchParams.get('connected')==='1'}));}
    const job=await createView(auth.actorId,processId,page,req.nextUrl.searchParams.get('connected')==='1');
    const key=process.env.ORACLE2_OPERATING_TRIGGER_SECRET_KEY;
    if(!key&&process.env.ORACLE2_OPERATING_SYNTHETIC!=='1')return NextResponse.json({error:'Dedicated view worker unavailable'},{status:503});
    if(key){const {tasks}=await import('@trigger.dev/sdk/v3');await tasks.trigger('oracle2-operating-model-view',job,undefined,{clientConfig:{accessToken:key}});}
    return NextResponse.json({state:'pending',runId:job.runId},{status:202});
  }catch{return NextResponse.json({error:'Current operating model is unavailable'},{status:409});}
}
export async function GET(req:NextRequest){return view(req);}
