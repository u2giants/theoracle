from unittest import TestCase
from unittest.mock import MagicMock

from brain.directory_sync import apply_directory
from brain.graph.communities import _area_people_bulk


class EmployeeMatchingTests(TestCase):
    def test_verified_names(self):
        conn = MagicMock()
        names = ["Maria de la Cruz", "Li Li", "Or Head"]
        conn.execute.return_value.fetchall.side_effect = [
            list(enumerate([*names, "Design Team"])),
            [(name, None) for name in names],
        ]
        self.assertEqual(
            _area_people_bulk(conn, ["0", "1", "2", "3"]),
            {str(i): name for i, name in enumerate(names)},
        )

    def test_alias_follows_effective_primary_status(self):
        for stored, status, skipped in [
            (False, "", 0), (True, "", 1), (None, "", 1),
            (False, "active", 1), (True, "inactive", 0),
        ]:
            with self.subTest(stored=stored, status=status):
                conn = MagicMock()
                conn.execute.return_value.fetchall.return_value = (
                    [] if stored is None else [("lee", stored)]
                )
                conn.execute.return_value.fetchone.return_value = None if stored is None else (1, "Lee")
                rows = [
                    {"email": "lee@edgeho.me", "status": "active"},
                    {"email": "lee@popcre.com", "status": status},
                ]
                self.assertEqual(apply_directory(conn, rows)["skipped"], skipped)
