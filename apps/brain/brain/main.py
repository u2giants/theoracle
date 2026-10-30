"""FastAPI app for the brain service."""

from __future__ import annotations

from falkordb import FalkorDB
from fastapi import FastAPI

from brain.api.answer import router as answer_router
from brain.api.eval import router as eval_router
from brain.api.map import router as map_router
from brain.api.sources import router as sources_router
from brain.config import Settings, get_settings
from brain.db import check_database

app = FastAPI(title="brain")
app.include_router(sources_router)
app.include_router(answer_router)
app.include_router(map_router)
app.include_router(eval_router)


def check_graph(settings: Settings | None = None) -> bool:
    """Return True when FalkorDB answers a ping."""
    cfg = settings if settings is not None else get_settings()
    try:
        client = FalkorDB.from_url(cfg.falkordb_url)
        client.execute_command("PING")
    except Exception:
        return False
    return True


@app.get("/health")
def health() -> dict[str, bool]:
    """Report process and dependency reachability.

    ``ok`` and ``db`` track the required Postgres store; ``graph`` is
    advisory because FalkorDB is rebuildable from Postgres.
    """
    settings = get_settings()
    db_ok = check_database(settings)
    graph_ok = check_graph(settings)
    body = {
        "ok": db_ok,
        "db": db_ok,
        "graph": graph_ok,
    }
    return body
