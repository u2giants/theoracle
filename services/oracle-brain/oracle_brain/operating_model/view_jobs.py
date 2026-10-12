"""Opaque documentary jobs; immutable release and current per-source authority govern output."""
import json
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from .cutover import selected
from .contracts import digest,canonical_bytes
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
    from oracle_brain.knowledge.authority import _has_authority_conn
    current=ledger.read(workspace,manifest.artifact_id,manifest.artifact_version)
    scopes={f["scope"] for f in current.get("findings",()) }
    with psycopg.connect(database_url) as conn:
        reviewer_scopes=frozenset(scope for scope in scopes if _has_authority_conn(conn,workspace,actor,"finding-review:"+scope))
    retrieval=Retrieval(ledger,projection)
    pack=await retrieval.retrieve(workspace_id=workspace,artifact_id=manifest.artifact_id,version=manifest.artifact_version,
                                  plan=QueryPlan.model_validate_json(json.dumps(query)),reviewer_scopes=reviewer_scopes)
    retrieval.recheck_before_serve(workspace,manifest.artifact_id,manifest.artifact_version,pack)
    if selected(database_url,workspace)!=manifest:raise PermissionError('view inputs changed before persistence')
    # UI transport is a view, never a second ledger or an accepted company claim.
    pack['processes']=[{**p,'workflow_ids':[w['workflow_id'] for w in pack.get('workflows',[]) if w['process_id']==p['process_id']]} for p in pack.get('processes',[])]
    pack['reviewable_scopes']=sorted(reviewer_scopes)
    pack['finding_review_events']=ledger.review_events(workspace,manifest.artifact_id,manifest.artifact_version)
    pack['analysis']={'state':'unavailable','actual_data_acceptance':manifest.actual_event_acceptance}
    if synthetic and manifest.report_refs:
        from .report_store import serve_report
        previews=[]
        for reference in manifest.report_refs:
            content=ledger.read(workspace,reference.artifact_id,reference.version)
            if digest(content)!=reference.content_hash:raise ValueError('synthetic preview seal changed')
            report=serve_report(ledger,workspace,reference.artifact_id,reference.version)
            if report.model_artifact_hash!=manifest.artifact_content_hash or report.actual_data_acceptance!='synthetic':raise PermissionError('preview does not bind current invented release')
            previews.append(report.model_dump(mode='json'))
        pack['report_previews']=previews
        measured=next((r for r in previews if r['variant']=='measured'),None)
        if measured:
            values=measured['measurements']
            pack['analysis']={'state':'ready','actual_data_acceptance':'synthetic','measurements':{'Completed cases':values['cases']['retained_completed'],'Median elapsed seconds':values['elapsed_seconds']['median'] or 'unavailable','90th percentile elapsed seconds':values['elapsed_seconds']['p90_nearest_rank'] or 'unavailable'}}
    if selected(database_url,workspace)!=manifest:raise PermissionError('release changed before view persistence')
    retrieval.recheck_before_serve(workspace,manifest.artifact_id,manifest.artifact_version,pack)
    if len(canonical_bytes(pack))>QueryPlan.model_validate_json(json.dumps(query)).max_bytes:
        pack={"state":"coverage_incomplete","artifact_hash":pack["artifact_hash"],"reason":"Complete documentary and review evidence exceeds this view budget."}
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE oracle2.operating_view_runs SET status='completed',pack=%s WHERE run_id=%s AND actor_id=%s AND expires_at>now()",(Jsonb(pack),run_id,actor))
    return {'state':'completed','run_id':str(run_id)}
