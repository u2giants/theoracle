from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from graphrag_sdk.core.models import (GraphData, GraphNode, GraphRelationship,
                                      LLMResponse, TextChunk, TextChunks)
from graphrag_sdk.core.providers import Embedder, LLMInterface

from oracle_brain.graph.graphrag import (
    AdmittedEmbedder,
    AdmittedLLM,
    CallBudget,
    Corpus,
    CorpusSource,
    HolisticGraphPilot,
    HolisticAnswer,
    EvidenceCitation,
    PreserveReportedRelations,
    ProcessExtraction,
    WholeDocumentChunks,
)
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest


def source(text: str, *, source_id: UUID | None = None, revision: str = "r1") -> CorpusSource:
    return CorpusSource(source_id=source_id or uuid4(), revision=revision,
                        filename="fixture.txt", text=text,
                        content_hash=hashlib.sha256(text.encode()).hexdigest(), complete=True)


def source_with_provenance(text: str, *, original_hash: str | None = None,
                           parser_identity: str = "native-text-v1",
                           evidence_kind: str = "native_text") -> CorpusSource:
    return CorpusSource(source_id=uuid4(), revision="r1", filename="fixture.txt", text=text,
                        content_hash=hashlib.sha256(text.encode()).hexdigest(), complete=True,
                        original_hash=original_hash, parser_identity=parser_identity,
                        evidence_kind=evidence_kind)


def corpus(*texts: str) -> Corpus:
    items = tuple(source(text) for text in texts)
    return Corpus(workspace_id=uuid4(), sources=items,
                  expected_source_ids=frozenset(item.source_id for item in items))


def request_and_approval(*, provider: str = "local-synthetic"):
    request = ProcessingRequest(provider=provider, account="test", endpoint="http://127.0.0.1",
                                data_classes=frozenset({"synthetic"}), purpose="holistic-test",
                                terms_hash="a" * 64)
    approval = ProcessingApproval(**request.model_dump(),
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                                  register_ref="test-fixture")
    return request, approval


class FixedLLM(LLMInterface):
    def __init__(self, content: str):
        super().__init__("fixed-synthetic", max_concurrency=1)
        self.content = content
        self.calls = 0

    def invoke(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content=self.content)


class FixedEmbedder(Embedder):
    model_name = "fixed-embedder"

    def embed_query(self, text: str, **kwargs):
        return [0.0, 1.0, 0.0, 1.0]


def test_corpus_requires_complete_hashed_two_source_inventory_and_budget():
    first, second = source("step one"), source("step two")
    valid = Corpus(workspace_id=uuid4(), sources=(first, second),
                   expected_source_ids=frozenset({first.source_id, second.source_id}))
    assert len(valid.digest("config-v1")) == 64
    assert valid.digest("config-v1") != valid.digest("config-v2")

    with pytest.raises(ValueError, match="source hash mismatch"):
        CorpusSource(source_id=uuid4(), revision="r1", filename="x", text="real",
                     content_hash="0" * 64, complete=True)
    with pytest.raises(ValueError, match="incomplete source"):
        CorpusSource(source_id=uuid4(), revision="r1", filename="x", text="partial",
                     content_hash=hashlib.sha256(b"partial").hexdigest(), complete=False)
    with pytest.raises(ValueError, match="multi-document"):
        Corpus(workspace_id=uuid4(), sources=(first,), expected_source_ids=frozenset({first.source_id}))
    with pytest.raises(ValueError, match="multi-document"):
        Corpus(workspace_id=uuid4(), sources=(first, first),
               expected_source_ids=frozenset({first.source_id}))
    oversized = (source("x" * 250_001), source("y" * 250_001))
    with pytest.raises(ValueError, match="whole-context budget"):
        Corpus(workspace_id=uuid4(), sources=oversized,
               expected_source_ids=frozenset(item.source_id for item in oversized))


def test_corpus_requires_distinct_originals_and_rejects_conflicting_alias_readings():
    original_hash = hashlib.sha256(b"one original").hexdigest()
    first = source_with_provenance("one reading", original_hash=original_hash,
                                   parser_identity="a" * 64, evidence_kind="visual_transcription")
    alias = source_with_provenance("one reading", original_hash=original_hash,
                                   parser_identity="a" * 64, evidence_kind="visual_transcription")
    with pytest.raises(ValueError, match="distinct original"):
        Corpus(workspace_id=uuid4(), sources=(first, alias),
               expected_source_ids=frozenset({first.source_id, alias.source_id}))

    conflicting = source_with_provenance("different reading", original_hash=original_hash,
                                         parser_identity="b" * 64, evidence_kind="visual_transcription")
    with pytest.raises(ValueError, match="conflicting readings"):
        Corpus(workspace_id=uuid4(), sources=(first, conflicting),
               expected_source_ids=frozenset({first.source_id, conflicting.source_id}))


def test_corpus_digest_binds_original_provenance():
    first, second = source("step one"), source("step two")
    base = Corpus(workspace_id=uuid4(), sources=(first, second),
                  expected_source_ids=frozenset({first.source_id, second.source_id}))
    changed = first.model_copy(update={"original_hash": "c" * 64,
                                      "parser_identity": "d" * 64,
                                      "evidence_kind": "visual_transcription"})
    changed_corpus = Corpus(workspace_id=base.workspace_id, sources=(changed, second),
                            expected_source_ids=base.expected_source_ids)
    assert changed_corpus.digest("config-v1") != base.digest("config-v1")


def test_citations_reject_foreign_source_offsets_and_fake_quotes():
    first, second = source("Warehouse hands the packet to Design."), source("Design reviews the packet.")
    c = Corpus(workspace_id=uuid4(), sources=(first, second),
               expected_source_ids=frozenset({first.source_id, second.source_id}))
    answer = HolisticAnswer(explanation=[{"text": "handoff", "citations": [{
        "source_id": first.source_id, "quote": "Warehouse", "span_start": 0, "span_end": 9}]}],
        conflicts=[], unknowns=[], hypothetical_improvements=[])
    assert answer.validate_evidence(c)
    for bad in (
        {"source_id": second.source_id, "quote": "Warehouse", "span_start": 0, "span_end": 9},
        {"source_id": first.source_id, "quote": "invented", "span_start": 0, "span_end": 8},
    ):
        invalid = answer.model_copy(deep=True)
        invalid.explanation[0].citations[0] = EvidenceCitation(**bad)
        with pytest.raises(ValueError, match="invented or stale"):
            invalid.validate_evidence(c)

    derived = HolisticAnswer(explanation=[{"text": "handoff", "citations": [{
        "source_id": first.source_id, "quote": "Warehouse hands",}]}],
        conflicts=[], unknowns=[], hypothetical_improvements=[]).validate_evidence(c)
    assert derived.explanation[0].citations[0].span_start == 0
    assert derived.explanation[0].citations[0].span_end == len("Warehouse hands")

    repeated = source("Warehouse hands twice: Warehouse hands")
    repeated_corpus = Corpus(workspace_id=uuid4(), sources=(first, repeated),
                             expected_source_ids=frozenset({first.source_id, repeated.source_id}))
    ambiguous = HolisticAnswer(explanation=[{"text": "ambiguous", "citations": [{
        "source_id": repeated.source_id, "quote": "Warehouse hands"}]}],
        conflicts=[], unknowns=[], hypothetical_improvements=[])
    with pytest.raises(ValueError, match="ambiguous"):
        ambiguous.validate_evidence(repeated_corpus)


def test_provider_denial_happens_before_delegate_and_budget_is_enforced():
    request, approval = request_and_approval()
    delegate = FixedLLM("")
    denied = AdmittedLLM(delegate, request.model_copy(update={"terms_hash": "b" * 64}), [approval], CallBudget())
    with pytest.raises(PermissionError):
        denied.invoke("private")
    assert delegate.calls == 0

    budget = CallBudget(max_calls=1)
    admitted = AdmittedLLM(delegate, request, [approval], budget)
    admitted.invoke("first")
    with pytest.raises(RuntimeError, match="budget exhausted"):
        admitted.invoke("second")
    assert delegate.calls == 1


def test_admitted_embedder_batches_once_and_denies_before_delegate():
    request, approval = request_and_approval()
    delegate = FixedEmbedder()
    admitted = AdmittedEmbedder(delegate, request, [approval], CallBudget(max_calls=1))
    assert admitted.embed_documents(["one", "two"]) == [[0.0, 1.0, 0.0, 1.0]] * 2
    with pytest.raises(RuntimeError, match="budget exhausted"):
        admitted.embed_documents(["three"])
    denied = AdmittedEmbedder(delegate, request.model_copy(update={"terms_hash": "b" * 64}),
                              [approval], CallBudget())
    with pytest.raises(PermissionError):
        denied.embed_documents(["private"])


def test_chunking_is_lossless_and_extracts_once_with_cross_boundary_provenance():
    prefix = "A" * 1995
    quote = "CROSS-BOUNDARY-EVIDENCE"
    text = prefix + quote + "\n" + ("B" * 2050)
    chunks = asyncio.run(WholeDocumentChunks().chunk(text, None))
    assert "".join(chunk.text for chunk in chunks.chunks) == text
    assert all(len(chunk.text) <= 2000 for chunk in chunks.chunks)
    payload = {"objects": [{"key": "boundary", "kind": "Rule", "name": "Boundary rule",
                             "scope": "licensed", "description": "spans windows", "quote": quote}],
               "links": [], "missing_information": [], "conflicts": []}
    llm = FixedLLM(json.dumps(payload))
    data = asyncio.run(ProcessExtraction(llm).extract(chunks, None, None))
    assert llm.calls == 1
    assert data.nodes[0].properties["evidence_quote"] == quote
    assert len(data.nodes[0].properties["source_chunk_ids"]) == 2
    assert {mention.chunk_id for mention in data.mentions} == set(data.nodes[0].properties["source_chunk_ids"])


def test_process_extraction_uses_sdk_types_scopes_unknowns_and_rejects_unsupported_links():
    chunk = TextChunk(text="Dispatch sends the packet. Design reviews the packet.", index=0, uid="chunk-fixed")
    payload = {
        "objects": [
            {"key": "dispatch", "kind": "Role", "name": "Dispatch", "scope": "unknown",
             "description": "sender", "quote": "Dispatch"},
            {"key": "review", "kind": "Step", "name": "reviews", "scope": "licensed",
             "description": "review step", "quote": "reviews the packet"},
        ],
        "links": [{"source": "dispatch", "target": "review", "kind": "PRECEDES",
                    "description": "dispatch precedes review", "quote": "sends the packet"}],
        "missing_information": ["owner approval date"], "conflicts": [],
    }
    llm = FixedLLM(json.dumps(payload))
    result = asyncio.run(ProcessExtraction(llm).extract(TextChunks(chunks=[chunk]), None, None))
    assert len(result.nodes) == 2 and len(result.relationships) == 1
    assert any("unknown:chunk-fixed" in node.properties["name"] for node in result.nodes)
    assert result.relationships[0].properties["rel_type"] == "PRECEDES"
    assert llm.calls == 1

    bad = dict(payload, links=[{"source": "dispatch", "target": "review", "kind": "MADE_UP",
                                "description": "unsupported", "quote": "sends the packet"}])
    with pytest.raises(ValueError, match="unsupported relationship"):
        asyncio.run(ProcessExtraction(FixedLLM(json.dumps(bad))).extract(
            TextChunks(chunks=[chunk]), None, None))


def test_resolver_preserves_relation_types_and_scoped_same_names():
    nodes = [
        GraphNode(id="a", label="Role", properties={"name": "Owner [sales]", "scope": "sales"}),
        GraphNode(id="b", label="Role", properties={"name": "Owner [warehouse]", "scope": "warehouse"}),
    ]
    relationships = [
        GraphRelationship(start_node_id="a", end_node_id="b", type="RELATES",
                          properties={"rel_type": "HANDOFF_TO"}),
        GraphRelationship(start_node_id="a", end_node_id="b", type="RELATES",
                          properties={"rel_type": "CONTRADICTS"}),
    ]
    result = asyncio.run(PreserveReportedRelations().resolve(
        GraphData(nodes=nodes, relationships=relationships, mentions=[]), None))
    assert {item.properties["rel_type"] for item in result.relationships} == {
        "HANDOFF_TO", "CONTRADICTS"}
    assert {item.properties["scope"] for item in result.nodes} == {"sales", "warehouse"}


def test_pilot_has_no_legacy_fallback_and_rejects_changed_corpus_before_answer():
    c = corpus("Dispatch sends the packet.", "Design reviews the packet.")
    request, approval = request_and_approval()
    llm = AdmittedLLM(FixedLLM("{}"), request, [approval], CallBudget())
    pilot = HolisticGraphPilot(c, "redis://127.0.0.1:1", llm,
                               AdmittedEmbedder(FixedEmbedder(), request, [approval], CallBudget()),
                               config_id="config-v1", dimensions=4)
    with pytest.raises(RuntimeError, match="must be built"):
        asyncio.run(pilot.answer("How does the handoff work?", c))
    pilot.ready = True
    changed = Corpus(workspace_id=c.workspace_id,
                     sources=(c.sources[0], source("Design rejects the packet.",
                                                   source_id=c.sources[1].source_id, revision="r2")),
                     expected_source_ids=c.expected_source_ids)
    with pytest.raises(RuntimeError, match="must be built"):
        asyncio.run(pilot.answer("How does the handoff work?", changed))
