#!/usr/bin/env python3
"""Generate shared JSON schemas from the locked Python Pydantic contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "oracle-brain"))
from oracle_brain.contracts import CandidateBundle, ProjectionReceipt, RunRequest  # noqa: E402


def main() -> None:
    target = ROOT / "packages" / "brain-contracts" / "schema"
    target.mkdir(parents=True, exist_ok=True)
    for name, model in (("candidate-bundle", CandidateBundle),
                        ("projection-receipt", ProjectionReceipt),
                        ("run-request", RunRequest)):
        (target / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        )


if __name__ == "__main__":
    main()
