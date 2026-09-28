import json
from pathlib import Path
from uuid import uuid4

import pytest

from oracle_brain.contracts import CandidateBundle, ProjectionReceipt, RunRequest


ROOT = Path(__file__).resolve().parents[3]


def test_generated_schema_is_current():
    for name, model in (("candidate-bundle", CandidateBundle),
                        ("projection-receipt", ProjectionReceipt),
                        ("run-request", RunRequest)):
        stored = json.loads((ROOT / "packages/brain-contracts/schema" /
                             f"{name}.schema.json").read_text())
        assert stored == model.model_json_schema()


def test_candidate_source_revision_and_span_must_match():
    source_id, workspace_id, run_id = uuid4(), uuid4(), uuid4()
    base = dict(contract_version=1, workspace_id=workspace_id, run_id=run_id, source_id=source_id,
                source_revision=2)
    assertion = dict(assertion_id=uuid4(), subject="A", predicate="approves",
                     object="B", confidence=0.8,
                     span=dict(source_id=source_id, source_revision=1,
                               start=0, end=2, quote="AB"))
    with pytest.raises(ValueError):
        CandidateBundle(**base, assertions=[assertion])


def test_cross_language_contract_fixtures():
    contracts = {"candidateBundle": CandidateBundle,
                 "projectionReceipt": ProjectionReceipt, "runRequest": RunRequest}
    fixtures = json.loads((ROOT / "packages/brain-contracts/schema/parity-fixtures.json").read_text())
    assert len(fixtures) >= 6
    for fixture in fixtures:
        try:
            contracts[fixture["contract"]].model_validate_json(json.dumps(fixture["value"]))
            actual = True
        except ValueError:
            actual = False
        assert actual == fixture["valid"]
