"""Confirmed graph projection, partitioned by workspace and revision."""

from __future__ import annotations

import json
from urllib.parse import urlparse
from uuid import UUID

from falkordb import FalkorDB


class FalkorGraphStore:
    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("invalid FalkorDB URL")
        self.client = FalkorDB(host=parsed.hostname, port=parsed.port or 6379,
                               password=parsed.password,
                               ssl=parsed.scheme == "rediss")

    @staticmethod
    def _name(workspace_id: UUID) -> str:
        return f"oracle2_{workspace_id.hex}"

    def _graph(self, workspace_id: UUID):
        return self.client.select_graph(self._name(workspace_id))

    def project(self, workspace_id: UUID, assertion_id: UUID, revision: int,
                payload: dict) -> None:
        if revision < 1:
            raise ValueError("revision must be positive")
        graph = self._graph(workspace_id)
        row = graph.query(
            "MATCH (a:Assertion {id:$id}) RETURN a.revision",
            params={"id": str(assertion_id)},
        ).result_set
        if row and int(row[0][0]) >= revision:
            return
        graph.query(
            """MERGE (a:Assertion {id:$id})
               SET a.revision=$revision,a.payload=$payload,a.active=true""",
            params={"id": str(assertion_id), "revision": revision,
                    "payload": json.dumps(payload, sort_keys=True)},
        )

    def query(self, workspace_id: UUID, *, limit: int = 100) -> list[dict]:
        if limit < 1 or limit > 1000:
            raise ValueError("query limit must be 1..1000")
        rows = self._graph(workspace_id).query(
            "MATCH (a:Assertion) WHERE a.active=true RETURN a.id,a.revision,a.payload LIMIT $limit",
            params={"limit": limit},
        ).result_set
        return [{"assertion_id": UUID(row[0]), "revision": int(row[1]),
                 "payload": json.loads(row[2])} for row in rows]

    def withdraw(self, workspace_id: UUID, assertion_id: UUID, revision: int) -> None:
        if revision < 1:
            raise ValueError("revision must be positive")
        graph = self._graph(workspace_id)
        row = graph.query("MATCH (a:Assertion {id:$id}) RETURN a.revision",
                          params={"id": str(assertion_id)}).result_set
        if row and int(row[0][0]) >= revision:
            return
        graph.query(
            "MERGE (a:Assertion {id:$id}) SET a.revision=$revision,a.active=false",
            params={"id": str(assertion_id), "revision": revision},
        )

    def rebuild(self, workspace_id: UUID,
                accepted: list[tuple[UUID, int, dict]]) -> None:
        graph = self._graph(workspace_id)
        graph.query("MATCH (n) DETACH DELETE n")
        for assertion_id, revision, payload in accepted:
            self.project(workspace_id, assertion_id, revision, payload)
