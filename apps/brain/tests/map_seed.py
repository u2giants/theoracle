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

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings
        self.calls += 1
        prompt = str(messages[-1]["content"])
        if prompt.startswith("You are compressing"):
            # Map-reduce batch summary (repair C3): compress to one line.
            body = prompt.split("<<<", 1)[-1].rsplit(">>>", 1)[0]
            summary = " ".join(body.split())[:400] or "empty batch"
            return {
                "choices": [
                    {"message": {"content": json.dumps({"summary": summary})}}
                ],
                "usage": {"total_tokens": 5},
            }
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
    # Repair C3: level 1 is one report per function (row id = the function id,
    # title = the function name), so the fixture map needs a function to own
    # its licensing report. The corpus is one licensing-approval work stream,
    # so every entity is assigned to it.
    function_id = str(
        db.execute(
            "INSERT INTO cmap.function (key, name) VALUES ('licensing', %s) "
            "ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name RETURNING id",
            (LICENSING_TITLE,),
        ).fetchone()[0]
    )
    db.execute(
        "INSERT INTO cmap.entity_function (entity_id, function_id, weight, origin) "
        "SELECT id, %s, 1.0, 'auto' FROM cmap.entity "
        "ON CONFLICT (entity_id, function_id) DO UPDATE SET weight = EXCLUDED.weight",
        (function_id,),
    )
    db.commit()
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


ZH_ENTITY_DESCRIPTION = "杰西卡负责授权方审批的签署环节。"
ZH_COMMUNITY_TITLE = "授权审批交接"
ZH_COMMUNITY_SUMMARY = "设计部与授权部门之间的审批交接流程。"


def seed_translations(db: Any, ids: dict[str, Any]) -> dict[str, Any]:
    """zh-CN sidecar rows for the 3.1 browser test (plan step 3.1)."""
    rows = [
        ("entity", ids.get("jessica_id"), "description", "zh-CN", ZH_ENTITY_DESCRIPTION),
        ("community", ids.get("licensing_community_id"), "title", "zh-CN", ZH_COMMUNITY_TITLE),
        ("community", ids.get("licensing_community_id"), "summary", "zh-CN", ZH_COMMUNITY_SUMMARY),
    ]
    for kind, ref_id, field, lang, text in rows:
        if ref_id:
            db.execute(
                "INSERT INTO cmap.translation (kind, ref_id, field, lang, text) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (kind, ref_id, field, lang) DO UPDATE SET text = EXCLUDED.text",
                (kind, ref_id, field, lang, text),
            )
    db.commit()
    return {
        "zh_entity_description": ZH_ENTITY_DESCRIPTION,
        "zh_community_title": ZH_COMMUNITY_TITLE,
        "zh_community_summary": ZH_COMMUNITY_SUMMARY,
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
CREATE TABLE IF NOT EXISTS public.departments (
  id text PRIMARY KEY,
  display_label varchar(120) NOT NULL,
  description text,
  head_employee_id uuid,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.employee_departments (
  employee_id uuid NOT NULL,
  department_id text NOT NULL,
  added_at timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (employee_id, department_id)
);
CREATE TABLE IF NOT EXISTS public.employee_directory_roles (
  employee_id uuid NOT NULL,
  role_name text NOT NULL,
  PRIMARY KEY (employee_id, role_name)
);
ALTER TABLE public.employees ADD COLUMN IF NOT EXISTS departments text[] NOT NULL DEFAULT '{}';
ALTER TABLE public.employees ADD COLUMN IF NOT EXISTS created_at timestamp NOT NULL DEFAULT now();
ALTER TABLE public.employee_identities ADD COLUMN IF NOT EXISTS auth_provider text;
"""


def seed_eval(db: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Two replayed eval runs of the seed questions (plan step 11 page test).

    The first run drops every citation (as a broken pipeline would) so the
    page has a run-over-run change to show; the second is the normal replay.
    """
    from test_answer import FakeSupport, _point_embeddings, fake_compress
    from test_eval_fixture import EvalAnswers, KeywordGrader

    from brain.answer import answer as answer_mod
    from brain.eval import run as eval_mod

    _point_embeddings(db)
    eval_mod.load_seed()
    # Plan B1: only approved questions count toward the eval bar; the two
    # replayed runs score the approved seed set, while the e2e drafts below
    # stay unapproved for the approve-flow browser test.
    db.execute("UPDATE cmap.eval_question SET approved_at = now()")
    db.commit()
    monkeypatch.setattr(answer_mod, "_post_chat", EvalAnswers())
    monkeypatch.setattr(answer_mod, "_post_flat", FakeSupport())
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
    # Two unapproved e2e drafts (plan B1 approve-flow test): one plain draft
    # with a recommendation and one abstention question. Synthetic fixture
    # wording only. They land after the replayed runs so the runs stay over
    # the approved seed set.
    draft_row = db.execute(
        "INSERT INTO cmap.eval_question (question, expected_points, "
        "expected_source_titles, author, recommendation) VALUES (%s, %s, %s, "
        "'seed', %s) RETURNING id::text",
        (
            EVAL_DRAFT,
            EVAL_DRAFT_POINTS,
            ["licensing-approval-procedure.pdf"],
            "Approve as written.",
        ),
    ).fetchone()
    abstention_row = db.execute(
        "INSERT INTO cmap.eval_question (question, expected_points, "
        "expected_source_titles, author, abstention, recommendation) VALUES "
        "(%s, %s, %s, 'seed', true, %s) RETURNING id::text",
        (
            EVAL_DRAFT_ABSTENTION,
            EVAL_DRAFT_ABSTENTION_POINTS,
            ["licensing-approval-procedure.pdf"],
            "Approve - abstention question.",
        ),
    ).fetchone()
    db.commit()
    return {
        "eval_first_mean": first["mean_score"],
        "eval_mean": second["mean_score"],
        "eval_draft": EVAL_DRAFT,
        "eval_draft_id": draft_row[0],
        "eval_draft_abstention": EVAL_DRAFT_ABSTENTION,
        "eval_draft_abstention_id": abstention_row[0],
    }


def seed_interviews(db: Any, jessica_id: str) -> dict[str, Any]:
    """Step 12 questions page: one unrouted open question, one answered one,
    and the browser-test admin as an employee who has messaged the bot."""
    db.execute("TRUNCATE cmap.open_question, cmap.teams_conversation, cmap.employee_flags, "
        "cmap.interview_send")
    db.execute(
        "INSERT INTO cmap.teams_conversation (employee_id, conversation_ref) "
        "VALUES ('00000000-0000-4000-8000-0000000000e1', "
        "'{\"conversation\": {\"id\": \"a:map-e2e\"}}'::jsonb)"
    )
    db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids) VALUES (%s, %s, %s)",
        (INTERVIEW_OPEN, "Licensing approval", [jessica_id]),
    )
    db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids, target_employee_id, "
        "state, asked_at, answer, answered_at) VALUES (%s, 'Samples', '{}', "
        "'00000000-0000-4000-8000-0000000000e1', 'answered', now() - interval '1 hour', "
        "%s, now())",
        (INTERVIEW_ANSWERED, INTERVIEW_ANSWER),
    )
    db.execute(
        "INSERT INTO cmap.interview_send (employee_id, sent_at) VALUES "
        "('00000000-0000-4000-8000-0000000000e1', now() - interval '1 hour')"
    )
    db.commit()
    return {"interview_open": INTERVIEW_OPEN, "interview_answer": INTERVIEW_ANSWER}


def seed_recommendations(db: Any) -> dict[str, Any]:
    """Step 13 page: two cards, the licensing one backed by more sources."""
    db.execute("TRUNCATE cmap.recommendation")
    sources = [str(row[0]) for row in db.execute(
        "SELECT id FROM cmap.source ORDER BY title").fetchall()]
    for problem, cited in ((REC_SMALL, sources[:1]), (REC_LICENSING, sources)):
        explanations = [
            {"hypothesis": "Only one person can record sign-off.", "support": cited,
             "against": []},
            {"hypothesis": "The data is incomplete: no timings were recorded.",
             "support": [], "against": []},
        ]
        options = [
            {"option": "Name a backup approver", "effort": "low", "risk": "Training.",
             "includes_no_change": False},
            {"option": "Batch submissions weekly", "effort": "med", "risk": "Delay.",
             "includes_no_change": False},
            {"option": "No change: keep the current process.", "effort": "low", "risk": "",
             "includes_no_change": True},
        ]
        experiment = {"change": "Backup approver for four weeks.",
                      "metric": "Days to sign-off (the metric must be measured first)",
                      "baseline_needed": True, "review_after_days": 28,
                      "owner_role": "Licensing Manager"}
        db.execute(
            "INSERT INTO cmap.recommendation (problem, explanations, options, experiment) "
            "VALUES (%s, %s, %s, %s)",
            (problem, json.dumps(explanations), json.dumps(options), json.dumps(experiment)),
        )
    db.commit()
    return {"rec_licensing": REC_LICENSING, "rec_small": REC_SMALL}


CONTRADICTION_SUMMARY = "Jordan Lee and Ilona both claim the sample sign-off."
TIMELINE_SUMMARY = "The sample sign-off owner changed between the January and March memos."


def _contradiction_relation(
    db: Any,
    source_id: str,
    from_entity: str,
    to_entity: str,
    text: str,
    ordinal: int,
) -> str:
    """One OWNS relation chunk for the D3 seed; returns the relation id."""
    chunk_id = str(
        db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
            "VALUES (%s::uuid, %s, %s::jsonb, %s, 20) RETURNING id::text",
            (source_id, ordinal, json.dumps({"page": ordinal + 1}), text),
        ).fetchone()[0]
    )
    from_m = str(
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) VALUES (%s::uuid, 'Person', 'Jordan', "
            "'jordan', %s, %s::uuid) RETURNING id::text",
            (chunk_id, text, from_entity),
        ).fetchone()[0]
    )
    to_m = str(
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) VALUES (%s::uuid, 'Process', 'sign-off', "
            "'sign off', %s, %s::uuid) RETURNING id::text",
            (chunk_id, text, to_entity),
        ).fetchone()[0]
    )
    return str(
        db.execute(
            "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, "
            "rel_type, description, stance, confidence, quote) "
            "VALUES (%s::uuid, %s::uuid, %s::uuid, 'OWNS', %s, 'practice', 0.9, %s) "
            "RETURNING id::text",
            (chunk_id, from_m, to_m, text, text),
        ).fetchone()[0]
    )


def _contradiction_source(db: Any, title: str, effective_date: str) -> str:
    return str(
        db.execute(
            "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, "
            "effective_date, read_state) VALUES ('text', %s, %s, %s, 10, %s, 'read') "
            "RETURNING id::text",
            (title, f"cmap/e2e/{title}", f"sha-e2e-{title}", effective_date),
        ).fetchone()[0]
    )


def seed_contradictions(db: Any) -> dict[str, Any]:
    """D3 page seed: one open conflict and one recorded timeline change."""
    person = str(
        db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) "
            "VALUES ('Person', 'Jordan Lee') RETURNING id::text"
        ).fetchone()[0]
    )
    process = str(
        db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) "
            "VALUES ('Process', 'Sample sign-off') RETURNING id::text"
        ).fetchone()[0]
    )
    memo = _contradiction_source(db, "Ownership memo", "2026-01-10")
    notes = _contradiction_source(db, "Team standup notes", "2026-01-10")
    rel_a = _contradiction_relation(
        db, memo, person, process,
        "Jordan Lee owns the sample sign-off.", 0,
    )
    rel_b = _contradiction_relation(
        db, notes, person, process,
        "Ilona owns the sample sign-off, not Jordan.", 1,
    )
    db.execute(
        "INSERT INTO cmap.contradiction (relation_a, relation_b, kind, summary, status) "
        "VALUES (%s::uuid, %s::uuid, 'true_contradiction', %s, 'open')",
        (rel_a, rel_b, CONTRADICTION_SUMMARY),
    )
    jan = _contradiction_source(db, "January ownership policy", "2026-01-05")
    mar = _contradiction_source(db, "March ownership policy", "2026-03-05")
    rel_c = _contradiction_relation(
        db, jan, person, process,
        "Jordan Lee owned the sample sign-off in January.", 0,
    )
    rel_d = _contradiction_relation(
        db, mar, person, process,
        "Ilona owns the sample sign-off from March.", 1,
    )
    db.execute(
        "INSERT INTO cmap.contradiction (relation_a, relation_b, kind, summary, "
        "status, resolution) VALUES (%s::uuid, %s::uuid, 'changed_over_time', %s, "
        "'explained', %s)",
        (
            rel_c,
            rel_d,
            TIMELINE_SUMMARY,
            "dates differ — timeline change, not a conflict; "
            "supersedes-over-time signal for D2",
        ),
    )
    db.commit()
    return {
        "contradiction_summary": CONTRADICTION_SUMMARY,
        "contradiction_timeline_summary": TIMELINE_SUMMARY,
        "contradiction_entity_id": person,
    }


REC_LICENSING = "Licensor sign-off stalls artwork release."
REC_SMALL = "Sample room bookings clash."
EVAL_DRAFT = "How long does the internal artwork review take in the procedure?"
EVAL_DRAFT_POINTS = [
    "The procedure defines an artwork review before release",
    "The review is recorded before the purchase order is created",
    "A rejection sends the package back for rework",
]
EVAL_DRAFT_ABSTENTION = "How many artwork reviews did the licensing team complete last quarter?"
EVAL_DRAFT_ABSTENTION_POINTS = [
    "The answer states the documents do not say",
    "The answer does not guess a number",
    "The answer names who to ask next",
]
INTERVIEW_OPEN = "Who covers licensor approvals when Jessica is out?"
INTERVIEW_ANSWERED = "Who books the sample room?"
INTERVIEW_ANSWER = "Ilona books it every Monday."


def _reset(db: Any) -> None:
    db.execute(
        "TRUNCATE cmap.source, cmap.job, cmap.entity, cmap.community, "
        "cmap.graph_version, cmap.eval_question, cmap.eval_run, cmap.translation, "
        "cmap.review_flag CASCADE"
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
        db.execute("UPDATE public.employees SET locale = 'en'")
        db.commit()
        _reset(db)
        with pytest.MonkeyPatch.context() as monkeypatch:
            ids = seed_map(db, monkeypatch)
            ids.update(seed_eval(db, monkeypatch))
        ids.update(seed_interviews(db, ids["jessica_id"]))
        ids.update(seed_recommendations(db))
        ids.update(seed_contradictions(db))
        ids.update(seed_translations(db, ids))
    print(json.dumps(ids))


if __name__ == "__main__":
    main()
