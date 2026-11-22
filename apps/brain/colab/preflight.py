"""Headless Google Colab CLI preflight, CCU budget guard, and teardown wrapper (#664 Step 0.1).

Every remote Colab invocation MUST pass through ``run_with_colab_guard`` so that:
1. Worst-case compute-unit burn is bounded before provisioning a VM.
2. Account balance (when reported by ``colab usage``) covers the worst-case burn.
3. Forbidden credentials (``DATABASE_URL``, ``DIRECT_URL``, ``SUPABASE_SERVICE_ROLE_KEY``,
   ``OPENROUTER_API_KEY``, ``BRAIN_SHARED_TOKEN``) are hard-blocked before provisioning (L1),
   and allowed worker secrets (e.g. ``BRAIN_COLAB_WORKER_TOKEN``) are transferred via an
   ephemeral ``0600`` uploaded file that is unlinked before user code runs — never via CLI
   ``--env`` arguments visible in ``ps``.
4. Remote execution is wrapped in a ``__future__``-safe in-VM ``try ... finally`` calling
   ``google.colab.runtime.unassign()`` AND a host-side ``try ... finally`` calling
   ``colab stop -s <session>`` + ``colab sessions`` verification on normal exit, exception,
   wall-clock timeout, or SIGINT/SIGTERM.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import posixpath
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
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

# Locked decision L1: DB, Supabase service-role, OpenRouter, and shared brain tokens
# must NEVER be copied onto ephemeral Colab VMs.
FORBIDDEN_COLAB_ENV_KEYS: frozenset[str] = frozenset(
    {
        "DATABASE_URL",
        "DIRECT_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "OPENROUTER_API_KEY",
        "BRAIN_SHARED_TOKEN",
        "PROD_DIRECT_URL",
    }
)

_SECRET_KEY_HINT_RE = re.compile(
    r"(?:TOKEN|SECRET|KEY|PASSWORD|PASSWD|CREDENTIAL|AUTH)",
    re.IGNORECASE,
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MAX_WALL_MINUTES_DEFAULT_CEILING = 240.0
MAX_CCU_DEFAULT_CEILING = 200.0
USAGE_PROBE_TIMEOUT_SECONDS = 15.0
TEARDOWN_TIMEOUT_SECONDS = 30.0
REMOTE_SECRETS_PATH = "/content/.colab_guard_secrets.json"

_BALANCE_RE = re.compile(
    r"(?:current\s+balance|balance|available|remaining)[^\d\n]{0,24}(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ASSIGNMENTS_RE = re.compile(
    r"active\s+assignments\s*:\s*(\d+)",
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


def parse_active_assignments(usage_output: str) -> int | None:
    """Extract integer active assignment count from ``colab usage`` output when present."""
    match = _ASSIGNMENTS_RE.search(usage_output)
    if match is None:
        return None
    return int(match.group(1))


def parse_upload_spec(spec: str) -> tuple[Path, str]:
    """Parse ``LOCAL_PATH:REMOTE_PATH`` safely on both Windows drive paths and POSIX."""
    cleaned = spec.strip()
    if ":" not in cleaned:
        raise ValueError(f"upload spec must be LOCAL_PATH:REMOTE_PATH, got {spec!r}")
    local_raw, remote_raw = cleaned.rsplit(":", 1)
    if not local_raw or not remote_raw:
        raise ValueError(f"upload spec must be LOCAL_PATH:REMOTE_PATH, got {spec!r}")
    return Path(local_raw), remote_raw


def parse_download_spec(spec: str) -> tuple[str, Path]:
    """Parse ``REMOTE_PATH:LOCAL_PATH`` safely on both Windows drive paths and POSIX."""
    cleaned = spec.strip()
    if ":" not in cleaned:
        raise ValueError(f"download spec must be REMOTE_PATH:LOCAL_PATH, got {spec!r}")
    remote_raw, local_raw = cleaned.split(":", 1)
    if not remote_raw or not local_raw:
        raise ValueError(f"download spec must be REMOTE_PATH:LOCAL_PATH, got {spec!r}")
    return remote_raw, Path(local_raw)


def _partition_and_validate_env(
    env_vars: Mapping[str, str] | None,
    secret_env_vars: Mapping[str, str] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate L1 env policy and split plain env vars from secret env vars."""
    plain: dict[str, str] = {}
    secrets: dict[str, str] = {}

    for source_map, force_secret in ((env_vars or {}, False), (secret_env_vars or {}, True)):
        for key, value in source_map.items():
            if _ENV_NAME_RE.fullmatch(key) is None:
                raise ValueError(f"invalid environment variable name: {key!r}")
            if key.upper() in FORBIDDEN_COLAB_ENV_KEYS:
                raise ColabPreflightError(
                    f"L1 security policy forbids passing {key!r} onto a Google Colab runtime"
                )
            if force_secret or _SECRET_KEY_HINT_RE.search(key) is not None:
                plain.pop(key, None)
                secrets[key] = str(value)
            elif key not in secrets:
                plain[key] = str(value)

    return plain, secrets


def _split_future_header_and_body(target_script_source: str) -> tuple[str, str]:
    """Keep module docstring and ``from __future__ import ...`` at module top level."""
    lines = target_script_source.splitlines(keepends=True)
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    cleaned = "".join(lines)
    if not cleaned.strip():
        return "", ""

    try:
        tree = ast.parse(cleaned)
    except SyntaxError:
        return "", cleaned

    split_end_lineno = 0
    for idx, stmt in enumerate(tree.body):
        is_docstring = (
            idx == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
        is_future = isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__"
        if is_docstring or is_future:
            split_end_lineno = max(split_end_lineno, stmt.end_lineno or stmt.lineno)
        else:
            break

    if split_end_lineno <= 0:
        return "", cleaned

    all_lines = cleaned.splitlines(keepends=True)
    header = "".join(all_lines[:split_end_lineno])
    if header and not header.endswith("\n"):
        header += "\n"
    body = "".join(all_lines[split_end_lineno:])
    return header, body


def _discover_companion_colab_modules(script: Path) -> list[tuple[Path, str]]:
    """If ``script`` imports ``colab.<mod>``, stage sibling ``colab/*.py`` files for ``/content/colab``."""
    parent = script.resolve().parent
    if parent.name != "colab":
        return []
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    needed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "colab":
                for alias in node.names:
                    needed.add(alias.name)
            elif node.module.startswith("colab."):
                needed.add(node.module.split(".", 2)[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("colab."):
                    needed.add(alias.name.split(".", 2)[1])

    if not needed:
        return []

    uploads: list[tuple[Path, str]] = []
    init_py = parent / "__init__.py"
    if init_py.is_file():
        uploads.append((init_py, "/content/colab/__init__.py"))
    for mod_name in sorted(needed):
        candidate = parent / f"{mod_name}.py"
        if candidate.is_file():
            uploads.append((candidate, f"/content/colab/{mod_name}.py"))
    return uploads


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


def build_remote_wrapper_source(
    target_script_source: str,
    *,
    exec_mode_argv: Sequence[str] | None = None,
    plain_env_vars: Mapping[str, str] | None = None,
    secret_env_remote_path: str | None = None,
    add_content_sys_path: bool = False,
    defer_unassign_for_download: bool = False,
) -> str:
    """Wrap ``target_script_source`` keeping ``__future__`` imports first and guaranteeing ``unassign()``."""
    future_header, body = _split_future_header_and_body(target_script_source)

    prelude_lines: list[str] = [
        "import json as _colab_guard_json",
        "import os as _colab_guard_os",
        "import sys as _colab_guard_sys",
        "import warnings as _colab_guard_warnings",
        '_colab_guard_warnings.filterwarnings("ignore", message="To exit: use")',
    ]
    if add_content_sys_path:
        prelude_lines.append(
            'if "/content" not in _colab_guard_sys.path:\n'
            '    _colab_guard_sys.path.insert(0, "/content")'
        )
    if exec_mode_argv is not None:
        argv_literal = "[" + ", ".join(repr(str(a)) for a in exec_mode_argv) + "]"
        prelude_lines.append(f"_colab_guard_sys.argv = {argv_literal}")
        prelude_lines.append('__name__ = "__main__"')
    for k, v in sorted((plain_env_vars or {}).items()):
        prelude_lines.append(f"_colab_guard_os.environ[{k!r}] = {v!r}")
    if secret_env_remote_path is not None:
        prelude_lines.append(
            "try:\n"
            f"    with open({secret_env_remote_path!r}, 'r', encoding='utf-8') as _cg_sf:\n"
            "        _cg_secrets = _colab_guard_json.load(_cg_sf)\n"
            "    for _cg_k, _cg_v in _cg_secrets.items():\n"
            "        _colab_guard_os.environ[str(_cg_k)] = str(_cg_v)\n"
            "    del _cg_secrets\n"
            "finally:\n"
            "    try:\n"
            f"        _colab_guard_os.remove({secret_env_remote_path!r})\n"
            "    except OSError:\n"
            "        pass"
        )

    indented_prelude = textwrap.indent("\n".join(prelude_lines) + "\n", "    ")
    indented_body = textwrap.indent(body if body.strip() else "pass\n", "    ")
    if not indented_body.endswith("\n"):
        indented_body += "\n"

    if defer_unassign_for_download:
        finally_block = "finally:\n    pass\n"
    else:
        finally_block = (
            "finally:\n"
            "    try:\n"
            "        from google.colab import runtime as _colab_guard_runtime\n"
            "        _colab_guard_runtime.unassign()\n"
            "    except Exception:\n"
            "        pass\n"
        )

    return future_header + "try:\n" + indented_prelude + indented_body + finally_block


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


def _run_checked_step(
    cmd: list[str],
    *,
    step_label: str,
    session_name: str,
    max_wall_minutes: float,
    deadline: float,
    runner: SubprocessRunner,
) -> subprocess.CompletedProcess[str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ColabTimeoutError(
            f"Colab session {session_name!r} exceeded max_wall_minutes={max_wall_minutes:g} before {step_label}"
        )
    try:
        proc = runner(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ColabTimeoutError(
            f"Colab session {session_name!r} exceeded max_wall_minutes={max_wall_minutes:g} during {step_label}"
        ) from exc
    if proc.returncode != 0:
        raw_detail = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
        redacted = re.sub(
            r"colab-runtime-proxy-token=[^&\s]+",
            "colab-runtime-proxy-token=[REDACTED]",
            raw_detail,
        )[:400]
        raise ColabPreflightError(
            f"Colab step {step_label!r} failed (exit {proc.returncode}): {redacted}"
        )
    return proc


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
    secret_env_vars: Mapping[str, str] | None = None,
    install_packages: Sequence[str] = (),
    install_requirements: str | Path | None = None,
    uploads: Sequence[tuple[str | Path, str]] = (),
    downloads: Sequence[tuple[str | Path]] | Sequence[tuple[str, str | Path]] = (),
    session_name: str | None = None,
    runner: SubprocessRunner = subprocess.run,
) -> ColabRunResult:
    """Execute ``script_path`` on Colab inside CCU, wall-clock, secret, and teardown guards."""
    tier = gpu_tier.upper()
    worst_case_ccu = validate_budget(
        gpu_tier=tier,
        max_wall_minutes=max_wall_minutes,
        max_ccu=max_ccu,
        override_ccu_cap=override_ccu_cap,
    )
    plain_env, secret_env = _partition_and_validate_env(env_vars, secret_env_vars)

    script = Path(script_path)
    if not script.is_file():
        raise FileNotFoundError(f"Colab script does not exist: {script}")

    req_path: Path | None = None
    if install_requirements is not None:
        req_path = Path(install_requirements)
        if not req_path.is_file():
            raise FileNotFoundError(f"Colab requirements file does not exist: {req_path}")

    resolved_uploads: list[tuple[Path, str]] = []
    for local_item, remote_dest in _discover_companion_colab_modules(script):
        resolved_uploads.append((local_item, remote_dest))
    for local_item, remote_dest in uploads:
        lp = Path(local_item)
        if not lp.is_file():
            raise FileNotFoundError(f"Upload source file does not exist: {lp}")
        resolved_uploads.append((lp, str(remote_dest)))

    resolved_downloads = [(str(rem), Path(loc)) for rem, loc in downloads]
    needs_managed_session = bool(
        install_packages
        or req_path is not None
        or resolved_uploads
        or resolved_downloads
        or secret_env
    )

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
        base = _base_colab_cmd(colab_bin, auth, config_path)

        previous_handlers: dict[int, object] = {}

        def _handle_signal(signum: int, _frame: object) -> None:
            raise KeyboardInterrupt(f"received signal {signum}")

        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    previous_handlers[sig] = signal.signal(sig, _handle_signal)
                except ValueError:
                    pass

        primary_exc: BaseException | None = None
        proc: subprocess.CompletedProcess[str] | None = None
        deadline = time.monotonic() + (max_wall_minutes * 60.0)
        try:
            try:
                if not needs_managed_session:
                    wrapped_path.write_text(
                        build_remote_wrapper_source(script.read_text(encoding="utf-8")),
                        encoding="utf-8",
                    )
                    cmd = [*base, "run", "-s", sess, "--timeout", "0"]
                    if tier != "CPU":
                        cmd.extend(["--gpu", tier])
                    for key, value in plain_env.items():
                        cmd.extend(["--env", f"{key}={value}"])
                    cmd.append(str(wrapped_path))
                    cmd.extend(str(item) for item in args)
                    proc = runner(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=max_wall_minutes * 60.0,
                        check=False,
                    )
                else:
                    secret_remote: str | None = None
                    if secret_env:
                        secret_file = tmp_root / "secrets.json"
                        secret_file.write_text(
                            json.dumps(secret_env, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        try:
                            os.chmod(secret_file, 0o600)
                        except OSError:
                            pass
                        secret_remote = REMOTE_SECRETS_PATH
                        resolved_uploads.append((secret_file, REMOTE_SECRETS_PATH))

                    remote_script = f"/content/{script.name}"
                    resolved_uploads.insert(0, (script, remote_script))

                    install_specs: list[str] = []
                    if req_path is not None:
                        remote_req = f"/content/{req_path.name}"
                        resolved_uploads.insert(0, (req_path, remote_req))
                        install_specs.extend(["-r", remote_req])
                    install_specs.extend(str(pkg) for pkg in install_packages)

                    upload_plan: list[tuple[Path, str]] = []
                    stage_moves: list[tuple[str, str]] = []
                    chunk_reassemblies: list[tuple[list[str], str]] = []
                    max_single_upload = 8 * 1024 * 1024
                    for idx, (local_item, remote_dest) in enumerate(resolved_uploads):
                        file_size = local_item.stat().st_size
                        if file_size > max_single_upload:
                            part_remotes: list[str] = []
                            with local_item.open("rb") as src_fh:
                                part_no = 0
                                while chunk_bytes := src_fh.read(max_single_upload):
                                    part_local = tmp_root / f"_cg_part_{idx}_{part_no:04d}.bin"
                                    part_local.write_bytes(chunk_bytes)
                                    part_remote = f"/content/_cg_part_{idx}_{part_no:04d}.bin"
                                    upload_plan.append((part_local, part_remote))
                                    part_remotes.append(part_remote)
                                    part_no += 1
                            chunk_reassemblies.append((part_remotes, remote_dest))
                        else:
                            parent_dir = posixpath.dirname(remote_dest)
                            if parent_dir in ("", "/", "/content"):
                                upload_plan.append((local_item, remote_dest))
                            else:
                                staged_flat = f"/content/_cg_stage_{idx}_{local_item.name}"
                                upload_plan.append((local_item, staged_flat))
                                stage_moves.append((staged_flat, remote_dest))

                    argv_json = json.dumps([remote_script, *(str(a) for a in args)])
                    reasm_json = json.dumps(chunk_reassemblies)
                    moves_json = json.dumps(stage_moves)
                    specs_json = json.dumps(install_specs)
                    launcher_body = (
                        "import json as _cg_sub_json, os as _cg_sub_os, shutil as _cg_shutil, subprocess as _cg_sub, sys as _cg_sub_sys, threading as _cg_thr\n"
                        "def _cg_run_stream(_cmd, _env=None):\n"
                        "    _stop = _cg_thr.Event()\n"
                        "    def _hb():\n"
                        "        while not _stop.wait(20.0):\n"
                        "            try:\n"
                        "                _cg_sub_sys.stderr.write('[colab-guard-heartbeat]\\n')\n"
                        "                _cg_sub_sys.stderr.flush()\n"
                        "            except Exception:\n"
                        "                break\n"
                        "    _t = _cg_thr.Thread(target=_hb, daemon=True)\n"
                        "    _t.start()\n"
                        "    try:\n"
                        "        _proc = _cg_sub.Popen(_cmd, env=_env, stdout=_cg_sub.PIPE, stderr=_cg_sub.STDOUT, text=True, bufsize=1)\n"
                        "        assert _proc.stdout is not None\n"
                        "        for _line in _proc.stdout:\n"
                        "            _cg_sub_sys.stdout.write(_line)\n"
                        "            _cg_sub_sys.stdout.flush()\n"
                        "        return _proc.wait()\n"
                        "    finally:\n"
                        "        _stop.set()\n"
                        f"for _cg_parts, _cg_dst in _cg_sub_json.loads({reasm_json!r}):\n"
                        "    _cg_sub_os.makedirs(_cg_sub_os.path.dirname(_cg_dst) or '/content', exist_ok=True)\n"
                        "    with open(_cg_dst, 'wb') as _cg_out:\n"
                        "        for _cg_pt in _cg_parts:\n"
                        "            with open(_cg_pt, 'rb') as _cg_in:\n"
                        "                _cg_shutil.copyfileobj(_cg_in, _cg_out)\n"
                        "            _cg_sub_os.remove(_cg_pt)\n"
                        f"for _cg_src, _cg_dst in _cg_sub_json.loads({moves_json!r}):\n"
                        "    _cg_sub_os.makedirs(_cg_sub_os.path.dirname(_cg_dst), exist_ok=True)\n"
                        "    _cg_sub_os.replace(_cg_src, _cg_dst)\n"
                        f"_cg_pkgs = _cg_sub_json.loads({specs_json!r})\n"
                        "_cg_inst_rc = 0\n"
                        "if _cg_pkgs:\n"
                        "    if _cg_shutil.which('uv'):\n"
                        "        _cg_inst_rc = _cg_run_stream(['uv', 'pip', 'install', '--system', *_cg_pkgs])\n"
                        "    else:\n"
                        "        _cg_inst_rc = 1\n"
                        "    if _cg_inst_rc != 0:\n"
                        "        _cg_inst_rc = _cg_run_stream([_cg_sub_sys.executable, '-m', 'pip', 'install', '-q', *_cg_pkgs])\n"
                        "if _cg_inst_rc != 0:\n"
                        "    _cg_sub_sys.stdout.write(f'\\n__COLAB_INSTALL_RC__={_cg_inst_rc}\\n')\n"
                        "    _cg_sub_sys.stdout.flush()\n"
                        "else:\n"
                        "    _cg_env = _cg_sub_os.environ.copy()\n"
                        "    _cg_env['COLAB_GUARD_MANAGED_TEARDOWN'] = '1'\n"
                        "    _cg_env['PYTHONUNBUFFERED'] = '1'\n"
                        "    _cg_env['PYTHONPATH'] = '/content' + (':' + _cg_env['PYTHONPATH'] if _cg_env.get('PYTHONPATH') else '')\n"
                        f"    _cg_rc = _cg_run_stream([_cg_sub_sys.executable, *_cg_sub_json.loads({argv_json!r})], _cg_env)\n"
                        "    _cg_sub_sys.stdout.write(f'\\n__COLAB_EXEC_RC__={_cg_rc}\\n')\n"
                        "    _cg_sub_sys.stdout.flush()\n"
                    )
                    wrapped_path.write_text(
                        build_remote_wrapper_source(
                            launcher_body,
                            plain_env_vars=plain_env,
                            secret_env_remote_path=secret_remote,
                            add_content_sys_path=True,
                            defer_unassign_for_download=True,
                        ),
                        encoding="utf-8",
                    )

                    new_cmd = [*base, "new", "-s", sess]
                    if tier != "CPU":
                        new_cmd.extend(["--gpu", tier])
                    try:
                        _run_checked_step(
                            new_cmd,
                            step_label="colab new",
                            session_name=sess,
                            max_wall_minutes=max_wall_minutes,
                            deadline=deadline,
                            runner=runner,
                        )
                    except ColabPreflightError:
                        # One bounded retry on transient Colab backend assignment failure
                        runner(
                            [*base, "stop", "-s", sess],
                            stdin=subprocess.DEVNULL,
                            capture_output=True,
                            text=True,
                            timeout=TEARDOWN_TIMEOUT_SECONDS,
                            check=False,
                        )
                        time.sleep(3.0)
                        _run_checked_step(
                            new_cmd,
                            step_label="colab new (retry)",
                            session_name=sess,
                            max_wall_minutes=max_wall_minutes,
                            deadline=deadline,
                            runner=runner,
                        )

                    for local_item, remote_dest in upload_plan:
                        _run_checked_step(
                            [*base, "upload", "-s", sess, str(local_item), remote_dest],
                            step_label=f"colab upload -> {remote_dest}",
                            session_name=sess,
                            max_wall_minutes=max_wall_minutes,
                            deadline=deadline,
                            runner=runner,
                        )

                    exec_remaining = deadline - time.monotonic()
                    if exec_remaining <= 0:
                        raise ColabTimeoutError(
                            f"Colab session {sess!r} exceeded max_wall_minutes={max_wall_minutes:g} before exec"
                        )
                    proc = runner(
                        [*base, "exec", "-s", sess, "--timeout", "0", "-f", str(wrapped_path)],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=exec_remaining,
                        check=False,
                    )
                    inst_m = re.search(r"__COLAB_INSTALL_RC__=(-?\d+)", proc.stdout or "")
                    if inst_m and int(inst_m.group(1)) != 0:
                        detail = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()[-1200:]
                        raise ColabPreflightError(
                            f"Colab staged package install failed (rc={inst_m.group(1)}): {detail}"
                        )
                    rc_m = re.search(r"__COLAB_EXEC_RC__=(-?\d+)", proc.stdout or "")
                    if rc_m:
                        real_rc = int(rc_m.group(1))
                        cleaned_stdout = re.sub(r"\n?__COLAB_EXEC_RC__=-?\d+\n?", "\n", proc.stdout or "")
                        proc = subprocess.CompletedProcess(
                            proc.args,
                            real_rc,
                            cleaned_stdout,
                            proc.stderr,
                        )

                    if proc.returncode == 0 and resolved_downloads:
                        for remote_src, local_dest in resolved_downloads:
                            local_dest.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                _run_checked_step(
                                    [*base, "download", "-s", sess, remote_src, str(local_dest)],
                                    step_label=f"colab download {remote_src}",
                                    session_name=sess,
                                    max_wall_minutes=max_wall_minutes,
                                    deadline=deadline,
                                    runner=runner,
                                )
                            except ColabPreflightError as dl_exc:
                                exec_out = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()[-1500:]
                                raise ColabPreflightError(
                                    f"{dl_exc}\n--- remote exec output ---\n{exec_out}"
                                ) from dl_exc
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
        description="Run a Python script on Google Colab with hard CCU, secret, and teardown guards.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="Run GPU nvidia-smi smoke test and unassign.")
    mode.add_argument("--script", type=Path, help="Local Python script to execute remotely.")
    parser.add_argument("--gpu", default="L4", help="Accelerator tier: CPU, T4, L4, G4, A100, H100.")
    parser.add_argument("--max-wall-minutes", type=float, default=120.0)
    parser.add_argument("--max-ccu", type=float, default=25.0)
    parser.add_argument("--override-ccu-cap", action="store_true")
    parser.add_argument(
        "--install",
        action="append",
        default=[],
        metavar="PKG_SPEC",
        help="Install a package spec inside the Colab VM before exec (repeatable).",
    )
    parser.add_argument("--install-requirements", type=Path, default=None)
    parser.add_argument(
        "--upload",
        action="append",
        default=[],
        metavar="LOCAL:REMOTE",
        help="Upload a local file to the Colab VM before exec (repeatable).",
    )
    parser.add_argument(
        "--download",
        action="append",
        default=[],
        metavar="REMOTE:LOCAL",
        help="Download a remote file from the Colab VM before teardown (repeatable).",
    )
    parser.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="ENV_NAME",
        help="Forward host environment variable by name (never pass secret values on argv).",
    )
    parser.add_argument("--auth", choices=("adc", "oauth2"), default=os.environ.get("COLAB_CLI_AUTH", "adc"))
    parser.add_argument("--colab-bin", default=os.environ.get("COLAB_CLI_BIN", "colab"))
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments after '--' forwarded to script.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    for token in raw:
        if token == "--pass-env" or token.startswith("--pass-env="):
            if "=" in token and "=" in token.split("=", 1)[1]:
                print(
                    "colab preflight error: --pass-env takes ENV_NAME only (never KEY=VALUE on argv)",
                    file=sys.stderr,
                )
                return 2

    parser = _build_parser()
    ns = parser.parse_args(argv)
    forwarded = list(ns.script_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    temp_smoke: Path | None = None
    try:
        forwarded_env: dict[str, str] = {}
        for env_name in ns.pass_env:
            if "=" in env_name:
                raise ColabPreflightError(
                    "--pass-env accepts variable names only (read from host environment), never KEY=VALUE"
                )
            if env_name not in os.environ:
                raise ColabPreflightError(f"--pass-env variable {env_name!r} is not set in host environment")
            forwarded_env[env_name] = os.environ[env_name]

        uploads = [parse_upload_spec(item) for item in ns.upload]
        downloads = [parse_download_spec(item) for item in ns.download]

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
            env_vars=forwarded_env,
            install_packages=ns.install,
            install_requirements=ns.install_requirements,
            uploads=uploads,
            downloads=downloads,
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
    except ColabPreflightError as exc:
        print(f"colab preflight error: {exc}", file=sys.stderr)
        return 2
    finally:
        if temp_smoke is not None:
            temp_smoke.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
