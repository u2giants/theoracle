"""Projected fixture map for the step-10 page tests (plan step 10).

``seed_map(db)`` runs the frozen fixtures (Teams transcript, procedure PDF,
flowchart PNG) through flat extraction, relations, resolution, projection and
communities with every model call replayed or faked, so the map has a
licensing community holding Jessica, findings with stances and source chips,
and quotes that land on the transcript. ``tests/test_map_api.py`` uses it, and
the Playwright test seeds its own database by running this file directly::

    DATABASE_URL=... FALKORDB_URL=... uv run python tests/map_seed.py

which prints one JSON line with the ids the browser test needs. No call
leaves the machine.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import (  # noqa: E402
    fake_embeddings,
    fake_relations,
    fake_scaledown,
    fake_vision,
)
from test_flat import PDF_FIXTURE, TRANSCRIPT_FIXTURE, _seed_fixture  # noqa: E402
from test_resolve import _fake as _fake_resolve  # noqa: E402

from brain.config import get_settings  # noqa: E402
from brain.extract.flat import handle_classify_extract  # noqa: E402
from brain.extract.relations import handle_relations  # noqa: E402
from brain.graph.communities import (  # noqa: E402
    SCOPE_L0,
    SCOPE_L1,
    SCOPE_L2,
    run_communities,  # noqa: E402
)
from brain.graph.project import run_project  # noqa: E402
from brain.resolve import resolve as resolve_mod  # noqa: E402
from brain.resolve.resolve import run_resolve  # noqa: E402

FLOWCHART_FIXTURE = "licensing-approval-flowchart.png"
LICENSING_TITLE = "Licensing approval"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
STANCES = ["policy", "practice", "report", "inference"]


class MapReports:
    """Deterministic community reports shaped like the frontier's answers.

    A level-0 community whose context names Jessica, and a level-1 community
    holding such a child, is titled "Licensing approval"; findings cite the
    source ids the context offers.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        self.calls += 1
        prompt = str(messages[-1]["content"])
        sources = list(dict.fromkeys(UUID_RE.findall(prompt)))
        if SCOPE_L1 in prompt:
            licensing = LICENSING_TITLE in prompt
        else:
            licensing = "jessica" in prompt.casefold()
        if SCOPE_L2 in prompt:
            title = "Company overview"
            summary = "Licensing sign-off is the slowest hand-off across departments."
            texts = [
                "Licensing sign-off stalls artwork release",
                "Buyers wait on approvals before raising purchase orders",
            ]
        elif SCOPE_L1 in prompt or SCOPE_L0 in prompt:
            title = LICENSING_TITLE if licensing else f"Area {self.calls}"
            summary = (
                "The approval moves from Design to Licensing and stalls at sign-off."
                if licensing
                else "A smaller part of the operation."
            )
            texts = [
                "Licensor sign-off is the bottleneck",
                "The written procedure requires the Licensing Manager to record sign-off",
            ]
        else:
            title = f"Area {self.calls}"
            summary = ""
            texts = []
        findings = [
            {
                "text": text,
                "kind": "bottleneck",
                "stance": STANCES[index % len(STANCES)],
                "source_ids": sources[: 3 - index] if sources else [],
            }
            for index, text in enumerate(texts)
        ]
        answer = {
            "title": title,
            "summary": summary,
            "findings": findings,
            "open_questions": [],
        }
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"total_tokens": 50},
        }


def seed_map(db: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Build the projected fixture map; return ids the page tests need."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "transcript.json", "pdf.json", "flowchart.json")
    fake_relations(monkeypatch)
    fake_vision(monkeypatch, "vision_flowchart.json")
    transcript = _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript")
    pdf = _seed_fixture(db, PDF_FIXTURE, "pdf")
    flowchart = _seed_fixture(db, FLOWCHART_FIXTURE, "image")
    for source_id in (transcript, pdf, flowchart):
        handle_classify_extract({"payload": {"source_id": source_id}})
        handle_relations({"payload": {"source_id": source_id}})
    _fake_resolve(monkeypatch)
    run_resolve()
    run_project()
    monkeypatch.setattr(resolve_mod, "_post_chat", MapReports())
    run_communities()
    jessica = db.execute(
        "SELECT id, canonical_name FROM cmap.entity WHERE canonical_name ILIKE '%%jessica%%' "
        "ORDER BY source_count DESC LIMIT 1"
    ).fetchone()
    licensing = db.execute(
        "SELECT c.id FROM cmap.community c WHERE c.level = 1 AND c.title = %s "
        "AND %s = ANY(c.entity_ids) LIMIT 1",
        (LICENSING_TITLE, jessica[0]),
    ).fetchone()
    return {
        "transcript_id": transcript,
        "pdf_id": pdf,
        "flowchart_id": flowchart,
        "jessica_id": str(jessica[0]),
        "jessica_name": str(jessica[1]),
        "licensing_community_id": str(licensing[0]) if licensing else None,
    }


# Browser-test employee (the Playwright fake auth server signs this user in).
# Columns match the web app's Drizzle ``employees`` / ``employee_identities``
# so the Next.js login lookup and the brain's admin lookup both resolve it.
E2E_EMPLOYEE_SQL = """
CREATE TABLE IF NOT EXISTS public.employees (
  id uuid PRIMARY KEY,
  email varchar(320) NOT NULL UNIQUE,
  name varchar(255) NOT NULL,
  role varchar(255) NOT NULL,
  department varchar(255),
  departments text[] NOT NULL DEFAULT '{}',
  is_admin boolean NOT NULL DEFAULT false,
  locale varchar(12) NOT NULL DEFAULT 'en',
  disabled_at timestamp,
  last_login_at timestamp,
  created_at timestamp NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.employee_identities (
  id uuid PRIMARY KEY,
  employee_id uuid NOT NULL,
  auth_provider text NOT NULL DEFAULT 'magic_link',
  auth_user_id uuid NOT NULL UNIQUE,
  auth_provider_subject varchar(255),
  email varchar(320) NOT NULL DEFAULT '',
  linked_at timestamp NOT NULL DEFAULT now(),
  last_login_at timestamp
);
INSERT INTO public.employees (id, email, name, role, is_admin) VALUES
  ('00000000-0000-4000-8000-0000000000e1', 'map-e2e@test.invalid', 'Map Test Admin',
   'Operations', true)
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.employee_identities (id, employee_id, auth_user_id, email) VALUES
  ('00000000-0000-4000-8000-0000000000e3', '00000000-0000-4000-8000-0000000000e1',
   '00000000-0000-4000-8000-0000000000e2', 'map-e2e@test.invalid')
ON CONFLICT (id) DO NOTHING;
"""


def seed_eval(db: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Two replayed eval runs of the seed questions (plan step 11 page test).

    The first run drops every citation (as a broken pipeline would) so the
    page has a run-over-run change to show; the second is the normal replay.
    """
    from test_answer import _point_embeddings, fake_compress
    from test_eval_fixture import EvalAnswers, KeywordGrader

    from brain.answer import answer as answer_mod
    from brain.eval import run as eval_mod

    _point_embeddings(db)
    eval_mod.load_seed()
    monkeypatch.setattr(answer_mod, "_post_chat", EvalAnswers())
    monkeypatch.setattr(eval_mod, "_post_chat", KeywordGrader())
    fake_compress(monkeypatch)
    real_finalize = answer_mod._finalize_local
    with monkeypatch.context() as broken:
        broken.setattr(
            answer_mod,
            "_finalize_local",
            lambda answer_md, raw, chunks: real_finalize(answer_md, raw, []),
        )
        first = eval_mod.run_eval()
    second = eval_mod.run_eval()
    return {"eval_first_mean": first["mean_score"], "eval_mean": second["mean_score"]}


def _reset(db: Any) -> None:
    db.execute(
        "TRUNCATE cmap.source, cmap.job, cmap.entity, cmap.community, "
        "cmap.graph_version, cmap.eval_question, cmap.eval_run CASCADE"
    )
    db.commit()


def main() -> None:
    """Seed the database in ``DATABASE_URL`` (never the shared test DB)."""
    import psycopg

    from brain.migrate import migrate

    if os.environ.get("MAP_SEED_ALLOW") != "1":
        raise SystemExit(
            "refusing to seed: set MAP_SEED_ALLOW=1 and point DATABASE_URL at a "
            "throwaway database (this truncates cmap.*)"
        )
    get_settings.cache_clear()
    migrate()
    settings = get_settings()
    with psycopg.connect(settings.database_url, connect_timeout=5) as db:
        db.execute(E2E_EMPLOYEE_SQL)
        db.commit()
        _reset(db)
        with pytest.MonkeyPatch.context() as monkeypatch:
            ids = seed_map(db, monkeypatch)
            ids.update(seed_eval(db, monkeypatch))
    print(json.dumps(ids))


if __name__ == "__main__":
    main()
