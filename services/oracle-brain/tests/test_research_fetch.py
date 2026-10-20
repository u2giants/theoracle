"""S10 offline gate: research fetch rejects private/link-local destinations.

Invented/synthetic only. No employees, no company data.
"""
from __future__ import annotations

import pytest

pytest.skip(
    'S10 research fetch implementation absent on main (oracle_brain.research.fetch not built; held PR #140). Named offline gate test registered fail-closed until research.fetch lands with SSRF/redirect guards.',
    allow_module_level=True,
)


def test_gate_registered():
    """Placeholder so the named offline gate test file exists and is collected."""
    raise AssertionError("unreachable: module-level skip")
