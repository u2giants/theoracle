"""Worker runtime boundary. Report dispatch remains paused; synthetic views are isolated."""
import asyncio
from pathlib import Path
from uuid import UUID
from graphrag_sdk.core.providers import LLMInterface,Embedder
from .authority_adapter import PostgresSources
from .artifact_storage import FileBlobStore
from .ledger import Ledger
from .cutover import selected
from .sdk_projection import SDKProjection
from .view_jobs import execute_view

class NoGeneration(LLMInterface):
    def __init__(self):super().__init__('disabled-generation',max_concurrency=1)
    def invoke(self,prompt,**kwargs):raise PermissionError('view cannot generate company answers or re-extract sources')

class SyntheticEmbedding(Embedder):
    model_name='invented-fixed-8'
    def embed_query(self,text,**kwargs):return [1.0]+[0.0]*7

async def run_view(run_id:UUID,workspace_id:UUID,*,database_url,graph_url,blobs,embedder,dimensions,synthetic:bool):
    import psycopg
    with psycopg.connect(database_url) as conn:
        row=conn.execute('SELECT actor_id FROM oracle2.operating_view_runs WHERE run_id=%s AND workspace_id=%s AND expires_at>now()',(run_id,workspace_id)).fetchone()
    if row is None:raise PermissionError('opaque view job unavailable')
    authority=PostgresSources(database_url)
    ledger=Ledger(database_url,blobs,principal=row[0],can_read=authority.can_read,current_source=authority.current)
    manifest=selected(database_url,workspace_id)
    if manifest.acceptance_state=='synthetic' and not synthetic:raise PermissionError('synthetic projection cannot enter hosted runtime')
    projection=SDKProjection(graph_url,workspace_id=workspace_id,artifact_id=manifest.artifact_id,artifact_version=manifest.artifact_version,
                             generation=manifest.graph_generation,llm=NoGeneration(),embedder=embedder,dimensions=dimensions)
    try:return await execute_view(database_url,run_id,ledger=ledger,projection=projection,synthetic=synthetic)
    finally:await projection.close()


def run_event(run_id,workspace_id,*,database_url,blobs,synthetic,operation="event_import"):
    import psycopg
    from .action_jobs import execute_event,execute_review
    with psycopg.connect(database_url) as conn:
        row=conn.execute('SELECT actor_id FROM oracle2.operating_action_runs WHERE run_id=%s AND workspace_id=%s AND expires_at>now()',(run_id,workspace_id)).fetchone()
    if row is None:raise PermissionError('opaque action unavailable')
    sources=PostgresSources(database_url)
    ledger=Ledger(database_url,blobs,principal=row[0],can_read=sources.can_read,current_source=sources.current)
    execute=execute_event if operation=="event_import" else execute_review
    return execute(database_url,run_id,workspace_id,ledger,synthetic)
