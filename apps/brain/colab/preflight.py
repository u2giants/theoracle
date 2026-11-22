"""Headless Google Colab CLI preflight, CCU budget guard, and teardown wrapper (#664 Step 0.1).

Every remote Colab invocation MUST pass through ``run_with_colab_guard`` so that:
1. Worst-case compute-unit burn is bounded before provisioning a VM.
2. Account balance (when reported by ``colab usage``) covers the worst-case burn.
3. Remote execution is wrapped in an in-VM ``try ... finally`` calling
   ``google.colab.runtime.unassign()`` AND a host-side ``try ... finally``
   calling ``colab stop -s <session>`` + ``colab sessions`` verification on
   normal exit, exception, wall-clock timeout, or SIGINT/SIGTERM.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# Conservative worst-case CCU/hour rates used for pre-provisioning budget checks.
# Unrecognized GPU names are rejected explicitly because google-colab-cli falls
# back to A100 on unknown strings.
BURN_RATE_CCU_PER_HOUR: dict[str, float] = {
    "CPU": 0.2,
    "T4": 1.2,
    "L4": 2.0,
    "G4": 4.0,
    "A100": 15.0,
    "H100": 35.0,
}

MAX_WALL_MINUTES_DEFAULT_CEILING = 240.0
MAX_CCU_DEFAULT_CEILING = 200.0
USAGE_PROBE_TIMEOUT_SECONDS = 15.0
TEARDOWN_TIMEOUT_SECONDS = 30.0

_BALANCE_RE = re.compile(
    r"(?:balance|available|remaining)[^\d\n]{0,24}(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


class ColabPreflightError(RuntimeError):
    """Base error for Colab preflight and lifecycle failures."""


class ColabBudgetError(ColabPreflightError):
    """Raised before provisioning when requested wall time or CCUs exceed budget."""


class ColabAuthError(ColabPreflightError):
    """Raised when headless Colab CLI credentials or scopes are unavailable."""


class ColabTimeoutError(ColabPreflightError):
    """Raised when a Colab job exceeds ``max_wall_minutes`` and is terminated."""


class ColabTeardownError(ColabPreflightError):
    """Raised when post-run session verification still sees an active runtime."""


@dataclass(frozen=True)
class ColabRunResult:
    """Summary of one guarded Colab run."""

    session_name: str
    gpu_tier: str
    worst_case_ccu: float
    account_balance_ccu: float | None
    returncode: int
    stdout: str
    stderr: str


SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


def compute_worst_case_ccu(gpu_tier: str, max_wall_minutes: float) -> float:
    """Return conservative CCU burn for ``gpu_tier`` over ``max_wall_minutes``."""
    tier = gpu_tier.upper()
    if tier not in BURN_RATE_CCU_PER_HOUR:
        allowed = ", ".join(sorted(BURN_RATE_CCU_PER_HOUR))
        raise ColabBudgetError(f"unsupported gpu_tier {gpu_tier!r}; allowed: {allowed}")
    if max_wall_minutes <= 0:
        raise ColabBudgetError("max_wall_minutes must be > 0")
    return round(BURN_RATE_CCU_PER_HOUR[tier] * (max_wall_minutes / 60.0), 4)


def validate_budget(
    *,
    gpu_tier: str,
    max_wall_minutes: float,
    max_ccu: float,
    override_ccu_cap: bool = False,
) -> float:
    """Validate wall-clock and CCU caps; return ``worst_case_ccu``."""
    if max_wall_minutes <= 0:
        raise ColabBudgetError("max_wall_minutes must be > 0")
    if max_ccu <= 0:
        raise ColabBudgetError("max_ccu must be > 0")
    if not override_ccu_cap:
        if max_wall_minutes > MAX_WALL_MINUTES_DEFAULT_CEILING:
            raise ColabBudgetError(
                f"max_wall_minutes={max_wall_minutes} exceeds ceiling "
                f"{MAX_WALL_MINUTES_DEFAULT_CEILING} without --override-ccu-cap"
            )
        if max_ccu > MAX_CCU_DEFAULT_CEILING:
            raise ColabBudgetError(
                f"max_ccu={max_ccu} exceeds ceiling "
                f"{MAX_CCU_DEFAULT_CEILING} without --override-ccu-cap"
            )
    worst_case = compute_worst_case_ccu(gpu_tier, max_wall_minutes)
    if worst_case > max_ccu:
        raise ColabBudgetError(
            f"worst-case burn {worst_case:.2f} CCU ({gpu_tier} for "
            f"{max_wall_minutes:g} min) exceeds max_ccu={max_ccu:.2f}"
        )
    return worst_case


def parse_balance_ccu(usage_output: str) -> float | None:
    """Extract numeric CCU balance from ``colab usage`` output when reported."""
    match = _BALANCE_RE.search(usage_output)
    if match is None:
        return None
    return float(match.group(1))


def _base_colab_cmd(colab_bin: str, auth: str, config_path: Path) -> list[str]:
    if auth not in ("adc", "oauth2"):
        raise ValueError(f"auth must be 'adc' or 'oauth2', got {auth!r}")
    return [colab_bin, f"--auth={auth}", "--config", str(config_path)]


def probe_account_balance(
    *,
    colab_bin: str = "colab",
    auth: str = "adc",
    config_path: Path,
    runner: SubprocessRunner = subprocess.run,
) -> float | None:
    """Run ``colab usage`` headlessly (stdin closed) and parse remaining CCUs."""
    cmd = [*_base_colab_cmd(colab_bin, auth, config_path), "usage"]
    try:
        proc = runner(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=USAGE_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ColabAuthError(
            f"{colab_bin!r} executable not found; install via 'uv tool install google-colab-cli'"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ColabAuthError(
            "colab usage timed out; OAuth interactive flow may be waiting on browser login"
        ) from exc

    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    lowered = combined.lower()
    if (
        "defaultcredentialserror" in lowered
        or "to authorize colab-cli, visit this url" in lowered
        or "failed to fetch compute-unit info" in lowered
        or "eoferror" in lowered
        or "401" in lowered
        or "403" in lowered
    ):
        raise ColabAuthError(
            "Google Colab CLI is not authenticated for headless execution "
            "(requires Google OAuth / ADC with scope "
            "'https://www.googleapis.com/auth/colaboratory')."
        )
    if proc.returncode != 0:
        raise ColabAuthError(
            f"colab usage exited with {proc.returncode}: {combined.strip()[:300]}"
        )
    return parse_balance_ccu(combined)


def build_remote_wrapper_source(target_script_source: str) -> str:
    """Wrap ``target_script_source`` so in-VM ``runtime.unassign()`` always fires."""
    return (
        "import sys as _colab_guard_sys\n"
        "try:\n"
        + textwrap.indent(target_script_source, "    ")
        + "\nfinally:\n"
        "    try:\n"
        "        from google.colab import runtime as _colab_guard_runtime\n"
        "        _colab_guard_runtime.unassign()\n"
        "    except Exception:\n"
        "        pass\n"
    )


def _teardown_session(
    *,
    colab_bin: str,
    auth: str,
    config_path: Path,
    session_name: str,
    runner: SubprocessRunner = subprocess.run,
) -> None:
    """Force-stop ``session_name`` and verify it is absent from ``colab sessions``."""
    base = _base_colab_cmd(colab_bin, auth, config_path)
    runner(
        [*base, "stop", "-s", session_name],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TEARDOWN_TIMEOUT_SECONDS,
        check=False,
    )
    sessions_proc = runner(
        [*base, "sessions"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TEARDOWN_TIMEOUT_SECONDS,
        check=False,
    )
    listing = f"{sessions_proc.stdout or ''}\n{sessions_proc.stderr or ''}"
    if session_name in listing:
        runner(
            [*base, "stop", "-s", session_name],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TEARDOWN_TIMEOUT_SECONDS,
            check=False,
        )
        recheck = runner(
            [*base, "sessions"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TEARDOWN_TIMEOUT_SECONDS,
            check=False,
        )
        recheck_listing = f"{recheck.stdout or ''}\n{recheck.stderr or ''}"
        if session_name in recheck_listing:
            raise ColabTeardownError(
                f"Colab session {session_name!r} remained active after two stop attempts"
            )


def run_with_colab_guard(
    script_path: str | Path,
    args: Sequence[str] = (),
    *,
    gpu_tier: str = "L4",
    max_wall_minutes: float = 120.0,
    max_ccu: float = 25.0,
    override_ccu_cap: bool = False,
    auth: str = "adc",
    colab_bin: str = "colab",
    env_vars: Mapping[str, str] | None = None,
    session_name: str | None = None,
    runner: SubprocessRunner = subprocess.run,
) -> ColabRunResult:
    """Execute ``script_path`` on Colab inside CCU, wall-clock, and teardown guards."""
    tier = gpu_tier.upper()
    worst_case_ccu = validate_budget(
        gpu_tier=tier,
        max_wall_minutes=max_wall_minutes,
        max_ccu=max_ccu,
        override_ccu_cap=override_ccu_cap,
    )
    script = Path(script_path)
    if not script.is_file():
        raise FileNotFoundError(f"Colab script does not exist: {script}")

    sess = session_name or f"oracle-664-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="oracle-colab-guard-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        config_path = tmp_root / "sessions.json"
        balance = probe_account_balance(
            colab_bin=colab_bin,
            auth=auth,
            config_path=config_path,
            runner=runner,
        )
        if balance is not None and balance < worst_case_ccu:
            raise ColabBudgetError(
                f"remaining Colab balance {balance:.2f} CCU is below worst-case "
                f"burn {worst_case_ccu:.2f} CCU"
            )

        wrapped_path = tmp_root / f"wrapped_{script.name}"
        wrapped_path.write_text(
            build_remote_wrapper_source(script.read_text(encoding="utf-8")),
            encoding="utf-8",
        )

        cmd = [*_base_colab_cmd(colab_bin, auth, config_path), "run", "-s", sess, "--timeout", "0"]
        if tier != "CPU":
            cmd.extend(["--gpu", tier])
        for key, value in (env_vars or {}).items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(f"invalid environment variable name: {key!r}")
            cmd.extend(["--env", f"{key}={value}"])
        cmd.append(str(wrapped_path))
        cmd.extend(str(item) for item in args)

        previous_handlers: dict[int, object] = {}

        def _handle_signal(signum: int, _frame: object) -> None:
            raise KeyboardInterrupt(f"received signal {signum}")

        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    previous_handlers[sig] = signal.signal(sig, _handle_signal)
                except ValueError:
                    # signal.signal only works in main thread
                    pass

        primary_exc: BaseException | None = None
        proc: subprocess.CompletedProcess[str] | None = None
        try:
            try:
                proc = runner(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=max_wall_minutes * 60.0,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                primary_exc = ColabTimeoutError(
                    f"Colab session {sess!r} exceeded max_wall_minutes={max_wall_minutes:g}"
                )
                raise primary_exc from exc
            except BaseException as exc:
                primary_exc = exc
                raise
        finally:
            for sig, prev in previous_handlers.items():
                try:
                    signal.signal(sig, prev)  # type: ignore[arg-type]
                except ValueError:
                    pass
            try:
                _teardown_session(
                    colab_bin=colab_bin,
                    auth=auth,
                    config_path=config_path,
                    session_name=sess,
                    runner=runner,
                )
            except BaseException:
                if primary_exc is None:
                    raise

        assert proc is not None
        return ColabRunResult(
            session_name=sess,
            gpu_tier=tier,
            worst_case_ccu=worst_case_ccu,
            account_balance_ccu=balance,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )


_SMOKE_SCRIPT = """\
import subprocess
proc = subprocess.run(
    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
    capture_output=True,
    text=True,
    check=False,
)
print(proc.stdout.strip() or proc.stderr.strip() or "CPU_RUNTIME")
raise SystemExit(proc.returncode)
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m colab.preflight",
        description="Run a Python script on Google Colab with hard CCU and teardown guards.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="Run GPU nvidia-smi smoke test and unassign.")
    mode.add_argument("--script", type=Path, help="Local Python script to execute remotely.")
    parser.add_argument("--gpu", default="L4", help="Accelerator tier: CPU, T4, L4, G4, A100, H100.")
    parser.add_argument("--max-wall-minutes", type=float, default=120.0)
    parser.add_argument("--max-ccu", type=float, default=25.0)
    parser.add_argument("--override-ccu-cap", action="store_true")
    parser.add_argument("--auth", choices=("adc", "oauth2"), default=os.environ.get("COLAB_CLI_AUTH", "adc"))
    parser.add_argument("--colab-bin", default=os.environ.get("COLAB_CLI_BIN", "colab"))
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments after '--' forwarded to script.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    forwarded = list(ns.script_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    temp_smoke: Path | None = None
    try:
        if ns.smoke:
            fd, raw_path = tempfile.mkstemp(prefix="colab_smoke_", suffix=".py")
            os.close(fd)
            temp_smoke = Path(raw_path)
            temp_smoke.write_text(_SMOKE_SCRIPT, encoding="utf-8")
            target = temp_smoke
        else:
            target = ns.script

        result = run_with_colab_guard(
            target,
            forwarded,
            gpu_tier=ns.gpu,
            max_wall_minutes=ns.max_wall_minutes,
            max_ccu=ns.max_ccu,
            override_ccu_cap=ns.override_ccu_cap,
            auth=ns.auth,
            colab_bin=ns.colab_bin,
        )
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        return result.returncode
    except ColabBudgetError as exc:
        print(f"colab budget check refused run: {exc}", file=sys.stderr)
        return 2
    except ColabAuthError as exc:
        print(f"colab auth preflight blocked: {exc}", file=sys.stderr)
        return 3
    except ColabTimeoutError as exc:
        print(f"colab wall-clock timeout: {exc}", file=sys.stderr)
        return 124
    finally:
        if temp_smoke is not None:
            temp_smoke.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
