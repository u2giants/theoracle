"""Unit and adversarial tests for apps/brain/colab/preflight.py (#664 Step 0.1 & §9a)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from colab.preflight import (
    ColabAuthError,
    ColabBudgetError,
    ColabTeardownError,
    ColabTimeoutError,
    build_remote_wrapper_source,
    compute_worst_case_ccu,
    main,
    run_with_colab_guard,
)


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["colab"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_ccu_budget_cap_blocks_provisioning(tmp_path: Path) -> None:
    """§9a: Requesting A100 for 20 hours (~300 CCUs) without override refuses before provisioning."""
    script = tmp_path / "job.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return _proc(0, "Balance: 2000 CCU")

    # 20 hours = 1200 minutes -> blocked by wall-minute ceiling before any CLI call
    with pytest.raises(ColabBudgetError, match="max_wall_minutes"):
        run_with_colab_guard(
            script,
            gpu_tier="A100",
            max_wall_minutes=1200,
            max_ccu=50,
            runner=fake_runner,
        )
    assert calls == []

    # Even with --override-ccu-cap on ceiling, worst_case_ccu (300) > max_ccu (250) blocks before CLI
    with pytest.raises(ColabBudgetError, match="worst-case burn 300.00 CCU"):
        run_with_colab_guard(
            script,
            gpu_tier="A100",
            max_wall_minutes=1200,
            max_ccu=250,
            override_ccu_cap=True,
            runner=fake_runner,
        )
    assert calls == []

    # CLI exit code is 2 on budget error
    rc = main(
        [
            "--script",
            str(script),
            "--gpu",
            "A100",
            "--max-wall-minutes",
            "120",
            "--max-ccu",
            "10",
        ]
    )
    assert rc == 2


def test_account_balance_shortfall_blocks_provisioning(tmp_path: Path) -> None:
    """When colab usage reports fewer CCUs than worst-case burn, preflight aborts before run."""
    script = tmp_path / "job.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    subcommands: list[str] = []

    def fake_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        subcommands.append(cmd[4])
        if cmd[4] == "usage":
            return _proc(0, "Compute units remaining: 4.5")
        raise AssertionError(f"unexpected command {cmd}")

    with pytest.raises(ColabBudgetError, match="remaining Colab balance 4.50 CCU"):
        run_with_colab_guard(
            script,
            gpu_tier="A100",
            max_wall_minutes=60,
            max_ccu=20,
            runner=fake_runner,
        )
    assert subcommands == ["usage"]


def test_unknown_gpu_tier_rejected() -> None:
    """Unknown GPU names are rejected so colab CLI never silently falls back to A100."""
    with pytest.raises(ColabBudgetError, match="unsupported gpu_tier"):
        compute_worst_case_ccu("B200-UNKNOWN", 10)


def test_crash_and_timeout_always_run_teardown(tmp_path: Path) -> None:
    """§9a: Uncaught exception or wall-clock timeout always runs stop + sessions verification."""
    script = tmp_path / "hang.py"
    script.write_text("import time; time.sleep(9999)\n", encoding="utf-8")

    # Case 1: TimeoutExpired during `colab run`
    seen_timeout: list[str] = []

    def timeout_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        sub = cmd[4]
        seen_timeout.append(sub)
        if sub == "usage":
            return _proc(0, "Available balance: 1950.0 CCU")
        if sub == "run":
            assert kwargs["timeout"] == pytest.approx(300.0)
            wrapped_src = Path(cmd[-1]).read_text(encoding="utf-8")
            assert "_colab_guard_runtime.unassign()" in wrapped_src
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=300.0)
        if sub == "stop":
            return _proc(0, "stopped")
        if sub == "sessions":
            return _proc(0, "No active sessions.")
        raise AssertionError(f"unexpected subcommand {sub}")

    with pytest.raises(ColabTimeoutError, match="exceeded max_wall_minutes=5"):
        run_with_colab_guard(
            script,
            gpu_tier="L4",
            max_wall_minutes=5,
            max_ccu=5,
            session_name="oracle-664-timeout",
            runner=timeout_runner,
        )
    assert seen_timeout == ["usage", "run", "stop", "sessions"]

    # Case 2: Unexpected runtime crash / KeyboardInterrupt during `colab run`
    seen_crash: list[str] = []

    def crash_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        sub = cmd[4]
        seen_crash.append(sub)
        if sub == "usage":
            return _proc(0, "Available balance: 1950.0 CCU")
        if sub == "run":
            raise RuntimeError("simulated transport crash")
        if sub == "stop":
            return _proc(0, "stopped")
        if sub == "sessions":
            return _proc(0, "No active sessions.")
        raise AssertionError(f"unexpected subcommand {sub}")

    with pytest.raises(RuntimeError, match="simulated transport crash"):
        run_with_colab_guard(
            script,
            gpu_tier="L4",
            max_wall_minutes=5,
            max_ccu=5,
            session_name="oracle-664-crash",
            runner=crash_runner,
        )
    assert seen_crash == ["usage", "run", "stop", "sessions"]


def test_stuck_session_raises_teardown_error(tmp_path: Path) -> None:
    """If a session still appears in `colab sessions` after two stop attempts, raise loudly."""
    script = tmp_path / "ok.py"
    script.write_text("print('done')\n", encoding="utf-8")

    def sticky_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        sub = cmd[4]
        if sub == "usage":
            return _proc(0, "Available balance: 500 CCU")
        if sub == "run":
            return _proc(0, "done\n")
        if sub == "stop":
            return _proc(1, "", "backend error")
        if sub == "sessions":
            return _proc(0, "oracle-664-sticky  L4  BUSY")
        raise AssertionError(sub)

    with pytest.raises(ColabTeardownError, match="oracle-664-sticky"):
        run_with_colab_guard(
            script,
            gpu_tier="L4",
            max_wall_minutes=5,
            max_ccu=5,
            session_name="oracle-664-sticky",
            runner=sticky_runner,
        )


def test_missing_oauth_reports_clean_auth_error(tmp_path: Path) -> None:
    """Missing ADC/OAuth raises ColabAuthError without hanging on stdin."""
    script = tmp_path / "ok.py"
    script.write_text("print('done')\n", encoding="utf-8")

    def unauth_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["stdin"] == subprocess.DEVNULL
        return _proc(1, "", "DefaultCredentialsError: Your default credentials were not found.")

    with pytest.raises(ColabAuthError, match="colaboratory"):
        run_with_colab_guard(script, runner=unauth_runner)


def test_happy_path_forwards_args_and_cleans_up(tmp_path: Path) -> None:
    """Normal execution forwards script args, env vars, and verifies zero active sessions."""
    script = tmp_path / "batch.py"
    script.write_text("import sys; print(sys.argv[1:])\n", encoding="utf-8")
    recorded: list[list[str]] = []

    def ok_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded.append(list(cmd))
        sub = cmd[4]
        if sub == "usage":
            return _proc(0, "Balance: 1800.5 CCU")
        if sub == "run":
            return _proc(0, "['--alpha', '1']\n")
        if sub == "stop":
            return _proc(0, "")
        if sub == "sessions":
            return _proc(0, "")
        raise AssertionError(sub)

    res = run_with_colab_guard(
        script,
        ["--alpha", "1"],
        gpu_tier="L4",
        max_wall_minutes=30,
        max_ccu=5,
        env_vars={"HF_HUB_OFFLINE": "0"},
        session_name="oracle-664-ok",
        runner=ok_runner,
    )
    assert res.returncode == 0
    assert res.worst_case_ccu == pytest.approx(1.0)
    assert res.account_balance_ccu == pytest.approx(1800.5)
    run_cmd = recorded[1]
    assert "--gpu" in run_cmd and "L4" in run_cmd
    assert "--env" in run_cmd and "HF_HUB_OFFLINE=0" in run_cmd
    assert run_cmd[-2:] == ["--alpha", "1"]
    wrapped = build_remote_wrapper_source("x = 1\n")
    assert "_colab_guard_runtime.unassign()" in wrapped
