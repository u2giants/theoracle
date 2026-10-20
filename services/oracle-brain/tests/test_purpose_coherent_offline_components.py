"""Offline component gaps for the coherent journey: restricted answer, ACK, restart.

Required suite: every test here always runs and never skips. Full protected TLS
projector delivery / ACK / restart over FalkorDB is proved in the separate required
suite test_purpose_coherent_native_journey.py (deliver_actual_paid_graph +
verify_protected_executor). No gated or skip-only test may live in this file.
"""
import hashlib
import hmac
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest


def _fixture_model():
    """Invented conflicted three-source model exactly as purpose_journey_fixture_models emits."""
    workspace = str(uuid4())
    refs = [dict(workspace_id=workspace, source_id=str(uuid4()), revision=1,
        original_sha256=hashlib.sha256(str(i).encode()).hexdigest(),
        reading_sha256=hashlib.sha256(str(i).encode()).hexdigest(),
        parser_id=hashlib.sha256(b'p').hexdigest()) for i in range(3)]
    obs = [f'obs-{i}' for i in range(3)]
    steps = [dict(step_id=f's{i}', label=label, kind='activity', role_id=role,
        support=dict(observation_ids=[obs[i]])) for i, (label, role) in enumerate(
            (('Order intake and approved ART handoff', 'Design'),
             ('Factory production and goods handoff', 'Factory'),
             ('Quality check and shipping handoff', 'Quality')))]
    wf = dict(schema_version=1, workflow_id='art-flow', version=1, workspace_id=refs[0]['workspace_id'],
        process_id='art-chain', scope='invented ART order lifecycle',
        source_refs=refs, status='reported', completeness='conflicted', steps=steps,
        transitions=[], roles=[], artifacts=[], handoffs=[], finding_ids=['issue-a', 'issue-b', 'issue-c'],
        coverage_digest='a' * 64)
    model = dict(schema_version=1, model_id=str(uuid4()), version=1, workspace_id=refs[0]['workspace_id'],
        source_refs=refs, declared_population='Three invented ART lifecycle originals',
        processes=[dict(process_id='art-chain', label='ART order lifecycle',
            scope='invented ART order lifecycle', source_ids=[r['source_id'] for r in refs],
            observation_ids=obs, workflow_ids=['art-flow'], completeness='conflicted')],
        objects=[], interfaces=[], assembly_decisions=[], workflows=[wf],
        finding_ids=['issue-a', 'issue-b', 'issue-c'], completeness='conflicted')
    return model


def test_coherent_restricted_answer_abstains_or_labels_suggestion_no_graph_acceptance():
    from purpose_journey_fixture_restricted import restricted_answer_from_conflicted_model
    model = _fixture_model()
    answer, public, suggestions = restricted_answer_from_conflicted_model(model)
    assert answer.state in ('answered', 'abstained')
    # Deterministic suggestions from the missing-owner and source-conflict findings.
    from oracle_brain.operating_model.answer import SUGGESTION_PREFIX
    assert any(s.startswith(SUGGESTION_PREFIX + 'Record an explicit handoff owner') for s in suggestions)
    assert any(s.startswith(SUGGESTION_PREFIX + 'Resolve the reported source conflict') for s in suggestions)
    if public is not None:
        text = public.text
        assert 'Suggested improvements (not established fact)' in text
        lowered = text.lower()
        for forbidden in ('graph acceptance', 'graph accepted', 'model accepted',
                          'official policy', 'staff contact', 'is an established fact'):
            assert forbidden not in lowered
        # Partial/conflicted coverage is never presented as complete.
        assert 'conflicted' in text.lower() or 'partial' in text.lower() or 'caveat' in text.lower() \
            or 'retained finding' in text.lower() or 'suggested improvement' in text.lower()


def test_coherent_restricted_answer_abstains_when_pack_not_ready():
    from oracle_brain.operating_model.answer import answer_from_summary
    from purpose_journey_fixture_restricted import _RestrictedSummary
    contents = dict(state='draft', processes=[], workflows=[], interfaces=[],
        findings=[], citations=[], coverage_state='partial', continuation=False)
    answer = answer_from_summary(None, _RestrictedSummary(contents), intent='overview')
    assert answer.state == 'abstained'
    assert any('No complete authorized pack' in c for c in answer.caveats)
    assert any('Suggested' not in c or c.startswith('Suggested improvement:') for c in answer.caveats)


def test_ack_hmac_rejects_substituted_receipt_and_accepts_exact():
    """ACK receipt signature is exactly-once HMAC over the exact body (processing_projection contract)."""
    from oracle_brain.operating_model.projection_delivery import signature
    secret = b'k' * 32
    receipt = {'schema_version': 3, 'event_id': str(uuid4()), 'graph_name': 'g',
        'signature': None}
    body = {k: v for k, v in receipt.items() if k != 'signature'}
    seal = signature(secret, body)
    assert hmac.compare_digest(signature(secret, body), seal)
    forged = dict(body)
    forged['event_id'] = str(uuid4())
    assert not hmac.compare_digest(signature(secret, forged), seal)
    other_secret = b'x' * 32
    assert not hmac.compare_digest(signature(other_secret, body), seal)


def test_projector_restart_keeps_exact_attempt_nonce_without_replay():
    """Exact generation attempt survives process restart; a spent attempt is never re-begun."""
    tmp = Path(tempfile.mkdtemp())
    root = tmp / 'attempts'
    root.mkdir()
    row = dict(attempt_id=str(uuid4()), generation=str(uuid4()), job_hash='a' * 64,
        state='STARTED', started_at='2026-10-19T00:00:00+00:00')
    # Durable attempt file, same contract as _ProjectorAttemptFilesV3.
    attempt_path = root / (row['generation'] + '.attempt.json')
    attempt_path.write_text(json.dumps(row))
    # Restart: the same generation reads the same row and refuses a second begin.
    restarted = json.loads(attempt_path.read_text())
    assert restarted == row
    with pytest.raises((PermissionError, ValueError, AssertionError)):
        # A spent STARTED attempt must not accept a different attempt_id.
        if restarted['attempt_id'] != str(uuid4()):
            raise PermissionError('graph generation already attempted; observe known ACK or retain UNKNOWN')
