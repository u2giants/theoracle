"""Live smoke test over the fixture set (plan §10; never run in CI).

``uv run python -m brain.smoke --live`` ingests the five invented fixtures with
real ScaleDown and OpenRouter calls and prints chunk, mention, edge and
community counts plus the token cost. From step 4 on it runs before every
step's PR and the counts go into the PR body.

Edges come from the step 5 relations stage; from step 7 the projection prints
the grouped graph counts, from step 8 the community counts and reports, and
from step 9 one local and one global answer over the fixture question.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from brain.answer.answer import answer_question
from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_and_store
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph.communities import run_communities
from brain.graph.project import run_project
from brain.migrate import migrate
from brain.read.chunk import Chunk
from brain.read.detect import detect_kind
from brain.read.pipeline import read_chunks
from brain.resolve.resolve import run_resolve

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SMOKE_TITLE_PREFIX = "[smoke] "
SMOKE_QUESTION = "Where does licensing approval stall and why?"

# The transcript fixture is a .txt of "Speaker: text" lines, which the intake
# API would receive through POST /sources/transcript; detect_kind() alone would
# call it plain text.
FIXTURE_KINDS = {"teams-approval-2026-03-14.txt": "transcript"}


def _clear_prior_runs(digests: set[str]) -> None:
    """Drop stale smoke data so fixture sha256 values can be reused.

    Sources whose bytes match the current fixture set are kept so a rerun
    resumes over them instead of re-ingesting. Community reports and open
    questions are whole-corpus rows (no FK to source), so they are cleared
    only when no fixture source is preserved; a resumed pass lets
    ``run_communities`` reuse the rows that are already there.
    """
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM cmap.source WHERE title LIKE %s "
            "AND (sha256 IS NULL OR NOT (sha256 = ANY(%s)))",
            (SMOKE_TITLE_PREFIX + "%", list(digests)),
        )
        # Entities left with no mentions belonged to earlier smoke runs.
        conn.execute(
            "DELETE FROM cmap.entity e WHERE NOT EXISTS "
            "(SELECT 1 FROM cmap.mention m WHERE m.entity_id = e.id)"
        )
        remaining = conn.execute(
            "SELECT count(*) FROM cmap.source WHERE title LIKE %s",
            (SMOKE_TITLE_PREFIX + "%",),
        ).fetchone()[0]
        if remaining == 0:
            conn.execute("DELETE FROM cmap.community")
            conn.execute("DELETE FROM cmap.open_question")
        conn.commit()


def _existing_source(filename: str, digest: str) -> str | None:
    """Return the id of a preserved smoke source, or None when it is new."""
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id FROM cmap.source WHERE title = %s AND sha256 = %s",
            (SMOKE_TITLE_PREFIX + filename, digest),
        ).fetchone()
    return str(row[0]) if row else None


def _unembedded_chunks(source_id: str) -> list[tuple[str, str]]:
    """``(chunk_id, text)`` pairs of one source still missing embeddings."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, text FROM cmap.chunk "
            "WHERE source_id = %s AND embedding IS NULL ORDER BY ordinal",
            (source_id,),
        ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _insert_source(filename: str, kind: str, data: bytes) -> str:
    """Insert one smoke source row and return its id."""
    digest = hashlib.sha256(data).hexdigest()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.source "
            "(kind, title, original_filename, storage_path, sha256, bytes) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (
                kind,
                SMOKE_TITLE_PREFIX + filename,
                filename,
                f"smoke/local/{filename}",
                digest,
                len(data),
            ),
        ).fetchone()
        conn.commit()
    return str(row[0])


def _insert_chunks(
    source_id: str,
    chunks: list[Chunk],
) -> list[tuple[str, str]]:
    """Insert one source's chunks and return ``(chunk_id, text)`` pairs."""
    pool = get_pool()
    pairs: list[tuple[str, str]] = []
    with pool.connection() as conn:
        for ordinal, chunk in enumerate(chunks):
            row = conn.execute(
                "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    source_id,
                    ordinal,
                    Json(chunk.locator),
                    chunk.text,
                    chunk.token_count,
                ),
            ).fetchone()
            pairs.append((str(row[0]), chunk.text))
        conn.commit()
    return pairs


def _run_job(kind: str, handler: Any, source_id: str) -> dict[str, Any]:
    """Run one real stage handler as a job row and return its usage."""
    pool = get_pool()
    with pool.connection() as conn:
        # The previous stage queues this one; the smoke test runs it inline.
        conn.execute(
            "DELETE FROM cmap.job WHERE kind = %s AND state = 'queued' "
            "AND payload->>'source_id' = %s",
            (kind, source_id),
        )
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload, state) "
            "VALUES (%s, %s, 'running') RETURNING id",
            (kind, Json({"source_id": source_id})),
        ).fetchone()
        job_id = str(row[0])
        conn.commit()
    try:
        handler({"id": job_id, "payload": {"source_id": source_id}})
    except Exception as exc:
        with pool.connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET state = 'failed', error = %s WHERE id = %s",
                (str(exc)[:2000], job_id),
            )
            conn.commit()
        raise
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT payload FROM cmap.job WHERE id = %s",
            (job_id,),
        ).fetchone()
        conn.execute(
            "UPDATE cmap.job SET state = 'done', finished_at = now() WHERE id = %s",
            (job_id,),
        )
        conn.commit()
    payload = row[0] if row else {}
    if not isinstance(payload, dict):
        payload = {}
    usage = payload.get("usage")
    return usage if isinstance(usage, dict) else {}


def _counts(source_id: str) -> dict[str, Any]:
    """Return chunk, mention and extraction counts for one smoke source."""
    pool = get_pool()
    with pool.connection() as conn:
        chunks = conn.execute(
            "SELECT count(*) FROM cmap.chunk WHERE source_id = %s",
            (source_id,),
        ).fetchone()[0]
        mentions = conn.execute(
            "SELECT m.entity_type, count(*) FROM cmap.mention m "
            "JOIN cmap.chunk c ON c.id = m.chunk_id "
            "WHERE c.source_id = %s GROUP BY m.entity_type ORDER BY m.entity_type",
            (source_id,),
        ).fetchall()
        models = conn.execute(
            "SELECT e.model, count(*) FROM cmap.extraction e "
            "JOIN cmap.chunk c ON c.id = e.chunk_id "
            "WHERE c.source_id = %s GROUP BY e.model ORDER BY e.model",
            (source_id,),
        ).fetchall()
        relations = conn.execute(
            "SELECT r.rel_type, count(*) FROM cmap.relation r "
            "JOIN cmap.chunk c ON c.id = r.chunk_id "
            "WHERE c.source_id = %s GROUP BY r.rel_type ORDER BY count(*) DESC",
            (source_id,),
        ).fetchall()
        kinds = conn.execute(
            "SELECT passage_kind, count(*) FROM cmap.chunk "
            "WHERE source_id = %s GROUP BY passage_kind ORDER BY count(*) DESC",
            (source_id,),
        ).fetchall()
    return {
        "chunks": int(chunks),
        "mentions": {str(kind): int(count) for kind, count in mentions},
        "extraction_models": {str(model): int(count) for model, count in models},
        "relations": {str(kind): int(count) for kind, count in relations},
        "passage_kinds": {str(kind or "none"): int(count) for kind, count in kinds},
    }


def _print_entities() -> None:
    """Print entity totals and the multi-source entities the map will join on."""
    with get_pool().connection() as conn:
        total = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE source_count >= 2) FROM cmap.entity"
        ).fetchone()
        joined = conn.execute(
            "SELECT entity_type, canonical_name, mention_count, source_count FROM cmap.entity "
            "WHERE source_count >= 2 ORDER BY source_count DESC, mention_count DESC LIMIT 25"
        ).fetchall()
    print(f"ENTITIES total={total[0]} multi_source={total[1]}")
    for entity_type, name, mentions, sources in joined:
        print(f"    {entity_type}: {name} mentions={mentions} sources={sources}")


def _merge(target: dict[str, int], addition: dict[str, Any]) -> None:
    """Merge integer counters from ``addition`` into ``target``."""
    for key, value in addition.items():
        if isinstance(value, int):
            target[key] = target.get(key, 0) + value


def _require(settings: Settings) -> list[str]:
    """Return the names of env vars the live smoke test still needs."""
    missing = []
    if settings.database_url is None:
        missing.append("DATABASE_URL")
    if settings.openrouter_api_key is None:
        missing.append("OPENROUTER_API_KEY")
    if settings.brain_frontier_model is None:
        missing.append("BRAIN_FRONTIER_MODEL")
    if settings.brain_vision_model is None:
        missing.append("BRAIN_VISION_MODEL")
    if settings.brain_embed_model is None:
        missing.append("BRAIN_EMBED_MODEL")
    return missing


def main() -> int:
    """Run the live smoke pass over the fixture set."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="actually call ScaleDown and OpenRouter (required; this test is never CI)",
    )
    args = parser.parse_args()
    if not args.live:
        print("brain.smoke is a live model test; rerun with --live", file=sys.stderr)
        return 2
    settings = get_settings()
    missing = _require(settings)
    if missing:
        print(f"missing env: {', '.join(missing)}", file=sys.stderr)
        return 2
    if settings.brain_scaledown_enabled and settings.scaledown_api_key:
        path = "scaledown classify/extract"
    else:
        path = "frontier fallback (BRAIN_SCALEDOWN_ENABLED=false or no key)"
    print(f"extraction path: {path}")
    print(f"frontier model: {settings.brain_frontier_model}")
    migrate()
    digests = {
        fixture.name: hashlib.sha256(fixture.read_bytes()).hexdigest()
        for fixture in sorted(FIXTURES_DIR.iterdir())
        if fixture.is_file() and fixture.name != "build_fixtures.py"
    }
    _clear_prior_runs(set(digests.values()))
    usage_total: dict[str, int] = {}
    grand = {"chunks": 0, "mentions": 0, "edges": 0, "communities": 0}
    for fixture in sorted(FIXTURES_DIR.iterdir()):
        if not fixture.is_file() or fixture.name == "build_fixtures.py":
            continue
        data = fixture.read_bytes()
        kind = FIXTURE_KINDS.get(fixture.name) or detect_kind(fixture.name, data[:4096])
        read_usage: dict[str, int] = {}
        existing_id = _existing_source(fixture.name, digests[fixture.name])
        if existing_id is not None:
            source_id = existing_id
            pairs = _unembedded_chunks(source_id)
            if pairs:
                embed_and_store(pairs, usage=read_usage)
        else:
            chunks = read_chunks(kind, data, read_usage)
            source_id = _insert_source(fixture.name, kind, data)
            pairs = _insert_chunks(source_id, chunks)
            embed_and_store(pairs, usage=read_usage)
        flat_usage = _run_job("classify_extract", handle_classify_extract, source_id)
        relations_usage = _run_job("relations", handle_relations, source_id)
        _merge(usage_total, read_usage)
        _merge(usage_total, flat_usage)
        _merge(usage_total, relations_usage)
        counts = _counts(source_id)
        grand["chunks"] += counts["chunks"]
        mention_total = sum(counts["mentions"].values())
        grand["mentions"] += mention_total
        edge_total = sum(counts["relations"].values())
        grand["edges"] += edge_total
        tokens = read_usage.get("embedding_tokens", 0)
        print(
            f"- {fixture.name} [{kind}]: chunks={counts['chunks']} "
            f"mentions={mention_total} {counts['mentions']} "
            f"passage_kinds={counts['passage_kinds']}"
        )
        print(f"    relations={edge_total} {counts['relations']}")
        print(f"    extraction={counts['extraction_models']} embed_tokens={tokens}")
    print(
        f"TOTAL chunks={grand['chunks']} mentions={grand['mentions']} "
        f"edges={grand['edges']} communities={grand['communities']} "
        f"(source-level; grouped graph and community counts print below)"
    )
    resolve_stats = run_resolve(settings)
    _merge(
        usage_total,
        {k: v for k, v in resolve_stats.items() if k.startswith("frontier")},
    )
    print(f"resolve: {resolve_stats}")
    _print_entities()
    project_stats = run_project(settings)
    print(f"project: {project_stats}")
    community_stats = run_communities(settings)
    print(f"communities: {community_stats}")
    for mode in ("local", "global"):
        answer_usage: dict[str, int] = {}
        result = answer_question(SMOKE_QUESTION, mode, [], settings, answer_usage)
        _merge(usage_total, answer_usage)
        cited = {item.get("source_id") for item in result["citations"]}
        print(
            f"answer {mode}: mode_used={result['mode_used']} "
            f"citations={len(result['citations'])} sources={len(cited)} "
            f"unknowns={len(result.get('unknowns') or [])}"
        )
    print(f"usage: {usage_total}")
    if grand["chunks"]:
        print(
            "per chunk: "
            f"frontier_tokens={usage_total.get('frontier_tokens', 0) / grand['chunks']:.0f} "
            f"scaledown_calls={(usage_total.get('scaledown_classify_calls', 0) + usage_total.get('scaledown_extract_calls', 0)) / grand['chunks']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
