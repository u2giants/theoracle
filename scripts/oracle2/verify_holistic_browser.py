#!/usr/bin/env python3
"""Run the synthetic holistic browser proof with owned local processes only."""
from __future__ import annotations

import argparse
import json
import hashlib
import shutil
import re
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import threading
from contextlib import ExitStack
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dev.oracle2.legacy_database_fixture import owned_legacy_database, stop_owned_process, LegacyCleanupBlocked

FIXTURE = ROOT / "scripts/oracle2/holistic_browser_fixture.py"


def _loopback(url: str, label: str) -> None:
    if urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(f"{label} must be loopback-only")


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_fixture_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, encoded = line.partition("=")
        if not separator or not key or not encoded:
            raise ValueError("fixture environment file is malformed")
        value = json.loads(encoded)
        if not isinstance(value, str):
            raise ValueError("fixture environment values must be JSON strings")
        values[key] = value
    required = ("ORACLE2_DATABASE_URL", "ORACLE2_PILOT_TOKEN", "ORACLE2_PILOT_ACTOR",
                "ORACLE2_PILOT_WORKSPACE_ID", "ORACLE2_HOLISTIC_TRIGGER_SECRET_KEY",
                "ORACLE2_HOLISTIC_CORPUS_DIGEST", "ORACLE2_HOLISTIC_FIXTURE_SOURCE_ID",
                "ORACLE2_HOLISTIC_FIXTURE_DRAFT_ID", "ORACLE2_HOLISTIC_FIXTURE_SOURCE_IDS",
                "TRIGGER_API_URL")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError(f"fixture environment missing {len(missing)} required values")
    _loopback(values["ORACLE2_DATABASE_URL"], "fixture database")
    _loopback(values["TRIGGER_API_URL"], "fixture trigger API")
    json.loads(values["ORACLE2_HOLISTIC_FIXTURE_SOURCE_IDS"])
    return values


def _terminate(proc: subprocess.Popen[str] | None) -> None:
    stop_owned_process(proc)


def _wait_http(url: str, proc: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "unavailable"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"web process exited with code {proc.returncode}")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, URLError) as error:
            last_error = type(error).__name__
        time.sleep(0.5)
    raise TimeoutError(f"web readiness timed out ({last_error})")


def _browser_run(command, *, cwd, env, timeout):
    """Drain browser output continuously while retaining only a bounded tail."""
    proc=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    tail=bytearray()
    def drain():
        while True:
            chunk=proc.stdout.read(4096)
            if not chunk:break
            tail.extend(chunk)
            if len(tail)>262144:del tail[:-262144]
    reader=threading.Thread(target=drain,daemon=True);reader.start()
    timed_out=False
    try:proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
    finally:
        try:
            _terminate(proc)
        finally:
            reader.join(timeout=8)
            if reader.is_alive():raise LegacyCleanupBlocked('owned browser output did not close')
        proc.stdout.close()
    if timed_out:raise subprocess.TimeoutExpired(command,timeout,output=bytes(tail))
    return subprocess.CompletedProcess(command,proc.returncode,bytes(tail).decode('utf-8',errors='replace'))


def _retain_diagnostics(scratch_path, result_path, fixture_values):
    diagnostics={}
    if scratch_path is not None:
        for name in ('fixture.log','web.log','browser.log'):
            source=scratch_path / name
            if not source.exists():continue
            with source.open('rb') as stream:
                stream.seek(max(0,source.stat().st_size-262144))
                data=stream.read(262144).decode('utf-8',errors='replace')
            # Diagnostic copies contain no credential-bearing URLs or fixture tokens.
            data=re.sub(r'(postgres(?:ql)?|rediss?)://[^\s\"\']+',r'\1://[redacted]',data)
            for key,value in fixture_values.items():
                if any(word in key for word in ('TOKEN','SECRET','DATABASE_URL')) and value:data=data.replace(value,'[redacted]')
            fd,filename=tempfile.mkstemp(prefix=result_path.stem+'-',suffix='-'+name,dir=result_path.parent)
            target=Path(filename)
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'wb') as stream:
                encoded=data.encode()[-262144:];stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            diagnostics[name]={'file':target.name,'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest(),'tail_limit_bytes':262144}
    return diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", default="out/oracle2/holistic-browser-result.json")
    parser.add_argument("--readiness-only", action="store_true")
    parser.add_argument("--pilot-graph-evidence", action="store_true",
                        help="run pilot.spec.ts against the ready graph-evidence answer method")
    args = parser.parse_args()
    result_path = ROOT / args.result
    fixture_proc = web_proc = None
    scratch_path = None
    opened_logs = []
    fixture_values = {}
    databases = ExitStack()
    body_cleanup_failure = None
    result = {"success": False, "live_business_accepted": False, "phase": "setup"}
    try:
        admin_url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
        falkor_url = os.environ.get("ORACLE2_TEST_FALKORDB_URL", os.environ.get("FALKORDB_URL", ""))
        if not admin_url or not falkor_url:
            raise ValueError("ORACLE2_TEST_ADMIN_URL and ORACLE2_TEST_FALKORDB_URL are required")
        _loopback(admin_url, "admin database")
        _loopback(falkor_url, "FalkorDB")
        tmp_parent = os.environ.get("TMPDIR") or tempfile.gettempdir()
        scratch_path = Path(tempfile.mkdtemp(prefix="oracle2-holistic-browser-", dir=tmp_parent))
        os.chmod(scratch_path, 0o700)
        legacy = databases.enter_context(owned_legacy_database())
        admin_url = legacy.url
        fixture_env_path = scratch_path / "fixture.env"
        fixture_log = (scratch_path / "fixture.log").open("w", encoding="utf-8")
        fixture_proc = subprocess.Popen(
            [sys.executable, "-u", str(FIXTURE), "--admin-url", admin_url,
             "--falkordb-url", falkor_url, "--env-file", str(fixture_env_path),
             "--engine", ("graph-evidence" if args.pilot_graph_evidence else "holistic-graphrag")],
            cwd=ROOT, env={**os.environ, **legacy.environment(), "PYTHONPATH": str(ROOT / "services/oracle-brain")},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=fixture_log,
            text=True, start_new_session=True)
        opened_logs.append(fixture_log)
        ready = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            line = ""
            if fixture_proc.stdout and select.select([fixture_proc.stdout], [], [], 0.5)[0]:
                line = fixture_proc.stdout.readline()
            if line:
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    fixture_log.write(line); fixture_log.flush(); continue
                if candidate.get("ready") is True:
                    ready = candidate
                    break
            if fixture_proc.poll() is not None:
                raise RuntimeError(f"fixture exited with code {fixture_proc.returncode}")
        if ready is None:
            raise TimeoutError("fixture readiness timed out")
        fixture_values = _read_fixture_env(fixture_env_path)
        browser_port = _port()
        web_env = {
            **os.environ, **fixture_values,
            "ORACLE2_PREVIEW_URL": f"http://127.0.0.1:{browser_port}",
            "NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": "synthetic-anon-key",
            "PYTHONPATH": str(ROOT / "services/oracle-brain"),
        }
        # The dedicated fourth-argument SDK credential must work by itself.
        web_env.pop("TRIGGER_ACCESS_TOKEN", None)
        web_env.pop("TRIGGER_SECRET_KEY", None)
        if args.readiness_only:
            web_env.pop("ORACLE2_HOLISTIC_TRIGGER_SECRET_KEY", None)
            web_env.pop("ORACLE2_HOLISTIC_CORPUS_DIGEST", None)
        web_log = (scratch_path / "web.log").open("w", encoding="utf-8")
        opened_logs.append(web_log)
        web_proc = subprocess.Popen(
            ["pnpm", "--filter", "@oracle/web", "exec", "next", "dev",
             "--hostname", "127.0.0.1", "--port", str(browser_port)],
            cwd=ROOT, env=web_env, stdin=subprocess.DEVNULL,
            stdout=web_log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        _wait_http(f"http://127.0.0.1:{browser_port}/consultant", web_proc, 45)
        result["phase"] = "browser"
        test_env = {**web_env, "ORACLE2_PREVIEW_URL": f"http://127.0.0.1:{browser_port}"}
        completed = _browser_run(
            ["pnpm", "--filter", "@oracle/web", "exec", "playwright", "test",
             "--config", "playwright.oracle2.config.ts",
             ("tests/oracle2/pilot.spec.ts" if args.readiness_only or args.pilot_graph_evidence
              else "tests/oracle2/holistic-browser.spec.ts")],
            cwd=ROOT, env=test_env, timeout=90)
        browser_log=scratch_path / "browser.log"
        browser_log.write_text(completed.stdout or "", encoding="utf-8")
        browser_log.chmod(0o600)
        result.update({"success": completed.returncode == 0,
                       "exit_code": completed.returncode, "ready": ready})
        if completed.returncode != 0:
            result["error"] = "browser proof failed"
    except subprocess.TimeoutExpired as error:
        if scratch_path is not None:
            partial=error.stdout or b""
            if isinstance(partial,bytes):partial=partial.decode("utf-8",errors="replace")
            target=scratch_path / "browser.log"
            target.write_text(partial[-262144:]);target.chmod(0o600)
        result.update({"phase": "browser", "error": "browser proof timed out"})
    except LegacyCleanupBlocked as error:
        body_cleanup_failure = error
        result.update({"error": "owned process cleanup is not proven"})
    except Exception as error:
        result.update({"error": str(error)})
    finally:
        cleanup_failure = body_cleanup_failure
        for process in (web_proc, fixture_proc):
            try:
                _terminate(process)
            except LegacyCleanupBlocked as error:
                cleanup_failure = error
        for stream in opened_logs:
            stream.flush(); stream.close()
        try:
            if cleanup_failure:
                databases.__exit__(LegacyCleanupBlocked, cleanup_failure, None)
            else:
                databases.close()
        except Exception as cleanup_error:
            result.update({"success": False, "cleanup_error": type(cleanup_error).__name__})
        result_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics=_retain_diagnostics(scratch_path,result_path,fixture_values)
        if scratch_path is not None:shutil.rmtree(scratch_path)
        result['diagnostics']=diagnostics
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        result_path.chmod(0o600)
    print(json.dumps({key: value for key, value in result.items() if key != "ready"}))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
