"""Small domain records that remain independent of the graph library."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProjectionEvent:
    event_id: UUID
    workspace_id: UUID
    assertion_id: UUID
    revision: int
    operation: str
    payload: dict
    attempts: int = 0
