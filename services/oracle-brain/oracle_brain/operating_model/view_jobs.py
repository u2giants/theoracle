"""Opaque documentary jobs; immutable release and current per-source authority govern output."""
import json
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from .cutover import selected
from .contracts import digest
from .retrieval import QueryPlan,Retrieval

async def execute_view(database_url:str,run_id:UUID,*,ledger,projection,synthetic:bool):
    with psycopg.connect(database_url) as conn:
        row=conn.execute('SELECT workspace_id,actor_id,query_plan,release_id,release_hash,status FROM oracle2.operating_view_runs WHERE run_id=%s AND expires_at>now()',(run_id,)).fetchone()
    if row is None:raise PermissionError('view job absent or expired')
    workspace,actor,query,release_id,release_hash,status=row
    if actor!=ledger.principal:raise PermissionError('view actor does not match authoritative ledger identity')
    manifest=selected(database_url,workspace)
    if manifest.release_id!=release_id or manifest.content_hash()!=release_hash:raise PermissionError('view release changed')
    if synthetic!=(manifest.acceptance_state=='synthetic'):raise PermissionError('view environment mismatch')
    if not synthetic and manifest.acceptance_state!='admitted_hosted':raise PermissionError('hosted serving not admitted')
    if projection.graph_name!=manifest.graph_name:raise PermissionError('projection identity mismatch')
    retrieval=Retrieval(ledger,projection)
    pack=await retrieval.retrieve(workspace_id=workspace,artifact_id=manifest.artifact_id,version=manifest.artifact_version,
                                  plan=QueryPlan.model_validate_json(json.dumps(query)))
    retrieval.recheck_before_serve(workspace,manifest.artifact_id,manifest.artifact_version,pack)
    if selected(database_url,workspace)!=manifest:raise PermissionError('view inputs changed before persistence')
    # UI transport is a view, never a second ledger or an accepted company claim.
    pack['processes']=[{**p,'workflow_ids':[w['workflow_id'] for w in pack.get('workflows',[]) if w['process_id']==p['process_id']]} for p in pack.get('processes',[])]
    pack['analysis']={'state':'unavailable','actual_data_acceptance':manifest.actual_event_acceptance}
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE oracle2.operating_view_runs SET status='completed',pack=%s WHERE run_id=%s AND actor_id=%s AND expires_at>now()",(Jsonb(pack),run_id,actor))
    return {'state':'completed','run_id':str(run_id)}
