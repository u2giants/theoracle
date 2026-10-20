"""S09 offline gate: MCP and web permission-boundary parity.

Invented/synthetic only. No employees, no company data.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.retrieval.mcp_parity import (
    PermissionBoundary,
    READ_TOOL_NAMES,
    WRITE_TOOL_NAMES,
    McpSourceRecord,
    check_tool,
    mcp_retrieval_visible,
    parity_report,
    web_retrieval_visible,
)
from oracle_brain.retrieval.planner import AccessBounds


@pytest.fixture()
def workspace():
    return uuid4()


@pytest.fixture()
def access(workspace) -> AccessBounds:
    return AccessBounds(
        role="analyst",
        workspace_id=workspace,
        allowed_workspace_ids=(workspace,),
    )


def _source(
    *,
    workspace_id=None,
    roles=("analyst",),
    source_id=None,
) -> McpSourceRecord:
    return McpSourceRecord(
        source_id=source_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        roles=roles,
    )


def test_read_tools_allowed_write_tools_refused():
    for name in sorted(READ_TOOL_NAMES):
        assert check_tool(name).decision == "allowed"
    for name in sorted(WRITE_TOOL_NAMES):
        check = check_tool(name)
        assert check.decision == "refused"
        assert "read-only" in check.reason
    assert check_tool("drop_database").decision == "refused"


def test_empty_tool_name_raises():
    with pytest.raises(ValueError):
        check_tool("   ")


def test_access_bounds_filter_drops_other_workspace_and_role(workspace, access):
    mine = _source(workspace_id=workspace)
    other_ws = _source(workspace_id=uuid4())
    other_role = _source(workspace_id=workspace, roles=("viewer",))
    visible = mcp_retrieval_visible((mine, other_ws, other_role), access)
    assert [s.source_id for s in visible] == [mine.source_id]


def test_denied_source_is_refused_by_boundary(workspace, access):
    denied = _source(workspace_id=uuid4())
    boundary = PermissionBoundary(access=access)
    check = boundary.check_source(denied)
    assert check.decision == "denied"
    assert "denied" in check.reason
    allowed = _source(workspace_id=workspace)
    assert boundary.check_source(allowed).decision == "visible"


def test_web_and_mcp_boundaries_are_identical(workspace):
    second = uuid4()
    bounds = AccessBounds(
        role="analyst",
        workspace_id=workspace,
        allowed_workspace_ids=(workspace, second),
    )
    sources = (
        _source(workspace_id=workspace),
        _source(workspace_id=second),
        _source(workspace_id=uuid4()),
        _source(workspace_id=workspace, roles=("viewer",)),
    )
    web_ids = {s.source_id for s in web_retrieval_visible(sources, bounds)}
    mcp_ids = {s.source_id for s in mcp_retrieval_visible(sources, bounds)}
    assert web_ids == mcp_ids
    assert len(web_ids) == 2


def test_parity_report_aligned_and_denied_match(workspace, access):
    sources = (
        _source(workspace_id=workspace),
        _source(workspace_id=uuid4()),
        _source(workspace_id=workspace, roles=("admin",)),
    )
    report = parity_report(sources=sources, access=access)
    assert report.aligned
    assert report.web_visible == report.mcp_visible
    assert report.web_denied == report.mcp_denied
    assert len(report.web_visible) == 1
    assert len(report.web_denied) == 2


def test_boundary_requires_workspace_in_allowlist():
    workspace = uuid4()
    other = uuid4()
    with pytest.raises(ValueError):
        AccessBounds(
            role="analyst",
            workspace_id=other,
            allowed_workspace_ids=(workspace,),
        )
