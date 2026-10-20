"""Bounded read-only MCP adapter parity surface; pure, fixture-only.

Defines the same permission boundary as web retrieval: access bounds filter
(allowed workspaces plus role) and explicit refusal of denied sources. The
adapter is read-only — write tool names are refused. Both the web-retrieval
side and the MCP side delegate to one boundary so parity is assertable
offline. No live MCP server, no provider calls, no I/O.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from ..operating_model.source_receipts import _StrictModel
from .planner import AccessBounds

# Always-on / hidden read tools mirrored from the legacy apps/web/lib/mcp surface.
READ_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "health",
        "list_capabilities",
        "tool_search",
        "get_capability_details",
        "invoke_tool",
        "search_business_knowledge",
        "list_knowledge_domains",
        "list_brain_sections",
        "get_brain_section",
    }
)

# Names that would mutate state; refused by the read-only adapter.
WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "create_claim",
        "update_claim",
        "delete_claim",
        "write_brain",
        "publish_claim",
        "delete_source",
    }
)

ToolDecision = Literal["allowed", "refused"]
ReadDecision = Literal["visible", "denied"]


class McpSourceRecord(_StrictModel):
    """One fixture source with the bounds the permission boundary must honor."""
    schema_version: Literal[1] = 1
    source_id: UUID
    workspace_id: UUID
    roles: tuple[str, ...] = Field(min_length=1)


class ToolCheck(_StrictModel):
    schema_version: Literal[1] = 1
    tool_name: str = Field(min_length=1)
    decision: ToolDecision
    reason: str


class SourceCheck(_StrictModel):
    schema_version: Literal[1] = 1
    source_id: UUID
    decision: ReadDecision
    reason: str


class PermissionBoundary(_StrictModel):
    """Single source of truth shared by web retrieval and the MCP adapter."""
    schema_version: Literal[1] = 1
    access: AccessBounds

    def allows_source(self, source: McpSourceRecord) -> bool:
        allowed = set(self.access.allowed_workspace_ids)
        return source.workspace_id in allowed and self.access.role in source.roles

    def filter_visible(
        self, sources: tuple[McpSourceRecord, ...] | list[McpSourceRecord],
    ) -> tuple[McpSourceRecord, ...]:
        return tuple(source for source in sources if self.allows_source(source))

    def check_source(self, source: McpSourceRecord) -> SourceCheck:
        if self.allows_source(source):
            return SourceCheck(
                source_id=source.source_id,
                decision="visible",
                reason="source inside role/workspace access bounds",
            )
        return SourceCheck(
            source_id=source.source_id,
            decision="denied",
            reason="source denied by role/workspace access bounds",
        )


def check_tool(tool_name: str) -> ToolCheck:
    """Read-only gate: read tools allowed, write and unknown tools refused."""
    if not tool_name.strip():
        raise ValueError("tool_name must be non-empty")
    if tool_name in WRITE_TOOL_NAMES:
        return ToolCheck(
            tool_name=tool_name,
            decision="refused",
            reason="write tool refused by read-only MCP adapter",
        )
    if tool_name in READ_TOOL_NAMES:
        return ToolCheck(
            tool_name=tool_name,
            decision="allowed",
            reason="read-only tool inside bounded adapter surface",
        )
    return ToolCheck(
        tool_name=tool_name,
        decision="refused",
        reason="unknown tool refused by read-only MCP adapter",
    )


def web_retrieval_visible(
    sources: tuple[McpSourceRecord, ...] | list[McpSourceRecord],
    access: AccessBounds,
) -> tuple[McpSourceRecord, ...]:
    """Web-retrieval permission boundary: same rule as packing.filter_by_access."""
    return PermissionBoundary(access=access).filter_visible(sources)


def mcp_retrieval_visible(
    sources: tuple[McpSourceRecord, ...] | list[McpSourceRecord],
    access: AccessBounds,
) -> tuple[McpSourceRecord, ...]:
    """MCP adapter permission boundary: identical to the web-retrieval side."""
    return PermissionBoundary(access=access).filter_visible(sources)


class ParityReport(_StrictModel):
    """Offline parity assertion result for one access bound and source set."""
    schema_version: Literal[1] = 1
    aligned: bool
    web_visible: tuple[UUID, ...] = ()
    mcp_visible: tuple[UUID, ...] = ()
    web_denied: tuple[UUID, ...] = ()
    mcp_denied: tuple[UUID, ...] = ()


def parity_report(
    *,
    sources: tuple[McpSourceRecord, ...] | list[McpSourceRecord],
    access: AccessBounds,
) -> ParityReport:
    """Compare web-retrieval and MCP adapter decisions on the same inputs."""
    boundary = PermissionBoundary(access=access)
    web_visible = web_retrieval_visible(sources, access)
    mcp_visible = mcp_retrieval_visible(sources, access)
    web_ids = tuple(source.source_id for source in web_visible)
    mcp_ids = tuple(source.source_id for source in mcp_visible)
    denied = tuple(
        source.source_id for source in sources if not boundary.allows_source(source)
    )
    return ParityReport(
        aligned=web_ids == mcp_ids,
        web_visible=web_ids,
        mcp_visible=mcp_ids,
        web_denied=denied,
        mcp_denied=denied,
    )
