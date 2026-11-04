"""Offline resolver regressions; run directly with Python, without Postgres.

Load only the definitions under test so database/provider imports and the
integration suite's database fixtures are not required.
"""
from __future__ import annotations

import ast
import logging
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

SOURCE = Path(__file__).parents[1] / "brain/resolve/resolve.py"


def definitions(*names, **namespace):
    tree = ast.parse(SOURCE.read_text())
    tree.body = [node for node in tree.body if getattr(node, "name", None) in names]
    scope = {"threading": threading, **namespace}
    exec(compile(tree, str(SOURCE), "exec"), scope)
    return SimpleNamespace(**scope)


class ResolveOfflineTests(unittest.TestCase):
    def test_shared_name_cache(self):
        calls = []

        def embed(names, settings, usage):
            calls.append(names)
            time.sleep(0.01)
            usage["embedding_batches"] = usage.get("embedding_batches", 0) + 1
            return [[1.0] for _ in names]

        mod = definitions("_Frontier", embed_names=embed)
        frontier = mod._Frontier.__new__(mod._Frontier)
        frontier._lock = threading.Lock()
        frontier.settings = None
        frontier.usage = {}
        frontier.name_vectors = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(frontier.name_vectors_for, [["A", "A"]] * 8))
        self.assertEqual(results, [[[1.0], [1.0]]] * 8)
        self.assertEqual(calls, [["A"]])
        self.assertEqual(frontier.usage, {"embedding_batches": 1})

    def test_shortlist_includes_entities_without_embeddings(self):
        mod = definitions("_shortlist", SHORTLIST_K=25)
        conn = MagicMock()
        mention = SimpleNamespace(id="mention", entity_type="System", has_embedding=True)
        mod._shortlist(conn, mention, None)
        sql, params = conn.execute.call_args.args
        self.assertIn("UNION ALL", sql)
        self.assertIn("embedding IS NULL", sql)
        self.assertEqual(params, ("mention", "System", 25, "System"))
        mention.has_embedding = False
        mod._shortlist(conn, mention, None)
        sql, params = conn.execute.call_args.args
        self.assertNotIn("embedding", sql)
        self.assertEqual(params, ("System",))

    def test_embedding_outage_defers_only_failed_mention(self):
        class EmbedError(RuntimeError):
            pass

        conn = MagicMock()
        pool = MagicMock()
        pool.connection.return_value.__enter__.return_value = conn
        mentions = [SimpleNamespace(id="failed"), SimpleNamespace(id="exact")]
        assign = MagicMock()
        frontier = SimpleNamespace(usage={})
        resolve = MagicMock(side_effect=[EmbedError("offline"), ("exact", "entity")])
        mod = definitions(
            "run_resolve", EmbedError=EmbedError, _Frontier=lambda cfg: frontier,
            get_pool=lambda: pool, _load_unresolved=lambda conn: mentions,
            resolve_mention=resolve, _assign=assign, _refresh_counts=MagicMock(),
            _describe=lambda conn, frontier: 0, logger=logging.getLogger(__name__),
        )
        self.assertEqual(mod.run_resolve(object()), {"deferred": 1, "exact": 1, "described": 0})
        assign.assert_called_once_with(conn, mentions[1], "entity", set())
        self.assertEqual(conn.rollback.call_count, 2)
        conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
