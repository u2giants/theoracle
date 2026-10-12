"""Worker bundle adapter; arguments contain opaque run/workspace IDs only."""
import asyncio,json,os,sys
from uuid import UUID
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from oracle_brain.operating_model.runtime import run_view,run_event,SyntheticEmbedding
from oracle_brain.operating_model.artifact_storage import FileBlobStore
def main():
    # This command exposes no private text to stdout or task arguments.
    identifiers=json.loads(sys.argv[1]);run_id=UUID(identifiers['runId']);workspace_id=UUID(identifiers['workspaceId'])
    if os.getenv('ORACLE2_OPERATING_SYNTHETIC')!='1' or os.getenv('ORACLE2_ENVIRONMENT')!='synthetic':
        raise PermissionError('hosted worker requires its independently admitted transport configuration')
    if any(os.getenv(k) for k in ('SUPABASE_SERVICE_ROLE_KEY','ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL')):
        raise PermissionError('view identity contains forbidden capabilities')
    from urllib.parse import urlparse
    url=os.environ['ORACLE2_DATABASE_URL'];graph=os.environ['ORACLE2_OPERATING_GRAPH_URL']
    if urlparse(url).hostname not in {'127.0.0.1','localhost'} or urlparse(graph).hostname not in {'127.0.0.1','localhost'}:raise PermissionError('invented runtime requires loopback stores')
    operation=identifiers.get('operation','view')
    if operation in {'event_import','finding_review'}:
        run_event(run_id,workspace_id,database_url=url,blobs=FileBlobStore(Path(os.environ['ORACLE2_OPERATING_BLOB_ROOT'])),synthetic=True,operation=operation)
        print(json.dumps({'state':'completed','run_id':str(run_id)}));return
    if operation!='view':raise PermissionError('operation unavailable')
    result=asyncio.run(run_view(run_id,workspace_id,database_url=url,graph_url=graph,blobs=FileBlobStore(Path(os.environ['ORACLE2_OPERATING_BLOB_ROOT'])),embedder=SyntheticEmbedding(),dimensions=8,synthetic=True))
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception:
        print(json.dumps({'state':'denied'}));sys.exit(1)
