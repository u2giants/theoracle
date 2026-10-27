#!/usr/bin/env python3
"""S13 full-recovery synthetic DR exercise runner (parent #24)."""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path
from uuid import uuid4

root = Path("/tmp/oracle-parent24-wy02uT/s13-full-recovery-20261026")
scratch = Path("/tmp/oracle-parent24-wy02uT/s13-full-recovery-run-20261026")
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
falkor_name = None
t0 = time.time()
try:
    with worker_postgres({**os.environ, "COMPOSE_PROJECT_NAME": "oracle2-synthetic-p24full-mimo"},
                         scratch / "worker", "documentary-01") as (tls, identity):
        base = tls["ORACLE2_TEST_ADMIN_URL"]
        owned_worker_database(identity["container_id"], base)
        name = "oracle_operating_model_test_" + uuid4().hex
        with psycopg.connect(base, autocommit=True, connect_timeout=5,
                             options="-c statement_timeout=8000 -c lock_timeout=3000") as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = psycopg.conninfo.make_conninfo(base, dbname=name)
        # Live synthetic FalkorDB for graph census (pinned image, loopback only).
        import subprocess as _sp
        falkor_name = "s13-graph-census-" + uuid4().hex[:8]
        falkor_port = 16401
        falkor_pass = "s13_census_local_only"
        _sp.run(["docker", "rm", "-f", falkor_name], capture_output=True)
        _sp.run([
            "docker", "run", "-d", "--name", falkor_name,
            "--label", "oracle.operating.synthetic=true",
            "-p", f"127.0.0.1:{falkor_port}:6379",
            "-e", f"FALKORDB_ARGS=--dir /data --requirepass {falkor_pass} --appendonly yes",
            "falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d",
        ], check=True, capture_output=True)
        import time as _time
        for _i in range(30):
            _ping = _sp.run(
                ["docker", "exec", falkor_name, "redis-cli", "-a", falkor_pass, "ping"],
                capture_output=True, text=True)
            if "PONG" in (_ping.stdout or ""):
                break
            _time.sleep(1)
        else:
            raise RuntimeError("synthetic FalkorDB did not become ready")
        falkor_url = f"redis://:{falkor_pass}@127.0.0.1:{falkor_port}"

        env = {
            **os.environ, **tls,
            "ORACLE2_TEST_CONFIRMED_URL": falkor_url,
            "COMPOSE_PROJECT_NAME": identity["project"],
            "ORACLE2_TEST_ADMIN_URL": url,
            "ORACLE2_WORKER_CONTAINER_ID": identity["container_id"],
            "ORACLE2_SYNTHETIC_POSTGRES_CONTAINER": identity["container_id"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join([
                str(root / "services" / "oracle-brain"),
                str(root / "services" / "oracle-brain" / "tests"),
                str(root),
            ]),
        }
        junit = scratch / "s13-full-recovery-junit.xml"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest",
             str(root / "services/oracle-brain/tests/test_s13_full_recovery_exercise_v1.py"),
             "-v", "--tb=short", f"--junitxml={junit}"],
            env=env, cwd=str(root), capture_output=True, text=True, timeout=600,
        )
        (scratch / "pytest.txt").write_text(proc.stdout + "\n---STDERR---\n" + proc.stderr)
        result = {
            "returncode": proc.returncode,
            "junit": str(junit),
            "elapsed_seconds": round(time.time() - t0, 3),
            "identity": identity,
            "database": name,
            "branch": "codex/parent24-s13-full-recovery-20261026",
            "base_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        }
        (scratch / "runner-result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(json.dumps({"returncode": proc.returncode,
                          "elapsed_seconds": result["elapsed_seconds"],
                          "base_head": result["base_head"]}))
        sys.exit(proc.returncode)
finally:
    if identity is not None:
        try:
            subprocess.run(["docker", "compose", "-p", identity["project"], "down", "-v",
                            "--remove-orphans"], capture_output=True, timeout=60)
        except Exception:
            pass
    if falkor_name:
        try:
            subprocess.run(["docker", "rm", "-f", falkor_name],
                           capture_output=True, timeout=30)
        except Exception:
            pass
