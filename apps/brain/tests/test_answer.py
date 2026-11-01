"""Question answering: local and global modes (plan step 9).

The fixture question runs against the projected fixture corpus (procedure
PDF, Teams transcript, flowchart PNG) with every model call replayed from
``tests/fixtures/recorded/`` or a deterministic fake; no test calls a real
model. The named gate is the three done-when tests below.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from conftest import (
    FakeScaleDown,
    fake_relations,
    fake_scaledown,
    fake_vision,
    load_recorded,
)
from test_flat import PDF_FIXTURE, TRANSCRIPT_FIXTURE, _seed_fixture, _seed_text
from test_resolve import _fake as _fake_resolve

from brain.answer import answer as answer_mod
from brain.answer.answer import answer_question
from brain.config import get_settings
from brain.embed import vector_literal
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph.project import run_project
from brain.resolve.resolve import run_resolve

STALL_QUESTION = "Where does licensing approval stall and why?"
FLOWCHART_FIXTURE = "licensing-approval-flowchart.png"


# ------------------------------------------------------------------ helpers


def _dims() -> int:
    return get_settings().brain_embed_dims


def _direction(theta: float) -> list[float]:
    """Unit vector at angle ``theta`` from the all-ones question direction.

    ``fake_embeddings`` (and this file's ``fake_embeds`` fallback) return an
    all-equal vector for the question, so cosine similarity to the question is
    exactly ``cos(theta)`` and retrieval order is fully controlled.
    """
    size = _dims()
    base = [1.0 / math.sqrt(size)] * size
    perp = [0.0] * size
    perp[0] = 1.0 / math.sqrt(2)
    perp[1] = -1.0 / math.sqrt(2)
    return [
        math.cos(theta) * left + math.sin(theta) * right
        for left, right in zip(base, perp, strict=True)
    ]


def fake_embeds(
    monkeypatch: pytest.MonkeyPatch, special: dict[str, list[float]]
) -> list[list[str]]:
    """Replay embeddings: ``special`` substring keys win, else length vector."""
    from brain import embed as embed_mod

    calls: list[list[str]] = []

    def _post_embeddings(
        texts: list[str], settings: Any
    ) -> tuple[list[list[float]], dict[str, int]]:
        calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            chosen = None
            for key, vector in special.items():
                if key in text:
                    chosen = vector
                    break
            if chosen is None:
                chosen = [0.001 * len(text)] * settings.brain_embed_dims
            vectors.append(list(chosen))
        return vectors, {"embedding_tokens": len(texts) * 3}

    monkeypatch.setattr(embed_mod, "_post_embeddings", _post_embeddings)
    return calls


def _wrap(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "usage": {"total_tokens": 50},
    }


class FakeAnswer:
    """Replay frontier answer calls, split by local / global / map prompts.

    Local responses replay ``recorded/frontier/answer_local.json`` prose and
    cite one verbatim quote per source found in the prompt's QUOTES block (the
    quotes come from the database, so every echoed citation validates). Global
    responses rank the prompt's findings by distinct-source count — the plan's
    ranking rule — so the ranking test is not a tautology.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.calls: list[str] = []
        self.extra_citations: list[dict[str, Any]] = []
        self.override: dict[str, Any] | None = None
        self.local_recorded = load_recorded("frontier/answer_local.json")

    @staticmethod
    def _quotes(prompt: str) -> list[dict[str, str]]:
        marker = "QUOTES (verbatim, each with its chunk_id):\n"
        if marker not in prompt:
            return []
        blob = prompt.split(marker, 1)[1].split("\n>>>", 1)[0].strip()
        items = json.loads(blob)
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _findings(prompt: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for line in prompt.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- [") or "(sources: " not in stripped:
                continue
            text = stripped.split("] ", 1)[1].rsplit(" (sources: ", 1)[0]
            raw_ids = stripped.rsplit("(sources: ", 1)[1].rstrip(")")
            ids = [part.strip() for part in raw_ids.split(",") if part.strip()]
            out.append({"text": text, "source_ids": ids})
        return out

    def _local(self, prompt: str) -> dict[str, Any]:
        quotes = self._quotes(prompt)
        picked: list[dict[str, str]] = []
        seen_sources: set[str] = set()
        for quote in quotes:
            source_id = str(quote.get("source_id") or "")
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            picked.append(
                {
                    "chunk_id": str(quote.get("chunk_id") or ""),
                    "quote": str(quote.get("quote") or ""),
                }
            )
        entry = self.local_recorded.get("default") or {}
        for candidate in self.local_recorded.get("responses") or []:
            match = str(candidate.get("match") or "")
            if match and match in prompt:
                entry = candidate
                break
        payload: dict[str, Any] = {
            "answer_md": str(entry.get("answer_md") or ""),
            "citations": picked,
            "unknowns": [str(item) for item in (entry.get("unknowns") or [])],
        }
        if self.override is not None:
            payload.update(self.override)
        payload["citations"] = list(payload.get("citations") or []) + self.extra_citations
        return payload

    def _global(self, prompt: str) -> dict[str, Any]:
        findings = self._findings(prompt)
        ranked = sorted(
            findings,
            key=lambda item: len(set(item["source_ids"])),
            reverse=True,
        )
        points = ranked[:5]
        lines: list[str] = []
        citations: list[dict[str, str]] = []
        for position, item in enumerate(points, start=1):
            markers = ""
            for source_id in sorted(set(item["source_ids"])):
                citations.append({"source_id": source_id})
                markers += f"[{len(citations)}]"
            lines.append(f"{position}. {item['text']} {markers}")
        payload: dict[str, Any] = {
            "answer_md": "\n".join(lines),
            "citations": citations,
            "unknowns": [],
        }
        if self.override is not None:
            payload.update(self.override)
        payload["citations"] = list(payload.get("citations") or []) + self.extra_citations
        return payload

    def _map(self, prompt: str) -> dict[str, Any]:
        findings = self._findings(prompt)
        points = [
            {
                "text": item["text"],
                "source_ids": item["source_ids"],
                "relevance": min(10, 2 * len(set(item["source_ids"]))),
            }
            for item in findings[:10]
        ]
        return {"points": points}

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        self.prompts.append(prompt)
        if "list the points relevant to the question" in prompt:
            self.calls.append("map")
            return _wrap(self._map(prompt))
        if "REPORTS:" in prompt and "ENTITIES AND EDGES" not in prompt:
            self.calls.append("global")
            return _wrap(self._global(prompt))
        self.calls.append("local")
        return _wrap(self._local(prompt))


def fake_answer(monkeypatch: pytest.MonkeyPatch) -> FakeAnswer:
    """Replay frontier answer calls through the answer module's HTTP seam."""
    fake = FakeAnswer()
    monkeypatch.setattr(answer_mod, "_post_chat", fake)
    return fake


class FakeCompress(FakeScaleDown):
    """ScaleDown seam for the answer module: compress only, canned result."""

    def __init__(self) -> None:
        super().__init__([])
        self.compress_calls: list[dict[str, Any]] = []
        self.route_response: dict[str, Any] = {
            "top_label": "specific",
            "scores": {"specific": 0.9, "broad": 0.1},
        }

    def __call__(self, path: str, body: dict[str, Any], settings: Any) -> dict[str, Any]:
        del settings
        self.compress_calls.append({"path": path, "body": body})
        if path == "/compress/raw/":
            return {
                "results": {
                    "success": True,
                    "compressed_prompt": "COMPRESSED PASSAGES",
                    "compressed_prompt_tokens": 10,
                    "original_prompt_tokens": 20,
                }
            }
        if path == "/classify":
            return dict(self.route_response)
        raise AssertionError(f"unexpected scaledown path {path}")


def fake_compress(monkeypatch: pytest.MonkeyPatch) -> FakeCompress:
    fake = FakeCompress()
    monkeypatch.setattr(answer_mod, "_post_scaledown", fake)
    return fake


@pytest.fixture()
def answer_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _point_embeddings(db: Any) -> None:
    """Fix chunk and entity embeddings so retrieval order is deterministic."""
    quoted = {
        str(row[0])
        for row in db.execute("SELECT DISTINCT chunk_id FROM cmap.mention").fetchall()
    }
    rows = db.execute(
        "SELECT c.id, s.title FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id"
    ).fetchall()
    for chunk_id, title in rows:
        if "licensing-approval-procedure" in str(title):
            theta = 0.10
        elif "flowchart" in str(title):
            theta = 0.20
        elif str(chunk_id) in quoted:
            theta = 0.30
        else:
            theta = 1.30
        db.execute(
            "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_direction(theta)), chunk_id),
        )
    for (entity_id,) in db.execute("SELECT id FROM cmap.entity").fetchall():
        db.execute(
            "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_direction(0.05)), entity_id),
        )
    db.commit()


def _seed_minimal(db: Any) -> tuple[str, str, str]:
    """One source whose chunk text contains its mention quote verbatim."""
    text = "The sign-off stalls at the licensor review step."
    source_id = _seed_text(db, text, "stall")
    chunk_id = str(
        db.execute(
            "SELECT id FROM cmap.chunk WHERE source_id = %s", (source_id,)
        ).fetchone()[0]
    )
    entity_row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name, description, "
        "mention_count, source_count) VALUES ('Issue', 'the sign-off stall', "
        "'A bottleneck.', 1, 1) RETURNING id"
    ).fetchone()
    entity_id = str(entity_row[0])
    db.execute(
        "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
        (vector_literal(_direction(0.0)), entity_id),
    )
    db.execute(
        "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
        "normalized_name, quote, embedding, entity_id) "
        "VALUES (%s, 'Issue', 'sign-off stall', 'sign-off stall', %s, "
        "%s::vector, %s)",
        (chunk_id, text, vector_literal(_direction(0.0)), entity_id),
    )
    db.execute(
        "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
        (vector_literal(_direction(0.0)), chunk_id),
    )
    db.commit()
    return source_id, chunk_id, entity_id


# --------------------------------------------------------- the named gate


def test_local_answer_cites_three_sources_for_stall_question(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The stall question's citations cover the PDF, transcript and flowchart."""
    fake_embeds(monkeypatch, {})
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
    _point_embeddings(db)
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    result = answer_question(STALL_QUESTION, "local", [])
    assert result["mode_used"] == "local"
    cited = {item["source_id"] for item in result["citations"]}
    assert cited == {transcript, pdf, flowchart}
    for cite in result["citations"]:
        assert cite["title"]
        assert cite["chunk_id"]
        assert cite["quote"]
        assert cite["locator"] is not None
    prompt = fake.prompts[0]
    assert STALL_QUESTION in prompt
    assert "ENTITIES AND EDGES" in prompt
    assert "QUOTES (verbatim, each with its chunk_id)" in prompt
    assert result["answer_md"].strip()
    assert not result["unknowns"] or all(isinstance(item, str) for item in result["unknowns"])


def test_global_answer_ranks_licensing_delay_top(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The company-wide answer puts the most-attested problem first."""
    fake_embeds(monkeypatch, {"Licensing delay blocks artwork release": _direction(0.0)})
    proc = _seed_text(db, "The licensor sign-off stalls the release for weeks.", "proc")
    tx = _seed_text(db, "Jessica says the sign-off is the bottleneck.", "tx")
    flow = _seed_text(db, "FLOWCHART n4 Record sign-off (Jessica)", "flow")
    proc_chunks = db.execute(
        "SELECT id FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
        (proc,),
    ).fetchall()
    base_chunk = str(proc_chunks[0][0])
    second = db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, 1, %s, %s, 10) RETURNING id",
        (proc, json.dumps({"page": 2}), "A second procedure page about sign-off timing."),
    ).fetchone()
    second_chunk = str(second[0])
    for chunk_id, theta in ((base_chunk, 0.05), (second_chunk, 1.0)):
        db.execute(
            "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_direction(theta)), chunk_id),
        )
    for source_id in (tx, flow):
        db.execute(
            "UPDATE cmap.chunk SET embedding = %s::vector WHERE source_id = %s",
            (vector_literal(_direction(0.5)), source_id),
        )
    findings = {
        "Licensing": [
            {
                "text": "Licensing delay blocks artwork release",
                "kind": "bottleneck",
                "stance": "report",
                "source_ids": [proc, tx, flow],
            }
        ],
        "PO": [
            {
                "text": "PO exceptions pile up over weekends",
                "kind": "complaint",
                "stance": "report",
                "source_ids": [proc],
            }
        ],
    }
    for title, items in findings.items():
        db.execute(
            "INSERT INTO cmap.community (level, parent_id, title, report_md, "
            "findings, entity_ids, graph_version) "
            "VALUES (1, NULL, %s, %s, %s, %s, 0)",
            (
                title,
                f"# {title}\n\nArea summary.\n\n## Findings",
                json.dumps(items),
                [],
            ),
        )
    db.execute(
        "INSERT INTO cmap.community (level, parent_id, title, report_md, "
        "findings, entity_ids, graph_version) "
        "VALUES (2, NULL, 'Company', %s, %s, %s, 0)",
        (
            "# Company\n\nCompany-wide view.\n\n## Findings",
            json.dumps(
                [
                    {
                        "text": "Sample room checks are chronically late",
                        "kind": "complaint",
                        "stance": "report",
                        "source_ids": [tx],
                    }
                ]
            ),
            [],
        ),
    )
    db.commit()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    result = answer_question(
        "What are the biggest problems across the company?", "global", []
    )
    assert result["mode_used"] == "global"
    first_line = result["answer_md"].splitlines()[0]
    assert first_line.startswith("1.")
    assert "Licensing delay" in first_line
    assert "PO exceptions" in result["answer_md"]
    assert {item["source_id"] for item in result["citations"]} == {proc, tx, flow}
    for cite in result["citations"]:
        assert cite["title"].startswith("flat-test single chunk")
        assert cite["chunk_id"]
        assert cite["quote"]
        assert cite["locator"] is not None
    by_source = {item["source_id"]: item for item in result["citations"]}
    assert by_source[proc]["chunk_id"] == base_chunk
    assert [item["title"] for item in result["communities"]] == [
        "Licensing",
        "PO",
        "Company",
    ]
    assert fake.calls == ["global"]


def test_invalid_citation_dropped(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A fabricated quote is dropped and its sentence is marked (uncited)."""
    fake_embeds(monkeypatch, {})
    source_id, chunk_id, _entity_id = _seed_minimal(db)
    run_project()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.override = {
        "answer_md": (
            "The sign-off stalls at the licensor review step [1]. "
            "A fabricated sentence pretends evidence [2]."
        ),
        "unknowns": [],
    }
    fake.extra_citations = [
        {"chunk_id": chunk_id, "quote": "these words appear in no chunk at all"}
    ]
    result = answer_question(STALL_QUESTION, "local", [])
    assert [item["quote"] for item in result["citations"]] == [
        "The sign-off stalls at the licensor review step."
    ]
    assert result["citations"][0]["source_id"] == source_id
    assert "(uncited)" in result["answer_md"]
    assert "pretends evidence. (uncited)" in result["answer_md"]
    assert "these words appear in no chunk at all" not in result["answer_md"]
    assert "stalls at the licensor review step. [1]" in result["answer_md"]


# ------------------------------------------------------- plan rules at unit level


def test_passages_compressed_when_over_threshold(
    answer_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passages over 6,000 tokens go through ScaleDown /compress/raw/."""
    fake = fake_compress(monkeypatch)
    settings = get_settings()
    usage: dict[str, int] = {}
    short = answer_mod._compress_passages(
        ["short passage"] * 3, STALL_QUESTION, settings, usage
    )
    assert short == "short passage\n\nshort passage\n\nshort passage"
    assert fake.compress_calls == []
    long = answer_mod._compress_passages(
        ["lorem ipsum dolor sit amet " * 200] * 15, STALL_QUESTION, settings, usage
    )
    assert long == "COMPRESSED PASSAGES"
    assert len(fake.compress_calls) == 1
    assert fake.compress_calls[0]["path"] == "/compress/raw/"
    assert fake.compress_calls[0]["body"]["rate"] == "auto"
    assert fake.compress_calls[0]["body"]["prompt"] == STALL_QUESTION
    assert usage["scaledown_compress_calls"] == 1


def test_route_mode_specific_broad_and_low_confidence(
    answer_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ScaleDown classify routes specific/local, broad/global, low score/both."""
    fake = fake_compress(monkeypatch)
    settings = get_settings()
    usage: dict[str, int] = {}
    assert answer_mod._route_mode("q", settings, usage) == "local"
    fake.route_response = {
        "top_label": "broad",
        "scores": {"specific": 0.1, "broad": 0.9},
    }
    assert answer_mod._route_mode("q", settings, usage) == "global"
    fake.route_response = {
        "top_label": "broad",
        "scores": {"specific": 0.5, "broad": 0.5},
    }
    assert answer_mod._route_mode("q", settings, usage) == "both"
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "false")
    get_settings.cache_clear()
    assert answer_mod._route_mode("q", get_settings(), usage) == "both"


def test_history_appended_and_capped_to_six_turns() -> None:
    """Only the last six turns reach the prompt (plan step 9 conversation)."""
    history = [{"role": "user", "content": f"turn {index}"} for index in range(8)]
    rendered = answer_mod._render_history(history)
    assert "turn 7" in rendered
    assert "turn 2" in rendered
    assert "turn 1" not in rendered
    assert answer_mod._render_history([]) == "CONVERSATION SO FAR: (none)"


def test_global_map_reduce_over_many_reports(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Reports past the one-call budget map per batch of 10, then reduce."""
    fake_embeds(monkeypatch, {})
    sources = [
        _seed_text(db, f"Source {index} covers one area of the delay.", f"s{index}")
        for index in range(3)
    ]
    filler = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do " * 500
    for index in range(25):
        items = [
            {
                "text": f"Point {index} about the flow",
                "kind": "flow",
                "stance": "practice",
                "source_ids": [sources[index % 3]],
            }
        ]
        if index == 0:
            items[0]["source_ids"] = list(sources)
        db.execute(
            "INSERT INTO cmap.community (level, parent_id, title, report_md, "
            "findings, entity_ids, graph_version) "
            "VALUES (1, NULL, %s, %s, %s, %s, 0)",
            (
                f"Area {index:02d}",
                f"# Area {index:02d}\n\n{filler}\n\n## Findings",
                json.dumps(items),
                [],
            ),
        )
    db.commit()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    result = answer_question(
        "What is the biggest problem across the company?", "global", []
    )
    assert fake.calls.count("map") == 3
    assert fake.calls[-1] == "global"
    assert "MAPPED POINTS" in fake.prompts[-1]
    assert result["answer_md"].splitlines()[0].startswith("1.")
    assert "Point 0" in result["answer_md"].splitlines()[0]
    assert len(result["communities"]) == 25


def test_answer_endpoint_round_trip(
    answer_env: None,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
    client: Any,
    user_headers: dict[str, str],
) -> None:
    """POST /answer returns the step-9 response shape for any employee."""
    fake_embeds(monkeypatch, {})
    source_id, _chunk_id, _entity_id = _seed_minimal(db)
    run_project()
    fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    response = client.post(
        "/answer",
        json={
            "question": STALL_QUESTION,
            "mode": "local",
            "history": [{"role": "user", "content": "hello"}],
        },
        headers=user_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "answer_md",
        "citations",
        "mode_used",
        "entities",
        "communities",
        "unknowns",
    }
    assert body["mode_used"] == "local"
    assert body["citations"][0]["source_id"] == source_id
    assert body["citations"][0]["quote"] == "The sign-off stalls at the licensor review step."
    rejected = client.post(
        "/answer",
        json={"question": "", "mode": "local"},
        headers=user_headers,
    )
    assert rejected.status_code == 400
    bad_mode = client.post(
        "/answer",
        json={"question": "hi", "mode": "magic"},
        headers=user_headers,
    )
    assert bad_mode.status_code == 400

def test_global_word_source_id_dropped(answer_env: None, db: Any) -> None:
    """A global citation whose source_id is not a uuid is dropped, not a crash.

    Measured on the bake-off (2026-11-01): a candidate answered with
    source_id "REPORTS" and the uuid column rejected the lookup.
    """
    from brain.config import get_settings

    md, kept = answer_mod._finalize_global(
        "The process stalls at the review step [1].",
        [{"source_id": "REPORTS", "quote": "any words"}],
        get_settings(),
        {},
    )
    assert kept == []
    assert "(uncited)" in md
