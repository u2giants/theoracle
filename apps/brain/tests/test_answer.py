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


class FakeSupport:
    """Flat-seat seam (H1): per-sentence support verdicts and one-shot rewrites.

    The default verdict is ``supported`` so replayed answers pass unchanged;
    tests pin ``verdicts`` / ``rewrites`` by sentence substring (casefolded).
    """

    def __init__(self) -> None:
        self.verdicts: dict[str, str] = {}
        self.rewrites: dict[str, str] = {}
        self.check_prompts: list[str] = []
        self.rewrite_prompts: list[str] = []

    @staticmethod
    def _sentence(prompt: str) -> str:
        marker = "SENTENCE:\n"
        if marker not in prompt:
            return ""
        return prompt.split(marker, 1)[1].split("\n\n", 1)[0].strip()

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        sentence = self._sentence(prompt)
        folded = sentence.casefold()
        if "REWRITE THIS SENTENCE" in prompt:
            self.rewrite_prompts.append(prompt)
            for key, text in self.rewrites.items():
                if key.casefold() in folded:
                    return _wrap({"sentence": text})
            return _wrap({"sentence": sentence})
        self.check_prompts.append(prompt)
        for key, verdict in self.verdicts.items():
            if key.casefold() in folded:
                return _wrap({"support": verdict})
        return _wrap({"support": "supported"})


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
        self.route_prompts: list[str] = []
        self.route_functions: list[dict[str, Any]] = []
        self.route_responses: dict[str, list[dict[str, Any]]] = {}
        self.extra_citations: list[dict[str, Any]] = []
        self.override: dict[str, Any] | None = None
        self.support = FakeSupport()
        self.local_recorded = load_recorded("frontier/answer_local.json")

    @staticmethod
    def _passage(prompt: str) -> str:
        marker = "PASSAGE:\n<<<\n"
        if marker not in prompt:
            return ""
        return prompt.split(marker, 1)[1].split("\n>>>", 1)[0]

    def _route(self, prompt: str) -> dict[str, Any]:
        self.route_prompts.append(prompt)
        passage = self._passage(prompt)
        for match, functions in self.route_responses.items():
            if match in passage:
                return {"functions": list(functions)}
        return {"functions": list(self.route_functions)}

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
        if "FUNCTION CLASSIFICATION" in prompt:
            self.calls.append("route")
            return _wrap(self._route(prompt))
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
    monkeypatch.setattr(answer_mod, "_post_flat", fake.support)
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
        assert cite["chunk_id"] is None
        assert cite["quote"]
        assert cite["locator"] is None
    # H1: the quote is the supporting finding text the prompt showed, never
    # the nearest chunk (the second procedure page is not evidence at all).
    assert {item["quote"] for item in result["citations"]} == {
        "Licensing delay blocks artwork release",
        "PO exceptions pile up over weekends",
        "Sample room checks are chronically late",
    }
    assert "second procedure page" not in json.dumps(result["citations"])
    assert [item["title"] for item in result["communities"]] == [
        "Licensing",
        "PO",
        "Company",
    ]
    # C4 step 3: function reports are selected by relevance always, so the
    # map step runs even under the old one-call token budget.
    assert fake.calls == ["map", "global"]


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
        "supported_share",
        "functions_consulted",
        "context_tokens",
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
    md, kept = answer_mod._finalize_global(
        "The process stalls at the review step [1].",
        [{"source_id": "REPORTS", "quote": "any words"}],
        [],
    )
    assert kept == []
    assert "(uncited)" in md


def test_global_ignores_superseded_reports(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair A1: a company-wide answer reads only the current map version.

    Two builds left contradictory company reports behind. The answer must be
    built from, and cite, only the newer one.
    """
    fake_embeds(monkeypatch, {})
    old = _seed_text(db, "Approvals take two days.", "old")
    new = _seed_text(db, "Approvals take three weeks.", "new")
    for version, title, text, source in (
        (1, "Company (old build)", "Approvals are fast, two days", old),
        (2, "Company", "Approvals are slow, three weeks", new),
    ):
        for level in (1, 2):
            db.execute(
                "INSERT INTO cmap.community (level, parent_id, title, report_md, "
                "findings, entity_ids, graph_version) "
                "VALUES (%s, NULL, %s, %s, %s, %s, %s)",
                (
                    level,
                    f"{title} L{level}",
                    f"# {title}\n\nSummary.\n\n## Findings",
                    json.dumps(
                        [
                            {
                                "text": f"{text} (level {level})",
                                "kind": "bottleneck",
                                "stance": "report",
                                "source_ids": [source],
                            }
                        ]
                    ),
                    [],
                    version,
                ),
            )
    db.commit()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    result = answer_question("How long do approvals take?", "global", [])
    assert result["mode_used"] == "global"
    assert "three weeks" in result["answer_md"]
    assert "two days" not in result["answer_md"]
    assert {item["source_id"] for item in result["citations"]} == {new}
    assert all("old build" not in item["title"] for item in result["communities"])
    assert all("two days" not in prompt for prompt in fake.prompts)


# ------------------------------- H1: every sentence supported or marked


def test_unsupported_sentence_marked(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """H1 gate: a sentence its quotes do not support is rewritten once, then marked.

    Policy: the rewrite is adopted only when a re-check finds it supported;
    otherwise the original sentence is shown with
    ``(unsupported \u2014 my inference)`` (shown, never deleted).
    """
    fake_embeds(monkeypatch, {})
    _seed_minimal(db)
    run_project()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.support.verdicts = {"robot": "not"}
    fake.support.rewrites = {"robot": "Robots cause every delay [1]."}
    fake.override = {
        "answer_md": (
            "The sign-off stalls at the licensor review step [1]. "
            "A robot army halts the sign-off step [1]."
        ),
        "unknowns": [],
    }
    result = answer_question(STALL_QUESTION, "local", [])
    assert (
        "A robot army halts the sign-off step. [1] (unsupported \u2014 my inference)"
        in result["answer_md"]
    )
    assert result["supported_share"] == pytest.approx(0.5)
    assert len(fake.support.check_prompts) == 3  # two checks plus the re-check
    assert len(fake.support.rewrite_prompts) == 1


def test_unsupported_sentence_rewrite_adopted(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """H1 policy: a rewrite the re-check finds supported is adopted, unmarked."""
    fake_embeds(monkeypatch, {})
    _seed_minimal(db)
    run_project()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.support.verdicts = {"robot": "not"}
    fake.support.rewrites = {
        "robot": "The sign-off stalls at the licensor review step [1]."
    }
    fake.override = {
        "answer_md": (
            "The sign-off stalls at the licensor review step [1]. "
            "A robot army halts the sign-off step [1]."
        ),
        "unknowns": [],
    }
    result = answer_question(STALL_QUESTION, "local", [])
    assert "A robot army" not in result["answer_md"]
    assert "robot" not in result["answer_md"]
    assert "(unsupported" not in result["answer_md"]
    assert result["supported_share"] == pytest.approx(1.0)


def test_uncited_sentence_marked(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """H1 gate: a sentence with no citation is marked (uncited), never passed through."""
    fake_embeds(monkeypatch, {})
    _seed_minimal(db)
    run_project()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.override = {
        "answer_md": (
            "The sign-off stalls at the licensor review step [1]. "
            "A bare claim floats without any source at all."
        ),
        "unknowns": [],
    }
    result = answer_question(STALL_QUESTION, "local", [])
    assert (
        "A bare claim floats without any source at all. (uncited)"
        in result["answer_md"]
    )
    assert result["supported_share"] == pytest.approx(0.5)


def test_global_cannot_cite_unseen_source(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """H1 gate: company-wide mode cites only sources present in the prompt."""
    fake_embeds(monkeypatch, {})
    seen = _seed_text(db, "The licensor sign-off stalls the release.", "seen")
    unseen = _seed_text(db, "A secret side process nobody saw.", "unseen")
    db.execute(
        "INSERT INTO cmap.community (level, parent_id, title, report_md, "
        "findings, entity_ids, graph_version) "
        "VALUES (1, NULL, %s, %s, %s, %s, 0)",
        (
            "Sign-off",
            "# Sign-off\n\nSummary.\n\n## Findings",
            json.dumps(
                [
                    {
                        "text": "Sign-off stalls the release",
                        "kind": "bottleneck",
                        "stance": "report",
                        "source_ids": [seen],
                    }
                ]
            ),
            [],
        ),
    )
    db.commit()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.override = {
        "answer_md": (
            "The release stalls at sign-off [1]. "
            "A side process hides the truth [2]."
        ),
        "citations": [{"source_id": seen}, {"source_id": unseen}],
        "unknowns": [],
    }
    result = answer_question("What stalls the release?", "global", [])
    assert [item["source_id"] for item in result["citations"]] == [seen]
    # H1: the quote is the prompt's supporting evidence text, not a chunk.
    assert result["citations"][0]["quote"] == "Sign-off stalls the release"
    assert result["citations"][0]["chunk_id"] is None
    assert "A side process hides the truth. (uncited)" in result["answer_md"]
    assert result["supported_share"] == pytest.approx(0.5)


def test_staged_check_marks_leftovers_verifying(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Plan §13 staged path: past the budget, non-priority sentences show (verifying)."""
    fake_embeds(monkeypatch, {})
    _seed_minimal(db)
    run_project()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    monkeypatch.setattr(answer_mod, "SUPPORT_PARALLEL_MAX", 1)
    monkeypatch.setattr(answer_mod, "SUPPORT_BUDGET_S", 0.0)
    fake.override = {
        "answer_md": (
            "The count reached 5 in 2026 [1]. "
            "plain claim alpha [1]. "
            "plain claim beta [1]."
        ),
        "unknowns": [],
    }
    result = answer_question(STALL_QUESTION, "local", [])
    assert "The count reached 5 in 2026. [1]" in result["answer_md"]
    assert "plain claim alpha. [1] (verifying)" in result["answer_md"]
    assert "plain claim beta. [1] (verifying)" in result["answer_md"]
    assert result["supported_share"] == pytest.approx(round(1 / 3, 4))


# ------------------------------- C4: function-scoped answering with a budget


def _seed_functions(db: Any) -> dict[str, str]:
    """Two curated functions: Licensing and Logistics (the C1 row shape)."""
    ids: dict[str, str] = {}
    for key, name in (("licensing", "Licensing"), ("logistics", "Logistics")):
        row = db.execute(
            "INSERT INTO cmap.function (key, name, description) "
            "VALUES (%s, %s, '') RETURNING id::text",
            (key, name),
        ).fetchone()
        ids[key] = str(row[0])
    db.commit()
    return ids


def _seed_function_chunk(
    db: Any, function_id: str, text: str, tag: str, theta: float = 0.0
) -> str:
    """One chunk assigned to ``function_id`` at weight 0.9, embedding pinned."""
    source_id = _seed_text(db, text, tag)
    chunk_id = str(
        db.execute(
            "SELECT id FROM cmap.chunk WHERE source_id = %s", (source_id,)
        ).fetchone()[0]
    )
    db.execute(
        "INSERT INTO cmap.chunk_function (chunk_id, function_id, weight, origin) "
        "VALUES (%s, %s, 0.9, 'auto')",
        (chunk_id, function_id),
    )
    db.execute(
        "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
        (vector_literal(_direction(theta)), chunk_id),
    )
    db.commit()
    return chunk_id


def test_scoped_answer_excludes_other_functions(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A Licensing question's context contains zero Logistics-only chunks."""
    fake_embeds(monkeypatch, {})
    ids = _seed_functions(db)
    _seed_function_chunk(
        db,
        ids["licensing"],
        "The licensor sign-off is recorded in the licensing approval log.",
        "lic",
    )
    _seed_function_chunk(
        db,
        ids["logistics"],
        "The freight forwarder books the container in the logistics dispatch log.",
        "log",
    )
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.route_functions = [{"key": "licensing", "weight": 0.9}]
    result = answer_question("How does the licensing approval log work?", "auto", [])
    assert [item["key"] for item in result["functions_consulted"]] == ["licensing"]
    assert "licensing approval log" in fake.prompts[0]
    assert all("logistics dispatch log" not in prompt for prompt in fake.prompts)


def test_handoff_neighbour_included(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """One hand-off hop across the function boundary is in scope; nothing else is."""
    fake_embeds(monkeypatch, {})
    ids = _seed_functions(db)
    chunk_id = _seed_function_chunk(
        db,
        ids["licensing"],
        "The licensor review hands the package to freight booking.",
        "hand",
    )
    entities: dict[str, str] = {}
    for key, name, function_key, theta in (
        ("review", "Licensor review", "licensing", 0.0),
        ("handoff", "Freight hand-off", "logistics", 0.05),
        ("truck", "Truck booking", "logistics", 0.05),
    ):
        row = db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name, description, "
            "mention_count, source_count) VALUES ('Step', %s, '', 1, 1) "
            "RETURNING id::text",
            (name,),
        ).fetchone()
        entity_id = str(row[0])
        entities[key] = entity_id
        db.execute(
            "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_direction(theta)), entity_id),
        )
        db.execute(
            "INSERT INTO cmap.entity_function (entity_id, function_id, weight, "
            "origin) VALUES (%s, %s, 0.9, 'auto')",
            (entity_id, ids[function_key]),
        )
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, embedding, entity_id) "
            "VALUES (%s, 'Step', %s, %s, %s, %s::vector, %s)",
            (
                chunk_id,
                name,
                name.lower(),
                "the quoted hand-off step",
                vector_literal(_direction(theta)),
                entity_id,
            ),
        )
    for from_key, to_key, rel_type in (
        ("review", "handoff", "HANDS_OFF_TO"),
        ("review", "truck", "DEPENDS_ON"),
    ):
        from_row = db.execute(
            "SELECT id FROM cmap.mention WHERE entity_id = %s", (entities[from_key],)
        ).fetchone()
        to_row = db.execute(
            "SELECT id FROM cmap.mention WHERE entity_id = %s", (entities[to_key],)
        ).fetchone()
        db.execute(
            "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, "
            "rel_type, description, stance, confidence, quote) "
            "VALUES (%s, %s, %s, %s, '', 'practice', 1.0, '')",
            (chunk_id, from_row[0], to_row[0], rel_type),
        )
    db.commit()
    run_project()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.route_functions = [{"key": "licensing", "weight": 0.9}]
    result = answer_question("How does the licensor review hand off work?", "auto", [])
    prompt = fake.prompts[0]
    assert "Freight hand-off" in prompt
    assert "Truck booking" not in prompt
    assert [item["key"] for item in result["functions_consulted"]] == ["licensing"]


def test_similarity_floor_returns_dont_know(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The similarity floor: nearest-of-nothing is never evidence."""
    fake_embeds(monkeypatch, {})
    ids = _seed_functions(db)
    _seed_function_chunk(
        db,
        ids["licensing"],
        "The catering menu lists spring rolls.",
        "far",
        theta=1.4,
    )
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.route_functions = [{"key": "licensing", "weight": 0.9}]
    result = answer_question("Where does the licensing approval stall?", "auto", [])
    assert "don't know" in result["answer_md"].casefold()
    assert result["citations"] == []
    assert result["context_tokens"] == 0
    assert fake.calls == ["route"]
    assert "spring rolls" not in "".join(fake.prompts)


def test_context_never_exceeds_budget(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The hard ceiling (BRAIN_ANSWER_CONTEXT_TOKENS) is never exceeded."""
    monkeypatch.setenv("BRAIN_ANSWER_CONTEXT_TOKENS", "300")
    get_settings.cache_clear()
    fake_embeds(monkeypatch, {})
    ids = _seed_functions(db)
    texts = [
        (
            f"Procedure step {index}: the licensing desk records the batch total "
            f"and forwards the file for counter-signature on page {index}. "
        )
        * 4
        for index in range(8)
    ]
    for index, text in enumerate(texts):
        _seed_function_chunk(db, ids["licensing"], text, f"b{index}")
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.route_functions = [{"key": "licensing", "weight": 0.9}]
    result = answer_question("How does the licensing desk record batches?", "auto", [])
    assert result["context_tokens"] <= 300
    shown = [text for text in texts if text in fake.prompts[0]]
    assert shown
    assert len(shown) < len(texts)


def test_short_alias_not_substring_matched(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Alias seeding matches on word boundaries and never for short aliases."""
    fake_embeds(monkeypatch, {})
    source_id = _seed_text(db, "The concatenate and wait steps of the lab process.", "alias")
    chunk_id = str(
        db.execute(
            "SELECT id FROM cmap.chunk WHERE source_id = %s", (source_id,)
        ).fetchone()[0]
    )
    names = {"trap": "Substring trap", "lab": "Lab process"}
    entity_ids: dict[str, str] = {}
    for key, name in names.items():
        row = db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name, description, "
            "mention_count, source_count) VALUES ('Step', %s, '', 1, 1) "
            "RETURNING id::text",
            (name,),
        ).fetchone()
        entity_ids[key] = str(row[0])
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) "
            "VALUES (%s, 'Step', %s, %s, %s, %s)",
            (chunk_id, name, name.lower(), "the lab process", entity_ids[key]),
        )
    for alias in ("it", "cat"):
        db.execute(
            "INSERT INTO cmap.entity_alias (entity_id, entity_type, normalized_name) "
            "VALUES (%s, 'Step', %s)",
            (entity_ids["trap"], alias),
        )
    db.execute(
        "INSERT INTO cmap.entity_alias (entity_id, entity_type, normalized_name) "
        "VALUES (%s, 'Step', 'lab')",
        (entity_ids["lab"],),
    )
    db.commit()
    question = "the concatenate and wait steps of the lab process"
    vector = [1.0 / math.sqrt(_dims())] * _dims()
    selected = answer_mod._select_entities(question, vector, False, None)
    found = {item["name"] for item in selected}
    assert "Lab process" in found
    assert "Substring trap" not in found


def test_followup_inherits_function(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """History is classified with the question, so follow-ups inherit scope."""
    fake_embeds(monkeypatch, {})
    ids = _seed_functions(db)
    _seed_function_chunk(
        db,
        ids["licensing"],
        "The licensor sign-off is recorded in the licensing approval log.",
        "lic",
    )
    _seed_function_chunk(
        db,
        ids["logistics"],
        "The freight forwarder books the container in the logistics dispatch log.",
        "log",
    )
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.route_responses = {
        "licensing": [{"key": "licensing", "weight": 0.9}],
        "logistics": [{"key": "logistics", "weight": 0.9}],
    }
    first = answer_question("How does the licensing approval log work?", "auto", [])
    assert [item["key"] for item in first["functions_consulted"]] == ["licensing"]
    history = [
        {"role": "user", "content": "How does the licensing approval log work?"},
        {"role": "assistant", "content": first["answer_md"]},
    ]
    result = answer_question("Why does it stall there?", "auto", history)
    assert [item["key"] for item in result["functions_consulted"]] == ["licensing"]
    assert "licensing approval log" in fake.route_prompts[1]
    assert all("logistics dispatch log" not in prompt for prompt in fake.prompts)


def test_low_routing_confidence_uses_one_hybrid_prompt(
    answer_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Low routing confidence: the top function plus the company report, one prompt."""
    fake_embeds(monkeypatch, {})
    ids = _seed_functions(db)
    _seed_function_chunk(
        db,
        ids["licensing"],
        "The licensor sign-off is recorded in the licensing approval log.",
        "lic",
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
                        "text": "Approvals queue up at the licensor review",
                        "kind": "bottleneck",
                        "stance": "report",
                        "source_ids": [],
                    }
                ]
            ),
            [],
        ),
    )
    db.commit()
    fake = fake_answer(monkeypatch)
    fake_compress(monkeypatch)
    fake.route_functions = [{"key": "licensing", "weight": 0.3}]
    result = answer_question("What are the biggest problems?", "auto", [])
    assert result["mode_used"] == "hybrid"
    assert fake.calls == ["route", "local"]
    prompt = fake.prompts[0]
    assert "licensing approval log" in prompt
    assert "Company-wide view." in prompt
    assert [item["key"] for item in result["functions_consulted"]] == ["licensing"]
