#!/usr/bin/env python3
"""Run the synthetic holistic browser proof with owned local processes only."""
from __future__ import annotations

import argparse
import json
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
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
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", default="out/oracle2/holistic-browser-result.json")
    parser.add_argument("--readiness-only", action="store_true")
    args = parser.parse_args()
    result_path = ROOT / args.result
    fixture_proc = web_proc = None
    result = {"success": False, "live_business_accepted": False, "phase": "setup"}
    try:
        admin_url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
        falkor_url = os.environ.get("ORACLE2_TEST_FALKORDB_URL", os.environ.get("FALKORDB_URL", ""))
        if not admin_url or not falkor_url:
            raise ValueError("ORACLE2_TEST_ADMIN_URL and ORACLE2_TEST_FALKORDB_URL are required")
        _loopback(admin_url, "admin database")
        _loopback(falkor_url, "FalkorDB")
        tmp_parent = os.environ.get("TMPDIR") or tempfile.gettempdir()
        with tempfile.TemporaryDirectory(prefix="oracle2-holistic-browser-", dir=tmp_parent) as scratch:
            scratch_path = Path(scratch)
            os.chmod(scratch_path, 0o700)
            fixture_env_path = scratch_path / "fixture.env"
            fixture_log = (scratch_path / "fixture.log").open("w", encoding="utf-8")
            fixture_proc = subprocess.Popen(
                [sys.executable, "-u", str(FIXTURE), "--admin-url", admin_url,
                 "--falkordb-url", falkor_url, "--env-file", str(fixture_env_path)],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "services/oracle-brain")},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=fixture_log,
                text=True, start_new_session=True)
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
            web_proc = subprocess.Popen(
                ["pnpm", "--filter", "@oracle/web", "exec", "next", "dev",
                 "--hostname", "127.0.0.1", "--port", str(browser_port)],
                cwd=ROOT, env=web_env, stdin=subprocess.DEVNULL,
                stdout=web_log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            _wait_http(f"http://127.0.0.1:{browser_port}/consultant", web_proc, 45)
            result["phase"] = "browser"
            test_env = {**web_env, "ORACLE2_PREVIEW_URL": f"http://127.0.0.1:{browser_port}"}
            completed = subprocess.run(
                ["pnpm", "--filter", "@oracle/web", "exec", "playwright", "test",
                 "--config", "playwright.oracle2.config.ts",
                 ("tests/oracle2/pilot.spec.ts" if args.readiness_only
                  else "tests/oracle2/holistic-browser.spec.ts")],
                cwd=ROOT, env=test_env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90,
                check=False)
            result.update({"success": completed.returncode == 0,
                           "exit_code": completed.returncode, "ready": ready})
            if completed.returncode != 0:
                result["error"] = "browser proof failed"
    except subprocess.TimeoutExpired:
        result.update({"phase": "browser", "error": "browser proof timed out"})
    except Exception as error:
        result.update({"error": str(error)})
    finally:
        _terminate(web_proc)
        _terminate(fixture_proc)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        result_path.chmod(0o600)
    print(json.dumps({key: value for key, value in result.items() if key != "ready"}))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
