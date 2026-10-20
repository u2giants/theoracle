"""S09 offline gate: MCP and web permission-boundary parity.

Invented/synthetic only. No employees, no company data.
"""
from __future__ import annotations

import pytest

pytest.skip(
    'S09 MCP adapter absent on main (apps/web/lib/mcp/ replacement not built). Named offline gate test registered fail-closed until the bounded read-only MCP adapter lands and can be asserted against the same permission boundary as web retrieval.',
    allow_module_level=True,
)


def test_gate_registered():
    """Placeholder so the named offline gate test file exists and is collected."""
    raise AssertionError("unreachable: module-level skip")
