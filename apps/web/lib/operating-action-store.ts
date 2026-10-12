import { randomUUID } from 'node:crypto';
import { operatingClient,operatingAuthority } from './operating-model-store';
import { pilotWorkspaceId } from './oracle2-store';
export async function createEventAction(actorId:string,processId:string,input:Record<string,unknown>) {
  const sql=operatingClient(),workspace=pilotWorkspaceId(),runId=randomUUID();
  try {await sql.begin(async tx=>{
    if(process.env.ORACLE2_OPERATING_SYNTHETIC!=='1')throw new Error('Private event admission unavailable');
    const [release]=await tx`SELECT m.payload,m.content_hash FROM oracle2.operating_release_selectors s JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id WHERE s.workspace_id=${workspace}::uuid`;
    if(!release||release.payload.acceptance_state!=='synthetic')throw new Error('Release unavailable');
    const mapping=input.mapping as Record<string,unknown>;
    const refs=input.source_refs as Array<Record<string,unknown>>;
    if(!mapping||mapping.process_id!==processId||typeof mapping.scope!=='string'||!Array.isArray(refs)||refs.length!==1||refs[0]?.workspace_id!==workspace)throw new Error('Exact export mapping required');
    for(const scope of [`event-import:${mapping.scope}`,...release.payload.source_refs.map((r:{source_id:string})=>`source-read:${r.source_id}`),`source-read:${refs[0]?.source_id}`]){
      const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,scope]);if(!rows[0]?.ok)throw new Error('Current authority denied');
    }
    const payload={...input,process_id:processId};
    await tx`INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status) VALUES(${runId}::uuid,${workspace}::uuid,${actorId}::uuid,'event_import',${sql.json(payload)},${release.payload.release_id}::uuid,${release.content_hash},'pending')`;
  });return {runId,workspaceId:workspace};}finally{await sql.end({timeout:1});}
}
export async function readEventAction(actorId:string,processId:string,runId:string){
  const sql=operatingClient(),workspace=pilotWorkspaceId();
  try{return await sql.begin(async tx=>{
    const [run]=await tx`SELECT a.*,m.payload AS release FROM oracle2.operating_action_runs a JOIN oracle2.operating_release_selectors s ON s.workspace_id=a.workspace_id AND s.release_id=a.release_id JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id AND m.content_hash=a.release_hash WHERE a.run_id=${runId}::uuid AND a.workspace_id=${workspace}::uuid AND a.actor_id=${actorId}::uuid AND a.operation='event_import' AND a.expires_at>now()`;
    if(!run||run.payload.process_id!==processId)throw new Error('Current action unavailable');
    const refs=[...run.release.source_refs,...run.payload.source_refs];
    for(const ref of refs){
      const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,`source-read:${ref.source_id}`]);
      const [source]=await tx`SELECT s.revision,s.status,d.status AS draft_status FROM oracle2.sources s JOIN oracle2.drafts d ON d.workspace_id=s.workspace_id AND d.source_id=s.source_id WHERE s.workspace_id=${workspace}::uuid AND s.source_id=${ref.source_id}::uuid`;
      if(!rows[0]?.ok||!source||source.revision!==ref.revision||source.status==='withdrawn'||source.draft_status!=='confirmed')throw new Error('Current source denied');
    }
    const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,`event-import:${run.payload.mapping.scope}`]);if(!rows[0]?.ok)throw new Error('Current event authority denied');
    return run.status==='completed'?run.result:{state:run.status,runId};
  });}finally{await sql.end({timeout:1});}
}

export async function createFindingAction(actorId:string,findingId:string,input:{action:string;scope:string;note:string}){
 const sql=operatingClient(),workspace=pilotWorkspaceId(),runId=randomUUID();
 try{await sql.begin(async tx=>{
  if(process.env.ORACLE2_OPERATING_SYNTHETIC!=='1'||!['annotate','resolve','supersede','withdraw'].includes(input.action)||!input.scope||!input.note||input.note.length>4000)throw new Error('Review action unavailable');
  const [release]=await tx`SELECT m.payload,m.content_hash FROM oracle2.operating_release_selectors s JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id WHERE s.workspace_id=${workspace}::uuid`;
  if(!release||release.payload.acceptance_state!=='synthetic')throw new Error('Current release unavailable');
  for(const scope of [`finding-review:${input.scope}`,...release.payload.source_refs.map((r:{source_id:string})=>`source-read:${r.source_id}`)]){const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,scope]);if(!rows[0]?.ok)throw new Error('Current review authority denied');}
  await tx`INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status) VALUES(${runId}::uuid,${workspace}::uuid,${actorId}::uuid,'finding_review',${sql.json({...input,finding_id:findingId})},${release.payload.release_id}::uuid,${release.content_hash},'pending')`;
 });return {runId,workspaceId:workspace};}finally{await sql.end({timeout:1});}
}

export async function readFindingAction(actorId:string,findingId:string,runId:string){
 const sql=operatingClient(),workspace=pilotWorkspaceId();
 try{return await sql.begin(async tx=>{
  const [run]=await tx`SELECT a.*,m.payload AS release FROM oracle2.operating_action_runs a JOIN oracle2.operating_release_selectors s ON s.workspace_id=a.workspace_id AND s.release_id=a.release_id JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id AND m.content_hash=a.release_hash WHERE a.run_id=${runId}::uuid AND a.workspace_id=${workspace}::uuid AND a.actor_id=${actorId}::uuid AND a.operation='finding_review' AND a.expires_at>now()`;
  if(!run||run.payload.finding_id!==findingId)throw new Error('Current review unavailable');
  for(const ref of run.release.source_refs){
   const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,`source-read:${ref.source_id}`]);
   const [source]=await tx`SELECT s.revision,s.status,d.status AS draft_status FROM oracle2.sources s JOIN oracle2.drafts d ON d.workspace_id=s.workspace_id AND d.source_id=s.source_id WHERE s.workspace_id=${workspace}::uuid AND s.source_id=${ref.source_id}::uuid`;
   if(!rows[0]?.ok||!source||source.revision!==ref.revision||source.status==='withdrawn'||source.draft_status!=='confirmed')throw new Error('Current source denied');
  }
  const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,`finding-review:${run.payload.scope}`]);if(!rows[0]?.ok)throw new Error('Current review authority denied');
  return run.status==='completed'?run.result:{state:run.status,runId};
 });}finally{await sql.end({timeout:1});}
}
