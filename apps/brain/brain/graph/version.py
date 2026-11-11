"""The current map version: the newest graph version that has reports.

Reports are reused across builds by stamping them with the new version
(``communities.run_communities``), so "current" means every report the
latest build selected. Answers, the map API and recommendations all read
through this one helper so none of them can see a superseded report.
"""

from __future__ import annotations

from typing import Any


def current_graph_version(conn: Any) -> int | None:
    """The newest graph version that has communities, or None when empty."""
    row = conn.execute("SELECT MAX(graph_version) FROM cmap.community").fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])
