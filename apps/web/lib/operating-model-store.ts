import postgres from 'postgres';
import { randomUUID } from 'node:crypto';
import { pilotWorkspaceId } from './oracle2-store';

export function operatingClient() {
  const url = process.env.ORACLE2_DATABASE_URL;
  if (!url) throw new Error('Operating model store unavailable');
  return postgres(url, { max: 1, connect_timeout: 5 });
}
export const operatingAuthority = `WITH RECURSIVE lineage AS (
 SELECT a.appointment_id AS start_id,a.appointment_id,a.parent_id,a.revoked_at,a.expires_at,a.scope,a.workspace_id,1 AS depth
 FROM oracle2.appointments a WHERE a.workspace_id=$1 AND a.actor_id=$2 AND a.scope IN ($3,'root')
 UNION ALL SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,l.depth+1
 FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id WHERE l.depth<16 AND p.workspace_id=l.workspace_id
) SELECT EXISTS(SELECT 1 FROM lineage GROUP BY start_id HAVING bool_and(revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())) AND bool_or(scope='root' AND parent_id IS NULL)) AS ok`;

export async function createView(actorId: string, processId?: string, page=0, connected=false) {
  const sql = operatingClient(); const workspace = pilotWorkspaceId(); const runId = randomUUID();
  try {
    await sql.begin(async tx => {
      const [release] = await tx`SELECT m.payload,m.content_hash FROM oracle2.operating_release_selectors s JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id WHERE s.workspace_id=${workspace}::uuid`;
      if (!release) throw new Error('No admitted operating model');
      const manifest = release.payload;
      if (manifest.acceptance_state !== 'admitted_hosted' && !(manifest.acceptance_state === 'synthetic' && process.env.ORACLE2_OPERATING_SYNTHETIC === '1')) throw new Error('Release is not admitted');
      for (const ref of manifest.source_refs) {
        const rows = await tx.unsafe(operatingAuthority,[workspace,actorId,`source-read:${ref.source_id}`]);
        if (!rows[0]?.ok) throw new Error('Source access denied');
      }
      const plan = {schema_version:1,view:processId?(connected?'connected_interfaces':'process_local'):'company_overview',process_ids:processId?[processId]:[],question:'Show the reported operating model and its unresolved controls.',max_bytes:131072,page,page_size:25};
      await tx`INSERT INTO oracle2.operating_view_runs(run_id,workspace_id,actor_id,query_plan,release_id,release_hash,status,source_refs) VALUES(${runId}::uuid,${workspace}::uuid,${actorId}::uuid,${sql.json(plan)},${manifest.release_id}::uuid,${release.content_hash},'pending',${sql.json(manifest.source_refs)})`;
    });
    return { runId, workspaceId: workspace };
  } finally { await sql.end({timeout:1}); }
}

export async function readView(actorId:string,runId:string,expected?:{processId?:string;page:number;connected:boolean}) {
  const sql=operatingClient();const workspace=pilotWorkspaceId();
  try {
    return await sql.begin(async tx=>{
      const [run]=await tx`SELECT r.*,m.payload AS release FROM oracle2.operating_view_runs r JOIN oracle2.operating_release_selectors s ON s.workspace_id=r.workspace_id AND s.release_id=r.release_id JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id AND m.content_hash=r.release_hash WHERE r.run_id=${runId}::uuid AND r.workspace_id=${workspace}::uuid AND r.actor_id=${actorId}::uuid AND r.expires_at>now()`;
      if(!run)throw new Error('View expired or changed');
      if(expected){
        const view=expected.processId?(expected.connected?'connected_interfaces':'process_local'):'company_overview';
        const ids=expected.processId?[expected.processId]:[];
        if(run.query_plan.view!==view || run.query_plan.page!==expected.page || JSON.stringify(run.query_plan.process_ids)!==JSON.stringify(ids))throw new Error('View does not match the requested scope');
      }
      const [changed]=await tx`SELECT COALESCE(max(sequence),0) AS sequence FROM oracle2.operating_model_change_log WHERE workspace_id=${workspace}::uuid`;
      if(!changed || Number(changed.sequence)!==run.release.ledger_watermark)throw new Error('Source changes require replay');
      const invalidated=await tx`SELECT 1 FROM oracle2.artifact_invalidations WHERE workspace_id=${workspace}::uuid AND artifact_id=${run.release.artifact_id}::uuid AND version=${run.release.artifact_version} LIMIT 1`;
      const [artifact]=await tx`SELECT content_hash,state FROM oracle2.artifact_manifests WHERE workspace_id=${workspace}::uuid AND artifact_id=${run.release.artifact_id}::uuid AND version=${run.release.artifact_version}`;
      if(invalidated.length || !artifact || artifact.state!=='ready' || artifact.content_hash!==run.release.artifact_content_hash)throw new Error('Artifact invalidated or changed');
      for(const ref of run.source_refs){
        const rows=await tx.unsafe(operatingAuthority,[workspace,actorId,`source-read:${ref.source_id}`]);
        const [source]=await tx`SELECT s.revision,s.status,d.status AS draft_status FROM oracle2.sources s JOIN oracle2.drafts d ON d.source_id=s.source_id AND d.workspace_id=s.workspace_id WHERE s.workspace_id=${workspace}::uuid AND s.source_id=${ref.source_id}::uuid`;
        if(!rows[0]?.ok||!source||source.revision!==ref.revision||source.status==='withdrawn'||source.draft_status!=='confirmed')throw new Error('Current source access denied');
      }
      return run.status==='completed'?run.pack:{state:run.status,runId};
    });
  } finally {await sql.end({timeout:1});}
}
