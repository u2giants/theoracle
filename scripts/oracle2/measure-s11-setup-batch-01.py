"""TEST SETUP measurement only: one-admin batching call counts + offline wall time.
Never a business/realized saving. Invented recording harness; no socket/DB/Next.

Sealed measurement JSON (the artifact Muse reads):
  docs/verification/oracle2/s11-setup-batch-measurement-01.json
Label on both this script and that JSON:
  TEST SETUP measurement only — UNPROVED for business/realized savings.
Static 5->1 (admin contexts / pins) is real in code; live-DB install wall-time
saving is unmeasured and is not claimed.
"""
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import contextmanager
import json
import sys
import time

root = Path("/tmp/oracle-parent24-wy02uT/pr201-s11")
sys.path[:0] = [
    str(root),
    str(root / "services/oracle-brain"),
    str(root / "services/oracle-brain/tests"),
    "/tmp/pglast-venv-20261023/lib/python3.14/site-packages",
]

import psycopg  # noqa: E402
import test_recommendation_actions_sql as setup  # noqa: E402

ORIGINAL_AUTHORITY = setup._installed_advice_authority_v1


class MultiOpenRecorder:
    """Allows N admin contexts (sequential path). Still no socket."""

    def __init__(self, max_connections=None):
        self.events = []
        self.pending = []
        self.committed = []
        self.connections = 0
        self.max_connections = max_connections
        self.constructed = []
        self.owner = uuid4()
        self.fingerprints = tuple(
            sorted((signature.split("(")[0], "a" * 64, "b" * 64) for signature in setup.FUNCTIONS)
        )
        self.closed = False

    def execute(self, query, params=()):
        text = query.as_string() if hasattr(query, "as_string") else query
        self.events.append(("sql", text, params))
        if text.startswith("SELECT actor_id FROM oracle2.appointments"):
            return SimpleNamespace(fetchone=lambda: (self.owner,))
        if text.startswith("SELECT p.proname"):
            return SimpleNamespace(fetchall=lambda: list(self.fingerprints))
        if text.startswith("INSERT INTO oracle2.recommendation_action_admissions_v1"):
            self.pending.append(params)
        return SimpleNamespace()

    @contextmanager
    def admin(self, url):
        self.connections += 1
        if self.max_connections is not None:
            assert self.connections <= self.max_connections, "setup must never retry or fall back"
        self.closed = False
        self.events.append(("owned-guard",))
        self.events.append(("tls-session-db-check",))
        self.events.append(("begin",))
        try:
            try:
                yield self
            except BaseException:
                self.pending.clear()
                self.events.append(("rollback",))
                raise
            else:
                self.events.append(("commit-attempt",))
                self.committed = list(self.pending)
                self.pending = []
                self.events.append(("committed",))
        finally:
            self.closed = True
            self.events.append(("closed",))

    def construct(self, stage, operation, login, aid, fingerprints):
        assert self.closed
        assert fingerprints == self.fingerprints
        self.constructed.append(operation)
        self.events.append(("construct", operation))
        return "auth-" + operation


class OneOpenRecorder(MultiOpenRecorder):
    """Batch path: exactly one admin context (suite invariant)."""

    def __init__(self):
        super().__init__(max_connections=1)


def make_stage():
    ca = Path("/tmp/oracle-parent24-wy02uT/measure-ca.pem")
    ca.write_bytes(b"invented")
    ca.chmod(0o600)
    return dict(
        login="invented_compiler",
        schema_owner="oracle2_admin",
        f=dict(
            root=uuid4(),
            workspace=uuid4(),
            actor=uuid4(),
            model=uuid4(),
            expiry=datetime(2030, 1, 1, tzinfo=timezone.utc),
            all_refs=(),
            url=psycopg.conninfo.make_conninfo(
                host="127.0.0.1",
                port="5432",
                dbname="invented",
                user="u",
                password="p",
                sslmode="verify-full",
                sslrootcert=str(ca),
            ),
        ),
    )


def count_path(batch: bool):
    rec = OneOpenRecorder() if batch else MultiOpenRecorder()
    stage = make_stage()

    def construct(*args):
        return rec.construct(*args)

    def no_socket(*a, **k):
        raise AssertionError("socket")

    with (
        patch.object(setup, "admin", rec.admin),
        patch.object(setup, "_installed_advice_authority_v1", construct),
        patch.object(psycopg, "connect", no_socket),
    ):
        if batch:
            setup._install_all_advice_authorities_v1("invented-owned-admin", stage)
        else:
            for op, login in [
                ("register", "invented_compiler"),
                ("read", "a"),
                ("feedback", "b"),
                ("measurement", "c"),
            ]:
                setup.install("invented-owned-admin", stage, op, login=login)
            # repin: one more admin context + pins, without rebuilding authorities
            # (measurement records call counts only).
            with setup.admin("invented-owned-admin") as connection:
                setup.pins(connection)

    return dict(
        admin_contexts=rec.connections,
        pins_calls=sum(
            1 for e in rec.events if e[0] == "sql" and str(e[1]).startswith("SELECT p.proname")
        ),
        admissions=sum(
            1
            for e in rec.events
            if e[0] == "sql"
            and "INSERT INTO oracle2.recommendation_action_admissions_v1" in str(e[1])
        ),
        authorities_constructed=len(rec.constructed),
        events=len(rec.events),
    )


out = {}
for label, batch in [
    ("sequential_install_plus_repin", False),
    ("one_admin_batch", True),
]:
    walls = []
    counts = None
    for _ in range(20):
        t0 = time.perf_counter()
        counts = count_path(batch)
        walls.append(time.perf_counter() - t0)
    walls.sort()
    out[label] = dict(
        counts=counts,
        wall_n=20,
        wall_median_s=round(walls[10], 6),
        wall_min_s=round(walls[0], 6),
        wall_max_s=round(walls[-1], 6),
    )

seq = out["sequential_install_plus_repin"]["counts"]
bat = out["one_admin_batch"]["counts"]
assert seq["admin_contexts"] == 5 and bat["admin_contexts"] == 1
assert seq["pins_calls"] == 5 and bat["pins_calls"] == 1
assert seq["admissions"] == 4 and bat["admissions"] == 4
assert seq["authorities_constructed"] == 4 and bat["authorities_constructed"] == 4
out["delta"] = dict(
    admin_contexts=seq["admin_contexts"] - bat["admin_contexts"],
    pins_calls=seq["pins_calls"] - bat["pins_calls"],
    wall_median_s=round(
        out["sequential_install_plus_repin"]["wall_median_s"]
        - out["one_admin_batch"]["wall_median_s"],
        6,
    ),
)
out["label"] = (
    "TEST SETUP measurement only — UNPROVED for business/realized savings; "
    "recording harness wall time is not production install cost"
)
out["static_reduction"] = (
    "admin contexts 5->1; pins 5->1; admissions 4->4 unchanged; "
    "authorities 4->4 unchanged"
)
path = Path("/tmp/oracle-parent24-wy02uT/s11-setup-batch-measurement-01.json")
path.write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2))
