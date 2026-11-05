"""Offline regression checks; run directly without the database conftest."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from brain.api import flags

ENTITY = "00000000-0000-4000-8000-0000000000ab"
OTHER = "00000000-0000-4000-8000-0000000000cd"


class FlagFilterTests(unittest.TestCase):
    def query(self, **kwargs):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        pool = MagicMock()
        pool.connection.return_value.__enter__.return_value = conn
        with patch.object(flags, "get_pool", return_value=pool):
            result = flags.list_flags(
                user=None, **dict(item_type=None, item_id=None,
                                  include_resolved=False, entity_id=None) | kwargs,
            )
        self.assertEqual(result, {"flags": []})
        return conn.execute.call_args.args

    def test_uppercase_uuid_matches_create_normalization(self):
        for kind in ("entity", "community"):
            _, params = self.query(item_type=kind, item_id=ENTITY.upper())
            self.assertEqual(params, [kind, flags._norm_item(kind, ENTITY.upper())])

    def test_relation_matches_create_normalization(self):
        target = f"{ENTITY.upper()}:{OTHER.upper()}: PERFORMS "
        _, params = self.query(item_type="relation", item_id=target)
        self.assertEqual(params, ["relation", f"{ENTITY}:{OTHER}:PERFORMS"])

    def test_invalid_or_untyped_target_rejected(self):
        for args in ({"item_id": ENTITY},
                     {"item_type": "entity", "item_id": "bad"},
                     {"item_type": "relation", "item_id": "bad"},
                     {"entity_id": "bad"}):
            with self.assertRaises(HTTPException) as error:
                self.query(**args)
            self.assertEqual(error.exception.status_code, 400)

    def test_entity_batch_covers_both_directions_without_truncation(self):
        sql, params = self.query(entity_id=ENTITY.upper())
        self.assertEqual(params, [ENTITY, ENTITY])
        self.assertIn("item_type = 'relation'", sql)
        self.assertIn("split_part(item_id, ':', 1) = %s OR split_part(item_id, ':', 2) = %s", sql)
        self.assertIn("resolved_at IS NULL", sql)
        self.assertNotIn("LIMIT", sql)

    def test_review_list_keeps_default_limit(self):
        sql, _ = self.query()
        self.assertIn("LIMIT 500", sql)

    def test_seed_reset_clears_review_flags(self):
        # Isolate the reset from the seed's model/database fixture imports.
        source = Path(__file__).with_name("map_seed.py").read_text()
        reset = next(node for node in ast.parse(source).body
                     if isinstance(node, ast.FunctionDef) and node.name == "_reset")
        namespace = {"Any": object}
        exec(compile(ast.Module(body=[reset], type_ignores=[]), "map_seed.py", "exec"), namespace)
        db = MagicMock()
        namespace["_reset"](db)
        self.assertIn("cmap.review_flag", db.execute.call_args.args[0])
        self.assertIn("TRUNCATE", db.execute.call_args.args[0])
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
