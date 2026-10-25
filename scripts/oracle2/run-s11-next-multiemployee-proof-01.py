"""S11 Next/multiemployee one-shot proof runner (Linux-only, edge-dev3).

Sealed into PR #201 so every fail-closed claim is inspectable:
  - exact-head pin          : receipt.head == git rev-parse HEAD of the execution worktree
  - receipt fields          : head, verdict=APPROVE, reviewer, reviewed_at
  - STOP exit 2             : missing/incomplete receipt refuses before any DB/Next work
  - owned cleanup           : compose-project absence proof (containers/networks/volumes)
  - source-before/after     : sha256 over the sealed truth source set is equal after the run

Budget honesty (Muse REJECT Critical 2):
  These two proofs are NOT a W10 120s sequential pair. Two Next startups alone can
  cost ~90s and each driver allows up to 110s communicate. This runner therefore
  executes TWO separate one-shot invocations, each with an explicit larger wall
  clock (ONE_SHOT_WALL_S). That wall clock is test-setup-only and is NOT the W10
  budget. Do NOT claim W10 SAME fit from this run. W10 placement already puts
  workspace_next_recipients_sql_v1 and recommendation_next_auth_browser_v1 in
  different parallel workers (verify_workflow_integrity.py).

Third-driver / dist-lock honesty (Muse REJECT Critical 3):
  Shared apps/web/.next/dev lock under full W10 parallel remains UNPROVED and is a
  named remaining gate. This one-shot does not claim W10 Next stability. The
  contention observation plan also names test_consolidation_next_auth_browser_v1
  (see docs/verification/oracle2/s11-next-dist-lock-note.md).

Platform: Linux only (/proc probing in the sealed drivers). Invent fixtures only.
No production, no company originals, no paid providers, no real employees.
"""
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import subprocess
import sys

# Authoring parent of this seal. The reviewed seal SHA is bound by the Muse
# receipt and by docs/verification/oracle2/pr201-next-status.md; the pin below
# is the checked-out execution HEAD vs receipt.head.
AUTHORING_PARENT = "ac1a848edaa3570070abaeef5627b8d33cfd3685"

# Per-invocation wall clock. test-setup-only; NOT the W10 120s budget.
ONE_SHOT_WALL_S = 300

# Sealed truth source set (Muse-referenced paths). Hashed before/after.
SEALED_SOURCE_PATHS = (
    "services/oracle-brain/tests/test_connected_answer_sdk_sql_v1.py",
    "services/oracle-brain/tests/test_workspace_next_recipients_sql_v1.py",
    "services/oracle-brain/tests/test_recommendation_next_auth_browser_v1.py",
    "services/oracle-brain/tests/test_recommendation_actions_sql.py",
    "services/oracle-brain/tests/invented_next_employee_fixture_v1.py",
    "apps/web/tests/oracle2/workspace-next-recipients-proof.ts",
    "apps/web/tests/oracle2/recommendation-next-auth-proof.ts",
    "apps/web/tests/oracle2/invented-auth-service.ts",
    "apps/web/next.config.ts",
    "scripts/oracle2/verify_workflow_integrity.py",
    "dev/oracle2/test_worker_postgres_fixture.py",
    "scripts/oracle2/run-s11-next-multiemployee-proof-01.py",
    "services/oracle-brain/tests/test_s11_next_database_fixture_order.py",
)

root = Path("/tmp/oracle-parent24-wy02uT/pr201-s11")
scratch = Path("/tmp/oracle-parent24-wy02uT/s11-next-multiemployee-proof-01")
receipt_path = Path("/tmp/oracle-parent24-wy02uT/s11-next-multiemployee-review-receipt.json")

# Linux-only: sealed drivers probe /proc and will raise FileNotFoundError in
# their finally path on a non-Linux host (Muse Medium finding).
if not Path("/proc").is_dir():
    print("STOP: Linux-only runner (/proc required); use edge-dev3")
    sys.exit(2)


def source_digest(base: Path) -> str:
    h = hashlib.sha256()
    for rel in SEALED_SOURCE_PATHS:
        p = base / rel
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes() if p.is_file() else b"<absent>")
        h.update(b"\0")
    return h.hexdigest()


def post_run_scan(base: Path, label: str) -> dict:
    """Additive cleanup evidence beyond the drivers' ppid==child.pid scan.

    Known gap (Muse High cleanup): the sealed drivers assert no remaining
    processes by scanning ppid == child.pid only; grandchildren reparent to
    init and pass that assertion. This scan is name/port/lock based and is
    recorded as evidence; it does not replace the drivers' own proof.
    """
    procs = []
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,comm,args"], text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines()[1:]:
            low = line.lower()
            if any(tok in low for tok in ("next dev", "next-server", "turbopack", "playwright", "chromium")):
                procs.append(line.strip())
    except BaseException as e:  # noqa: BLE001 - evidence collection, never masks main result
        procs.append(f"<ps-failed:{e}>")
    lock = base / "apps/web/.next/dev"
    lock_present = lock.exists()
    return {
        "label": label,
        "matching_processes": procs,
        "next_dev_lock_present": lock_present,
        "process_scan_clean": not procs,
        "lock_absent": not lock_present,
        "known_gap": (
            "drivers' ppid==child.pid scan misses reparented grandchildren; "
            "this name/port/lock scan is additive only"
        ),
    }


def stale_lock_precheck(base: Path, label: str) -> dict:
    lock = base / "apps/web/.next/dev"
    present = lock.exists()
    return {"label": label, "next_dev_lock_present": present, "ok": not present}


# Exact head binding before any work.
actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

# Review-receipt requirement: exact-head APPROVE must exist before DB/Next.
if not receipt_path.is_file():
    print("STOP: review receipt required before execution")
    print("expected:", receipt_path)
    print("required fields: head, verdict=APPROVE, reviewer, reviewed_at")
    sys.exit(2)

receipt = json.loads(receipt_path.read_text())
assert receipt.get("head") == actual, "receipt must bind exact checked-out head"
assert receipt.get("verdict") == "APPROVE", "exact-head APPROVE required"
assert receipt.get("reviewer"), "named reviewer required"
assert receipt.get("reviewed_at"), "reviewed_at required"

digest_before = source_digest(root)

sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "services/oracle-brain"))
sys.path.insert(0, str(root / "services/oracle-brain/tests"))
sys.path.insert(0, "/tmp/pglast-venv-20261023/lib/python3.14/site-packages")
os.umask(0o077)
scratch.mkdir(mode=0o700, exist_ok=False)

from dev.oracle2.test_worker_postgres_fixture import (  # noqa: E402
    worker_postgres,
    owned_worker_database,
)
import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

# Resource plan (Muse Critical 4). Provisioning/cleanup sit OUTSIDE each
# one-shot wall clock, matching W10's exclusion of setup from the test budget.
# Required stores beyond "one fresh PG":
#   - FalkorDB graph stores (connected-answer journey)
#   - TLS fixtures (verify-full + sslrootcert) via worker_postgres
#   - openssl (auth-browser cert fixtures)
#   - pnpm / tsx (TS proof drivers)
#   - Chromium (browser proof; CI installs unpinned — see plan)
#   - localhost.localdomain DNS and ::1 loopback
# Cluster-global invented LOGIN roles accumulate across runs; cleanup uses
# whole-project down --volumes (see plan).
RESOURCE_PRECHECK = {
    "falkordb": "compose worker_postgres graph stores",
    "tls": "verify-full + sslrootcert fixtures",
    "openssl": "required on PATH",
    "pnpm_tsx": "required for apps/web TS drivers",
    "chromium": "required (CI unpinned)",
    "dns": "localhost.localdomain and ::1 must resolve",
    "budget_label": "test-setup-only; NOT the W10 120s budget",
    "setup_inside_wall_clock": False,
}
(scratch_pre := Path("/tmp/oracle-parent24-wy02uT")).mkdir(parents=True, exist_ok=True)

identity = None
scans = []
try:
    with worker_postgres(
        {
            **os.environ,
            "COMPOSE_PROJECT_NAME": "oracle2-synthetic-p24s11-next-me",
        },
        scratch / "worker",
        "next-multiemployee-01",
    ) as (tls, identity):
        base = tls["ORACLE2_TEST_ADMIN_URL"]
        owned_worker_database(identity["container_id"], base)
        name = "oracle_operating_model_test_" + uuid4().hex
        with psycopg.connect(
            base,
            autocommit=True,
            connect_timeout=2,
            options="-c statement_timeout=5000 -c lock_timeout=2000",
        ) as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = psycopg.conninfo.make_conninfo(base, dbname=name)
        owned_worker_database(identity["container_id"], url)
        env = {
            **os.environ,
            **tls,
            "COMPOSE_PROJECT_NAME": identity["project"],
            "ORACLE2_TEST_ADMIN_URL": url,
            "ORACLE2_WORKER_CONTAINER_ID": identity["container_id"],
            "ORACLE2_SYNTHETIC_POSTGRES_CONTAINER": identity["container_id"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "/tmp/pglast-venv-20261023/lib/python3.14/site-packages:"
            + str(root / "services/oracle-brain")
            + ":"
            + str(root / "services/oracle-brain/tests")
            + ":"
            + str(root),
        }
        # TWO separate one-shot invocations (NOT a W10 120s sequential pair).
        # Each invocation gets ONE_SHOT_WALL_S; provisioning is outside the clock.
        invocations = [
            (
                "workspace_next_recipients_sql_v1",
                "services/oracle-brain/tests/test_workspace_next_recipients_sql_v1.py",
            ),
            (
                "recommendation_next_auth_browser_v1",
                "services/oracle-brain/tests/test_recommendation_next_auth_browser_v1.py",
            ),
        ]
        results = []
        for idx, (suite, rel) in enumerate(invocations):
            # Stale-lock pre-check between the two Next runs (Muse High cleanup).
            pre = stale_lock_precheck(root, f"pre-{suite}")
            scans.append(pre)
            assert pre["ok"], f"stale apps/web/.next/dev lock before {suite}"
            out_txt = scratch / f"pytest-{idx}-{suite}.txt"
            xml = scratch / f"pytest-{idx}-{suite}.xml"
            args = [
                "python3",
                "-m",
                "pytest",
                rel,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "--basetemp=" + str(scratch / f"pytest-owned-{idx}"),
                "--junitxml=" + str(xml),
            ]
            with out_txt.open("w") as f:
                result = subprocess.run(
                    args,
                    cwd=root,
                    env=env,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=ONE_SHOT_WALL_S,
                )
            import xml.etree.ElementTree as ET

            totals = {
                k: sum(
                    int(s.get(k, 0))
                    for s in ET.parse(xml).getroot().iter("testsuite")
                )
                for k in ("tests", "failures", "errors", "skipped")
            }
            results.append(
                {
                    "suite": suite,
                    "returncode": result.returncode,
                    "totals": totals,
                    "wall_clock_s": ONE_SHOT_WALL_S,
                    "budget_label": "test-setup-only; NOT the W10 120s budget",
                }
            )
            scans.append(post_run_scan(root, f"post-{suite}"))
            print("EXACT_JUNIT", suite, totals)
            assert result.returncode == 0, (suite, totals)
        (scratch / "result.json").write_text(
            json.dumps(
                {
                    "head": actual,
                    "authoring_parent": AUTHORING_PARENT,
                    "receipt_head": receipt["head"],
                    "receipt_reviewer": receipt["reviewer"],
                    "receipt_reviewed_at": receipt["reviewed_at"],
                    "database": name,
                    "project": identity["project"],
                    "invocations": results,
                    "w10_same_fit_claimed": False,
                    "dist_lock_w10_proved": False,
                    "budget_note": (
                        "two separate one-shot invocations at "
                        f"{ONE_SHOT_WALL_S}s each; NOT the W10 120s budget"
                    ),
                },
                indent=2,
            )
            + "\n"
        )
finally:
    try:
        digest_after = source_digest(root)
        (scratch / "source-equality.json").write_text(
            json.dumps(
                {
                    "before": digest_before,
                    "after": digest_after,
                    "equal": digest_before == digest_after,
                },
                indent=2,
            )
            + "\n"
        )
        assert digest_before == digest_after, "sealed source mutated during run"
        (scratch / "scans.json").write_text(json.dumps(scans, indent=2) + "\n")
        project = identity["project"] if identity is not None else None
        if project is None:
            (scratch / "cleanup.json").write_text(
                json.dumps({"observation": "UNKNOWN", "absence_proven": False}, indent=2)
                + "\n"
            )
            raise RuntimeError("no identity yielded")
        remains = {
            kind: bool(
                subprocess.check_output(
                    cmd + ["--filter", "label=com.docker.compose.project=" + project],
                    text=True,
                ).strip()
            )
            for kind, cmd in [
                ("containers", ["docker", "ps", "-aq"]),
                ("networks", ["docker", "network", "ls", "-q"]),
                ("volumes", ["docker", "volume", "ls", "-q"]),
            ]
        }
        final_scan = post_run_scan(root, "post-cleanup")
        scans.append(final_scan)
        (scratch / "cleanup.json").write_text(
            json.dumps(
                {
                    "project": project,
                    "remaining": remains,
                    "absence_proven": not any(remains.values()),
                    "final_process_scan": final_scan,
                    "role_note": (
                        "invented LOGIN roles are cluster-global and accumulate; "
                        "containment requires whole-project down --volumes"
                    ),
                },
                indent=2,
            )
            + "\n"
        )
        print("EXACT_OWNED_CLEANUP", not any(remains.values()))
        assert not any(remains.values())
    except BaseException as e:
        (scratch / "cleanup.json").write_text(
            json.dumps(
                {"observation": "UNKNOWN", "absence_proven": False, "error": str(e)},
                indent=2,
            )
            + "\n"
        )
        raise
