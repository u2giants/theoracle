"""Graph projection boundary. Postgres remains the authority."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class GraphStore(Protocol):
    def project(self, workspace_id: UUID, assertion_id: UUID, revision: int,
                payload: dict) -> None: ...

    def query(self, workspace_id: UUID, *, limit: int = 100) -> list[dict]: ...

    def withdraw(self, workspace_id: UUID, assertion_id: UUID,
                 revision: int) -> None: ...

    def rebuild(self, workspace_id: UUID, accepted: list[tuple[UUID, int, dict]]) -> None: ...
