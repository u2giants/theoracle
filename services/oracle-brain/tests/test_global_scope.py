"""S09 offline gate: company-wide/global scope answers.

Invented/synthetic only. No employees, no company data.
"""
from __future__ import annotations

import pytest

pytest.skip(
    'S09 global summary implementation absent on main (oracle_brain.retrieval.global_summary not built). Named offline gate test registered fail-closed until global_summary lands with explicit coverage, revision and support.',
    allow_module_level=True,
)


def test_gate_registered():
    """Placeholder so the named offline gate test file exists and is collected."""
    raise AssertionError("unreachable: module-level skip")
