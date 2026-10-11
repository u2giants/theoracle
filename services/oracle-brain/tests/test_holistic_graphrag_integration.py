from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from graphrag_sdk.core.models import LLMResponse
from graphrag_sdk.core.providers import Embedder, LLMInterface

from oracle_brain.graph.graphrag import (
    AdmittedEmbedder,
    AdmittedLLM,
    CallBudget,
    Corpus,
    CorpusSource,
    HolisticGraphPilot,
)
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest


DOC_ONE = "Intake Lead sends the packet to Review Team. Review Team follows the signed policy."
DOC_TWO = "Review Team reviews the packet. If the packet is incomplete, Review Team returns it to Intake Lead."


def _source(text: str, filename: str):
    return CorpusSource(source_id=uuid4(), revision="r1", filename=filename, text=text,
                        content_hash=hashlib.sha256(text.encode()).hexdigest(), complete=True)


class DeterministicLLM(LLMInterface):
    """Fixed local responses: no network model or default SDK model is used."""

    def __init__(self, first_id: str, second_id: str, first_text: str, second_text: str,
                 grounding_supported: bool = True):
        super().__init__("fixed-synthetic-llm", max_concurrency=1)
        self.first_id, self.second_id = first_id, second_id
        self.first_text, self.second_text = first_text, second_text
        self.grounding_supported = grounding_supported
        self.calls = []

    def invoke(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls.append(prompt)
        if "GROUNDING REVIEW" in prompt:
            return LLMResponse(content=json.dumps({
                "supported": self.grounding_supported,
                "unsupported_statements": [] if self.grounding_supported else ["invented causation"],
                "omitted_required_exceptions": [],
                "concealed_conflicts": [],
            }))
        if "FULL ORIGINAL SOURCE DATA" in prompt:
            answer = {
                "explanation": [{
                    "text": "Intake sends the packet and Review Team reviews it.",
                    "citations": [
                        {"source_id": self.first_id, "quote": "Intake Lead sends the packet to Review Team.",
                         },
                        {"source_id": self.second_id, "quote": "Review Team reviews the packet.",
                         },
                    ],
                }],
                "conflicts": [],
                "unknowns": ["The approval owner is not stated."],
                "hypothetical_improvements": [],
            }
            return LLMResponse(content=json.dumps(answer))
        if "DOCUMENT DATA" in prompt and "incomplete" in prompt:
            payload = {
                "objects": [
                    {"key": "review", "kind": "Role", "name": "Review Team", "scope": "licensed",
                     "description": "reviews packets", "quote": "Review Team reviews the packet"},
                    {"key": "return", "kind": "Exception", "name": "Incomplete packet return", "scope": "licensed",
                     "description": "return path", "quote": "If the packet is incomplete"},
                ],
                "links": [{"source": "review", "target": "return", "kind": "EXCEPTION_TO",
                            "description": "incomplete packets use the return path",
                            "quote": "If the packet is incomplete"}],
                "missing_information": [], "conflicts": [],
            }
        else:
            payload = {
                "objects": [
                    {"key": "intake", "kind": "Role", "name": "Intake Lead", "scope": "licensed",
                     "description": "sends packets", "quote": "Intake Lead sends the packet to Review Team"},
                    {"key": "review", "kind": "Role", "name": "Review Team", "scope": "licensed",
                     "description": "receives packets", "quote": "Review Team"},
                ],
                "links": [{"source": "intake", "target": "review", "kind": "HANDOFF_TO",
                            "description": "intake hands the packet to review",
                            "quote": "sends the packet to Review Team"}],
                "missing_information": [], "conflicts": [],
            }
        return LLMResponse(content=json.dumps(payload))


class DeterministicEmbedder(Embedder):
    @property
    def model_name(self):
        return "fixed-synthetic-embedder"

    def embed_query(self, text: str, **kwargs):
        return [0.0, 1.0, 0.0, 1.0]


def test_real_falkordb_sdk_builds_finalizes_retrieves_and_answers_across_documents():
    graph_url = os.environ.get("ORACLE2_TEST_FALKORDB_URL")
    if not graph_url:
        pytest.skip("set ORACLE2_TEST_FALKORDB_URL to an approved loopback FalkorDB port")
    first, second = _source(DOC_ONE, "intake.txt"), _source(DOC_TWO, "review.txt")
    corpus = Corpus(workspace_id=uuid4(), sources=(first, second),
                    expected_source_ids=frozenset({first.source_id, second.source_id}))
    request = ProcessingRequest(provider="local-synthetic", account="loopback", endpoint=graph_url,
                                data_classes=frozenset({"synthetic"}), purpose="holistic-integration",
                                terms_hash="a" * 64)
    approval = ProcessingApproval(**request.model_dump(), register_ref="loopback-fixture",
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    llm = DeterministicLLM(str(first.source_id), str(second.source_id), first.text, second.text)
    pilot = HolisticGraphPilot(
        corpus, graph_url,
        AdmittedLLM(llm, request, [approval], CallBudget(64)),
        AdmittedEmbedder(DeterministicEmbedder(), request, [approval], CallBudget(64)),
        config_id="fixed-synthetic-config-v1", dimensions=4,
    )

    async def run():
        try:
            built = await pilot.build()
            calls_after_first_build = len(llm.calls)
            reused = await pilot.build()
            assert reused["reused_snapshot"] is True
            assert len(llm.calls) == calls_after_first_build
            retrieved = await pilot.rag.retrieve("packet")
            stats = await pilot.rag.get_statistics()
            raw_rows = await pilot.rag._graph_store.query_raw(
                "MATCH (n) RETURN labels(n) AS labels, n LIMIT 100")
            graph_rows = [(row[0], row[1].properties) for row in raw_rows.result_set]
            raw_rels = await pilot.rag._graph_store.query_raw(
                "MATCH ()-[r:RELATES]->() RETURN r LIMIT 100")
            relation_rows = [row[0].properties for row in raw_rels.result_set]
            snapshot_rows = await pilot.rag._graph_store.query_raw(
                "MATCH (s:HolisticSnapshot {digest:$digest}) RETURN s.finalized,s.pipeline",
                params={"digest": pilot.digest})
            reviewed = HolisticGraphPilot(
                corpus, graph_url,
                AdmittedLLM(DeterministicLLM(str(first.source_id), str(second.source_id),
                                             first.text, second.text), request, [approval], CallBudget(64)),
                AdmittedEmbedder(DeterministicEmbedder(), request, [approval], CallBudget(64)),
                config_id="fixed-synthetic-config-v1", dimensions=4)
            await reviewed.load_reviewed_snapshot()
            changed = Corpus(workspace_id=corpus.workspace_id,
                             sources=(first.model_copy(), second.model_copy(update={"revision": "r2"})),
                             expected_source_ids=corpus.expected_source_ids)
            changed_pilot = HolisticGraphPilot(
                changed, graph_url,
                AdmittedLLM(DeterministicLLM(str(first.source_id), str(second.source_id),
                                             first.text, second.text), request, [approval], CallBudget(64)),
                AdmittedEmbedder(DeterministicEmbedder(), request, [approval], CallBudget(64)),
                config_id="fixed-synthetic-config-v1", dimensions=4)
            try:
                with pytest.raises(RuntimeError, match="finalized snapshot|graph originals"):
                    await changed_pilot.load_reviewed_snapshot()
            finally:
                await changed_pilot.close()
            changed_config_pilot = HolisticGraphPilot(
                corpus, graph_url,
                AdmittedLLM(DeterministicLLM(str(first.source_id), str(second.source_id),
                                             first.text, second.text), request, [approval], CallBudget(64)),
                AdmittedEmbedder(DeterministicEmbedder(), request, [approval], CallBudget(64)),
                config_id="fixed-synthetic-config-v2", dimensions=4)
            try:
                with pytest.raises(RuntimeError, match="finalized snapshot|graph originals"):
                    await changed_config_pilot.load_reviewed_snapshot()
            finally:
                await changed_config_pilot.close()
            partial_sources = (_source(DOC_ONE, "partial-a.txt"), _source(DOC_TWO, "partial-b.txt"))
            partial = Corpus(workspace_id=uuid4(), sources=partial_sources,
                             expected_source_ids=frozenset(s.source_id for s in partial_sources))
            partial_pilot = HolisticGraphPilot(
                partial, graph_url,
                AdmittedLLM(DeterministicLLM(str(partial.sources[0].source_id),
                                             str(partial.sources[1].source_id), DOC_ONE, DOC_TWO),
                            request, [approval], CallBudget(64)),
                AdmittedEmbedder(DeterministicEmbedder(), request, [approval], CallBudget(64)),
                config_id="fixed-partial-config", dimensions=4)
            try:
                await partial_pilot.rag._graph_store.query_raw(
                    "CREATE (:PartialMarker {marker:'partial'})")
                with pytest.raises(RuntimeError, match="graph originals|finalized snapshot"):
                    await partial_pilot.build()
            finally:
                await partial_pilot.close()
            result = await pilot.answer("How does intake hand off to review, including the exception?", corpus)
            llm.grounding_supported = False
            with pytest.raises(ValueError, match="grounding and exception review"):
                await pilot.answer("How does intake hand off to review, including the exception?", corpus)
            await reviewed.close()
            return built, reused, result, retrieved, stats, graph_rows, relation_rows, snapshot_rows
        finally:
            await pilot.close()

    built, reused, result, retrieved, stats, graph_rows, relation_rows, snapshot_rows = asyncio.run(run())
    assert built["sdk_version"] == "1.4.0"
    assert reused["corpus_digest"] == built["corpus_digest"]
    assert built["receipts"] and all(item["chunks_indexed"] >= 1 for item in built["receipts"])
    assert all(built["finalized"]["indexes"].values())
    labels = [label for row in graph_rows for label in row[0]]
    assert labels.count("Document") == 2
    assert labels.count("Chunk") == 2
    assert sum("Review Team" in str(item.get("name", "")) for _, item in graph_rows) == 1
    assert stats["node_count"] >= 8
    assert stats["edge_count"] >= 8
    assert {"Document", "Chunk", "Role", "Exception"} <= set(stats["entity_types"])
    properties = [properties for _, properties in graph_rows]
    assert any(first.content_hash in str(item) for item in properties)
    assert any(second.content_hash in str(item) for item in properties)
    assert any(DOC_ONE in str(item) for item in properties)
    assert any(DOC_TWO in str(item) for item in properties)
    assert {item["rel_type"] for item in relation_rows} >= {"HANDOFF_TO", "EXCEPTION_TO"}
    assert snapshot_rows.result_set == [[True, "holistic-s03-1"]]
    assert retrieved.items
    assert result["source_count"] == 2
    assert {citation["source_id"] for statement in result["answer"]["explanation"]
            for citation in statement["citations"]} == {str(first.source_id), str(second.source_id)}
    assert len(llm.calls) >= 3  # two extraction calls, finalization/retrieval completion

