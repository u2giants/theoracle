"""Bootstrap script validation (no database)."""

from __future__ import annotations

import os
import sys
import unittest
from uuid import uuid4

from oracle_brain import bootstrap_pilot_authority as mod


class BootstrapArgsTest(unittest.TestCase):
    def test_owner_and_appointed_by_must_differ(self):
        owner = str(uuid4())
        old = sys.argv
        sys.argv = [
            "bootstrap",
            "--workspace", str(uuid4()),
            "--owner", owner,
            "--appointed-by", owner,
            "--appointment-id", str(uuid4()),
            "--actor", str(uuid4()),
            "--owner-signature-hex", "00",
            "--actor-signature-hex", "00",
        ]
        try:
            with self.assertRaises(SystemExit):
                mod.main()
        finally:
            sys.argv = old

    def test_requires_admin_database_url(self):
        old_admin = os.environ.pop("ORACLE2_ADMIN_DATABASE_URL", None)
        old_url = os.environ.pop("ORACLE2_DATABASE_URL", None)
        old = sys.argv
        sys.argv = [
            "bootstrap",
            "--workspace", str(uuid4()),
            "--owner", str(uuid4()),
            "--appointed-by", str(uuid4()),
            "--appointment-id", str(uuid4()),
            "--actor", str(uuid4()),
            "--owner-signature-hex", "00",
            "--actor-signature-hex", "00",
        ]
        try:
            with self.assertRaises(SystemExit):
                mod.main()
        finally:
            sys.argv = old
            if old_admin is not None:
                os.environ["ORACLE2_ADMIN_DATABASE_URL"] = old_admin
            if old_url is not None:
                os.environ["ORACLE2_DATABASE_URL"] = old_url


if __name__ == "__main__":
    unittest.main()
