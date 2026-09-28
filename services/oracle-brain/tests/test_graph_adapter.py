from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from oracle_brain.graph.falkor import FalkorGraphStore
from oracle_brain.graph.graphiti_candidates import ExtractedRelation, candidate_bundle
import pytest


def test_project_query_withdraw_rebuild_and_workspace_isolation(confirmed_url):
    graph = FalkorGraphStore(confirmed_url)
    w1, w2, assertion = uuid4(), uuid4(), uuid4()
    graph.project(w1, assertion, 1, {"kind": "synthetic"})
    assert graph.query(w1) == [{"assertion_id": assertion, "revision": 1,
                                "payload": {"kind": "synthetic"}}]
    assert graph.query(w2) == []
    graph.project(w1, assertion, 1, {"kind": "forged-stale"})
    assert graph.query(w1)[0]["payload"]["kind"] == "synthetic"
    graph.withdraw(w1, assertion, 2)
    assert graph.query(w1) == []
    graph.rebuild(w1, [(assertion, 3, {"kind": "replayed"})])
    assert graph.query(w1)[0]["revision"] == 3
    assert graph.query(w2) == []


def test_candidate_exact_span_rejects_graphiti_style_unanchored_fact():
    source_id, workspace, run = uuid4(), uuid4(), uuid4()
    with pytest.raises(ValueError, match="exact source-span"):
        candidate_bundle(workspace_id=workspace, run_id=run, source_id=source_id,
                         source_revision=1, source_text="Design approves sample.",
                         relations=[ExtractedRelation(subject="Design", predicate="approves",
                                                      object="sample", quote="Design approves sample",
                                                      start=1, end=23, confidence=.8)])
    accepted = candidate_bundle(workspace_id=workspace, run_id=run,
                                source_id=source_id, source_revision=1,
                                source_text="Design approves sample.",
                                relations=[ExtractedRelation(subject="Design", predicate="approves",
                                                             object="sample", quote="Design approves sample",
                                                             start=0, end=22, confidence=.8)])
    assert accepted.assertions[0].span.quote == "Design approves sample"


def test_candidate_correction_cannot_invalidate_confirmed(candidate_url, confirmed_url):
    workspace, assertion = uuid4(), uuid4()
    candidate = FalkorGraphStore(candidate_url)
    confirmed = FalkorGraphStore(confirmed_url)
    confirmed.project(workspace, assertion, 1, {"fact": "confirmed"})
    candidate.project(workspace, assertion, 1, {"fact": "unreviewed"})
    candidate.withdraw(workspace, assertion, 2)
    assert candidate.query(workspace) == []
    assert confirmed.query(workspace) == [{"assertion_id": assertion, "revision": 1,
                                           "payload": {"fact": "confirmed"}}]


def test_concurrent_old_projection_cannot_override_new(confirmed_url):
    graph = FalkorGraphStore(confirmed_url)
    workspace, assertion = uuid4(), uuid4()
    graph.project(workspace, assertion, 1, {"revision": 1})
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(graph.project, workspace, assertion, revision,
                               {"revision": revision}) for revision in (2, 3, 4, 5, 2, 3, 4, 5)]
        for future in futures:
            future.result()
    assert graph.query(workspace) == [{"assertion_id": assertion, "revision": 5,
                                       "payload": {"revision": 5}}]
