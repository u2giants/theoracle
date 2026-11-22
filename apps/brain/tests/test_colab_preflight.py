"""Unit and adversarial tests for apps/brain/colab/preflight.py (#664 Step 0.1 & §9a)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from colab.preflight import (
    FORBIDDEN_COLAB_ENV_KEYS,
    REMOTE_SECRETS_PATH,
    ColabAuthError,
    ColabBudgetError,
    ColabPreflightError,
    ColabTeardownError,
    ColabTimeoutError,
    build_remote_wrapper_source,
    compute_worst_case_ccu,
    main,
    parse_active_assignments,
    parse_balance_ccu,
    parse_download_spec,
    parse_upload_spec,
    run_with_colab_guard,
)

COLAB_DIR = Path(__file__).resolve().parents[1] / "colab"


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["colab"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_ccu_budget_cap_blocks_provisioning(tmp_path: Path) -> None:
    """§9a: Requesting A100 for 20 hours (~300 CCUs) without override refuses before provisioning."""
    script = tmp_path / "job.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return _proc(0, "Current balance: 2000.00 compute units\nUsage rate: 0.00/hr\nActive assignments: 0")

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
            return _proc(
                0,
                "Current balance: 4.50 compute units\nUsage rate: 0.00/hr\nActive assignments: 0",
            )
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
    assert parse_balance_ccu("Current balance: 1984.25 compute units\nActive assignments: 0") == pytest.approx(1984.25)
    assert parse_active_assignments("Current balance: 1984.25 compute units\nActive assignments: 0") == 0


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
    """Normal execution forwards script args, plain env vars, and verifies zero active sessions."""
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


def test_wrapper_compiles_real_colab_scripts_with_future_imports() -> None:
    """Regression: wrapping real scripts containing `from __future__ import annotations` must compile cleanly."""
    for filename in ("run_vllm_batch.py", "drain_leases.py", "train_relations_lora.py"):
        src = (COLAB_DIR / filename).read_text(encoding="utf-8")
        assert "from __future__ import annotations" in src
        wrapped = build_remote_wrapper_source(
            src,
            exec_mode_argv=[filename, "--help"],
            plain_env_vars={"BRAIN_COLAB_API_URL": "https://brain.example"},
            secret_env_remote_path=REMOTE_SECRETS_PATH,
            add_content_sys_path=True,
        )
        # Must compile with zero SyntaxError!
        code_obj = compile(wrapped, f"<wrapped:{filename}>", "exec")
        assert code_obj is not None
        assert wrapped.index("from __future__ import annotations") < wrapped.index("try:\n")


def test_l1_forbidden_env_keys_blocked_and_worker_secret_never_in_argv(tmp_path: Path) -> None:
    """L1 + §9a: DB/Supabase/OpenRouter keys are refused; worker tokens never appear in subprocess argv."""
    script = COLAB_DIR / "drain_leases.py"
    calls: list[list[str]] = []

    def spy_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return _proc(0, "Current balance: 1900.00 compute units")

    for forbidden_key in sorted(FORBIDDEN_COLAB_ENV_KEYS):
        with pytest.raises(ColabPreflightError, match="L1 security policy forbids"):
            run_with_colab_guard(
                script,
                env_vars={forbidden_key: "should-never-leave-host"},
                runner=spy_runner,
            )
    assert calls == []

    # Now run drain_leases.py with BRAIN_COLAB_WORKER_TOKEN + install + upload + download:
    # must use managed session (new -> install -> upload -> exec -> download -> stop -> sessions),
    # automatically stage companion colab/run_vllm_batch.py, and NEVER place secret in any argv!
    req_file = COLAB_DIR / "requirements-colab.txt"
    pkt_in = tmp_path / "pkt.jsonl"
    pkt_in.write_text("{}\n", encoding="utf-8")
    out_local = tmp_path / "out" / "results.jsonl"
    secret_val = "ultra-secret-worker-token-never-in-ps-664"
    seen_subs: list[str] = []
    uploaded_remote_dests: list[str] = []

    def managed_runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        # Hard assertion: secret value NEVER appears anywhere on command-line argv!
        for token in cmd:
            assert secret_val not in token
        sub = cmd[4]
        seen_subs.append(sub)
        if sub == "usage":
            return _proc(0, "Current balance: 1950.00 compute units\nActive assignments: 0")
        if sub == "new":
            return _proc(0, "created")
        if sub == "install":
            return _proc(0, "installed")
        if sub == "upload":
            uploaded_remote_dests.append(cmd[-1])
            if cmd[-1] == REMOTE_SECRETS_PATH:
                assert secret_val in Path(cmd[-2]).read_text(encoding="utf-8")
            return _proc(0, "uploaded")
        if sub == "exec":
            wrapped_text = Path(cmd[-1]).read_text(encoding="utf-8")
            assert secret_val not in wrapped_text
            assert f"_colab_guard_os.remove({REMOTE_SECRETS_PATH!r})" in wrapped_text
            return _proc(0, '{"batches_completed": 1}\n')
        if sub == "download":
            Path(cmd[-1]).write_text('{"chunk_id":"c1"}\n', encoding="utf-8")
            return _proc(0, "downloaded")
        if sub == "stop":
            return _proc(0, "stopped")
        if sub == "sessions":
            return _proc(0, "No active sessions.")
        raise AssertionError(f"unexpected subcommand {sub}")

    res = run_with_colab_guard(
        script,
        ["--hf-model", "Qwen/Qwen2.5-32B-Instruct", "--hf-revision", "a" * 40],
        gpu_tier="A100",
        max_wall_minutes=30,
        max_ccu=10,
        env_vars={
            "BRAIN_COLAB_API_URL": "https://oracle-brain.example",
            "BRAIN_COLAB_WORKER_TOKEN": secret_val,
        },
        install_requirements=req_file,
        uploads=[(pkt_in, "/content/pkt.jsonl")],
        downloads=[("/content/results.jsonl", out_local)],
        session_name="oracle-664-managed",
        runner=managed_runner,
    )
    assert res.returncode == 0
    assert out_local.read_text(encoding="utf-8") == '{"chunk_id":"c1"}\n'
    assert "/content/colab/run_vllm_batch.py" in uploaded_remote_dests
    assert REMOTE_SECRETS_PATH in uploaded_remote_dests
    assert seen_subs[0:3] == ["usage", "new", "install"]
    assert seen_subs[-3:] == ["download", "stop", "sessions"]

    # Verify Windows drive-letter upload/download spec parsers
    up_loc, up_rem = parse_upload_spec(r"D:\tmp\packet.jsonl:/content/packet.jsonl")
    assert str(up_loc).endswith("packet.jsonl") and up_rem == "/content/packet.jsonl"
    dl_rem, dl_loc = parse_download_spec(r"/content/results.jsonl:D:\tmp\results.jsonl")
    assert dl_rem == "/content/results.jsonl" and str(dl_loc).endswith("results.jsonl")
