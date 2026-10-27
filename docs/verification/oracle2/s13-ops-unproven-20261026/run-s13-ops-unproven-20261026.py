#!/usr/bin/env python3
"""S13 ops-shaped UNPROVEN rows exercise runner (parent #24).

Covers rows 4 (alerts/retention/quota operational exercise) and 3 (production
RPO honesty / cadence-aware measurement). Owned synthetic stores only.
"""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path
from uuid import uuid4

root = Path("/tmp/oracle-parent24-wy02uT/s13-ops-unproven-20261026")
scratch = Path("/tmp/oracle-parent24-wy02uT/s13-ops-unproven-run-20261026")
sys.path.insert(0, str(root))
os.umask(0o077)
if scratch.exists():
    import shutil
    shutil.rmtree(scratch)
scratch.mkdir(mode=0o700)

with (scratch / "database-gate.txt").open("w") as f:
    subprocess.run(["ai-task-gates", "check", "--before", "database"], cwd=root,
                   stdout=f, stderr=subprocess.STDOUT, check=True)

from dev.oracle2.test_worker_postgres_fixture import worker_postgres, owned_worker_database
import psycopg
from psycopg import sql

identity = None
t0 = time.time()
try:
    with worker_postgres({**os.environ, "COMPOSE_PROJECT_NAME": "oracle2-synthetic-p24ops-mimo"},
                         scratch / "worker", "documentary-01") as (tls, identity):
        base = tls["ORACLE2_TEST_ADMIN_URL"]
        owned_worker_database(identity["container_id"], base)
        name = "oracle_operating_model_test_" + uuid4().hex
        with psycopg.connect(base, autocommit=True, connect_timeout=5,
                             options="-c statement_timeout=8000 -c lock_timeout=3000") as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = psycopg.conninfo.make_conninfo(base, dbname=name)
        env = {
            **os.environ, **tls,
            "COMPOSE_PROJECT_NAME": identity["project"],
            "ORACLE2_TEST_ADMIN_URL": url,
            "ORACLE2_WORKER_CONTAINER_ID": identity["container_id"],
            "ORACLE2_SYNTHETIC_POSTGRES_CONTAINER": identity["container_id"],
            "ORACLE2_S13_OPS_RESULT": str(scratch / "ops-result.json"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join([
                str(root / "services" / "oracle-brain"),
                str(root / "services" / "oracle-brain" / "tests"),
                str(root),
            ]),
        }
        junit = scratch / "s13-ops-unproven-junit.xml"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest",
             str(root / "services/oracle-brain/tests/test_s13_ops_unproven_exercise_v1.py"),
             "-v", "--tb=short", f"--junitxml={junit}"],
            env=env, cwd=str(root), capture_output=True, text=True, timeout=600,
        )
        (scratch / "pytest.txt").write_text(proc.stdout + "\n---STDERR---\n" + proc.stderr)
        junit_sha = hashlib.sha256(junit.read_bytes()).hexdigest() if junit.exists() else ""
        ops_sha = ""
        ops = scratch / "ops-result.json"
        if ops.exists():
            ops_sha = hashlib.sha256(ops.read_bytes()).hexdigest()
        result = {
            "returncode": proc.returncode,
            "junit": str(junit),
            "junit_sha256": junit_sha,
            "ops_result_sha256": ops_sha,
            "elapsed_seconds": round(time.time() - t0, 3),
            "identity": identity,
            "database": name,
            "branch": "codex/parent24-s13-ops-unproven-20261026",
            "base_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        }
        (scratch / "runner-result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(json.dumps({"returncode": proc.returncode,
                          "elapsed_seconds": result["elapsed_seconds"],
                          "junit_sha256": junit_sha,
                          "ops_result_sha256": ops_sha,
                          "base_head": result["base_head"]}))
        sys.exit(proc.returncode)
finally:
    if identity is not None:
        try:
            subprocess.run(["docker", "compose", "-p", identity["project"], "down", "-v",
                            "--remove-orphans"], capture_output=True, timeout=60)
        except Exception:
            pass
