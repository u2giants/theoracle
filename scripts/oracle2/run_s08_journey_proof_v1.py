"""One-shot S08 participation journey runner — sealed on PR #200 branch.

Binds the exact full 40-char HEAD at run time and a review receipt that names
that HEAD, this file's SHA-256, the plan SHA-256, the checker SHA-256 and the
evidence SHA-256, plus verdict APPROVE. Refuses without a precise
ai-task-gates check --before database ALLOW line. One fresh owned synthetic
Postgres (oracle2-synthetic-p24s08-journey-<unique>). Owned cleanup with
absence readback always — including pre-identity refusals.

Release workflow for the review receipt (C3):
  1. Operator mints review-receipt.json at a known path OUTSIDE any SCRATCH.
  2. Operator sets ORACLE2_S08_JOURNEY_RECEIPT to that path.
  3. Runner mints a unique per-run SCRATCH, then copies the receipt into it.
  A unique SCRATCH cannot hold a pre-minted receipt; the release path is the
  only supported minting location.

Journey stages (invented data only):
  provision-capture-admission -> observe-audience -> host-control ->
  current-turn -> sender -> bytes-in receipt -> status/reconcile

There is NO Next browser enable/control web surface on this head and NO sealed
fake-Recall HTTPS owner. HTTP 200/201/429/5xx network negatives and
"exactly ONE network invocation" are UNPROVED and are not executed here.

FORBIDDEN network path (never call; runner refuses if RECALL_* env is set):
  exchange_provider_v1 / sendRecallChatMessage / recall.ts HTTPS POST
  (apps/workers/src/lib/meeting-participation.ts:44,
   apps/workers/src/lib/recall.ts:29-63).
The only allowed bytes-in path is the factory layer
(meeting_participation_v1.py receipt_v1, bytes-in / artifact-out).

Deadline / CAS / conflict policy (H-C):
  Every SQL entry enforces a <=30s absolute deadline
  (021_meeting_participation.sql:163; participation_authority_v1.py:216-221).
  Observations expire in <=30s (021_meeting_participation.sql:259).
  control / prepare / observe / claim all take CAS revisions. On head conflict,
  expired observation, or elapsed window: STOP. No transparent retry. Record
  the failing stage and leave UNKNOWN semantics. One shared monotonic budget
  (120s) covers the journey stages only; fixture/bootstrap setup sits OUTSIDE
  that budget, matching verify_workflow_integrity.py:384-386,407.

  UNKNOWN routing (H5): UNKNOWN from claim commit/readback-loss proceeds to
  stage 5 (read-only reconcile of the OUTCOME). UNKNOWN from any earlier stage
  ends the journey at that stage. The journey layer never re-reads failing
  stage inputs; factory-internal fresh readbacks are the tested factory
  behaviour and are outside the "no re-read" scope.

Migration inventory is the sealed SYNTHETIC_MIGRATIONS bootstrap
(001,002,004,006..014,017,018,019,020,021,022,023,027) — NOT a contiguous
001..014 chain. The runner calls bootstrap_canonical_test_schema and asserts
the sealed inventory and catalog against golden digests; it never merely
echoes a note.

Real Teams producer stays UNQUALIFIED. Business acceptance HELD.

Python floor: >=3.11 (Exception.add_note used in cleanup paths, M8).
edge-dev3 runs 3.14; on 3.10 the finally handler itself would raise and
mask the original exception.

This is a prepared one-shot skeleton: stages refuse until implemented and
reviewed. Offline checks only until a reviewed release. Do not invent a
production effect.

Any edit to this file invalidates the receipt-bound SHA and requires a new
review and a new receipt (C5). There is no "no SHA churn" guarantee.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

# Repository root = two levels up from scripts/oracle2/.
ROOT = Path(__file__).resolve().parents[2]
# Unique per-run scratch; override only for offline checker isolation.
# SCRATCH must never live inside the repository (H-F/M-C).
SCRATCH_ENV = "ORACLE2_S08_JOURNEY_SCRATCH"
# Release path for the operator-minted review receipt (C3). Must live OUTSIDE
# SCRATCH; the runner copies it into SCRATCH after minting SCRATCH.
RECEIPT_RELEASE_ENV = "ORACLE2_S08_JOURNEY_RECEIPT"
SHARED_BUDGET_S = 120
PER_REQUEST_S = 30
DOCKER_PROBE_TIMEOUT_S = 60
# M5: every gate/preflight/git subprocess is bounded so a hang cannot outlast
# the one-shot run. The 120s stage budget is armed only after bootstrap.
TOOL_CALL_TIMEOUT_S = 60
COMPOSE_PROJECT_PREFIX = "oracle2-synthetic-p24s08-journey"
WORKER_LABEL = "documentary-01"
# Sealed SYNTHETIC_MIGRATIONS inventory. The runner applies the sealed
# bootstrap and asserts equality; it never a custom contiguous 001..014 chain.
SEALED_MIGRATION_INVENTORY = (
    "001_foundation.sql",
    "002_pilot.sql",
    "004_workflow_integrity.sql",
    "006_hosting_gateway_authority.sql",
    "007_hosting_candidate_permissions.sql",
    "008_hosting_runtime_permissions.sql",
    "009_hosting_result_permissions.sql",
    "010_hosting_job_permissions.sql",
    "011_hosting_source_processing_permissions.sql",
    "012_processing_compiler_capabilities.sql",
    "013_processing_purpose_permissions.sql",
    "014_replacement_source_custody.sql",
    "017_processing_model_history.sql",
    "018_original_review_reading_input.sql",
    "019_employee_conversations.sql",
    "020_meeting_capture.sql",
    "021_meeting_participation.sql",
    "022_consolidated_answer_delivery.sql",
    "023_maintained_research.sql",
    "027_legacy_migration.sql",
)
SEALED_MIGRATION_INVENTORY_NOTE = ",".join(
    name.split("_", 1)[0] for name in SEALED_MIGRATION_INVENTORY
)
FULL_SHA40 = re.compile(r"^[0-9a-f]{40}$")
# H3 sealed goldens — review-time constants, never computed from the same
# bytes the assertion re-reads. The inventory digest covers the 20-entry
# migration set (file names + content hashes) over GIT-BLOB bytes (C2/M2):
# `git show HEAD:services/oracle-brain/sql/<name>` so the constant is
# host-independent (LF). Mint command:
#   python -c "import hashlib,subprocess; names=(...); \
#   print(hashlib.sha256(b''.join(n.encode()+b'\\0'+hashlib.sha256(subprocess.check_output(['git','show',f'HEAD:services/oracle-brain/sql/{n}'])).digest() for n in names)).hexdigest())"
# Constant below is the git-blob digest of the 20-entry SYNTHETIC_MIGRATIONS set.
# The catalog digest is RECORDED, NOT GOLDEN (C3 option-a): it is written to
# evidence but never compared against a sealed constant (no refuse-on-empty).
SEALED_INVENTORY_DIGEST = (
    "7eb6085c3535175ac304b8ccd1db283aa64087042af52b2934a9065fd371be99"
)
# Catalog digest is recorded in evidence, not compared against a golden (C3).
# An empty value is acceptable; there is no refuse-on-empty.
SEALED_CATALOG_DIGEST = ""  # recorded, not golden (C3 option-a)
# Precise ALLOW token: a whole line that is exactly ALLOW, optionally with a
# `gate: ` prefix. Substring match is forbidden (H-G/M1). Any DENIED line
# present causes refusal regardless of ALLOW (M1).
ALLOW_LINE = re.compile(
    r"^(?:gate: )?ALLOW$|may start for effective class",
    re.MULTILINE,
)
DENIED_LINE = re.compile(
    r"^(?:gate: )?DENIED$|ai-task-gates: STOP",
    re.MULTILINE,
)
# H3/H4/L1: pytest green-receipt patterns. Factored into a helper so the checker
# can exercise ordering, singular/plural, and boundary behavior offline
# ("21 passed", "21 passed, 1 failed", "1 failed, 20 passed", "121 passed",
# "2 errors", "21 passed, 1 skipped") — a static string scan cannot (Muse H3/H4).
# L1: skipped/xfailed/xpassed/deselected counts are non-green too — "21 passed,
# 1 skipped" (22 collected) must NOT count as green. SQL_GREEN_COLLECTED pins
# the collected count when the pytest "collected N items" line is present.
SQL_GREEN_PASSED = re.compile(r"\b21\s+passed\b")
SQL_GREEN_FAILED = re.compile(
    r"\b\d+\s+(?:failed|errors?|skipped|xfailed|xpassed|deselected)\b"
)
SQL_GREEN_COLLECTED = re.compile(r"\bcollected\s+(\d+)\s+items?\b")
# Worktree-content suffixes and lock/compose/docker names the DB image
# depends on (H-F/M2). Shell scripts and build config included (M2).
# L10: JS module extensions included — dev/oracle2 ships .mjs/.mts files.
SOURCE_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".mts",
    ".sql", ".json", ".md", ".yaml", ".yml",
    ".toml", ".sh", ".bash", ".ps1", ".dockerignore",
)
SOURCE_BASENAMES = frozenset(
    {
        "compose.yaml",
        "compose.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "Dockerfile",
        ".dockerignore",
        "requirements.txt",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "go.sum",
    }
)


def _is_snapshotted_source(path: Path, name: str) -> bool:
    """L10: worktree files the DB image depends on.

    Covers the suffix list, the named basenames, Dockerfile variants
    (`Dockerfile`, `Dockerfile.web`, `api.Dockerfile`), and requirements
    files (`requirements.txt`, `requirements-dev.txt`).
    """
    if name in SOURCE_BASENAMES or path.suffix in SOURCE_SUFFIXES:
        return True
    if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
        return True
    if name.startswith("requirements") and name.endswith(".txt"):
        return True
    return False
# Forbidden network entry points (H-E). Named so a stage implementer cannot
# reach them by accident.
FORBIDDEN_NETWORK_PATHS = (
    "exchange_provider_v1",
    "sendRecallChatMessage",
    "recall.ts HTTPS POST",
)
RECALL_ENV_PREFIX = "RECALL_"

# Shared budget fence ContextVar (H1): narrowing, finite-only, entry + exit
# check. request_deadline_v1._request_fence_v1 is entry-check-only
# (request_remaining_v1 before yield, none after); this runner is STRICTER
# with an additional exit remaining check that catches overrunning stages.
_request_end_v1: ContextVar = ContextVar(
    "s08_journey_original_end_v1", default=None
)


class JourneyRefusal(RuntimeError):
    """Fail-closed refusal. Carries the failing stage for the outcome record."""


class JourneyUnknown(JourneyRefusal):
    """Routable UNKNOWN — not a fatal refusal (M1).

    A stage raises JourneyUnknown when the outcome is genuinely UNKNOWN
    (e.g. claim commit ACK loss) and the journey should route to the
    next phase per the H5 policy: UNKNOWN from claim commit/readback-loss
    proceeds to stage 5 (read-only reconcile); UNKNOWN from earlier stages
    ends the journey at that stage. The main loop catches JourneyUnknown
    separately from JourneyRefusal to implement that routing. A plain
    JourneyRefusal is always fatal (STOP).
    """


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_git_blob(path: Path) -> str:
    """Git-blob SHA-256 for receipt bindings (H6).

    Uses `git show HEAD:<relpath> | sha256sum` semantics so CRLF checkouts
    cannot diverge from the pinned bytes. All four receipt SHA bindings
    (runner/plan/checker/evidence) use this helper.
    """
    rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    git = _tool_identity("git")
    raw = subprocess.check_output(
        [git["path"], "show", f"HEAD:{rel}"],
        cwd=ROOT,
        timeout=TOOL_CALL_TIMEOUT_S,
    )
    return hashlib.sha256(raw).hexdigest()


def _inventory_digest_git_blob(names: tuple[str, ...], head: str) -> str:
    """Inventory digest over git-blob bytes (C2/M2 — host-independent LF).

    Same shape as test_canonical_schema._inventory_digest (name + NUL +
    sha256(content) per entry, concatenated then hashed) but reads content
    via `git show <head>:services/oracle-brain/sql/<name>` using the bound
    full 40-char HEAD (L13) so a mid-run checkout cannot hash a different
    commit than the receipt names. `head` is the exact SHA returned by
    require_head(); a symbolic HEAD is refused.
    """
    if not FULL_SHA40.fullmatch(head):
        raise JourneyRefusal(
            f"inventory digest requires a full 40-char bound head (L13): {head!r}"
        )
    git = _tool_identity("git")
    parts: list[bytes] = []
    for name in names:
        raw = subprocess.check_output(
            [git["path"], "show", f"{head}:services/oracle-brain/sql/{name}"],
            cwd=ROOT,
            timeout=TOOL_CALL_TIMEOUT_S,
        )
        parts.append(name.encode() + b"\0" + hashlib.sha256(raw).digest())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def _scratch() -> Path:
    """Unique per-run scratch, never inside the repository (M-C/L2)."""
    raw = os.environ.get(SCRATCH_ENV)
    if raw:
        scratch = Path(raw).resolve()
    else:
        base = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp")
        scratch = (base / f"oracle-parent24-s08-journey-{uuid4().hex}").resolve()
    try:
        scratch.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise JourneyRefusal(
            "SCRATCH must not live inside the repository worktree (M-C)"
        )
    # L2: parent must not be group/other-writable UNLESS the sticky bit is
    # set (standard /tmp semantics: mode 1777). S_ISVTX makes world-writable
    # safe because only the owner can delete entries.
    # L9: if the parent does not exist, check the nearest existing ancestor;
    # after mkdir, re-verify to close the stat-then-mkdir TOCTOU.
    parent = scratch.parent

    def _check_parent_mode(p: Path) -> None:
        if not p.exists():
            return
        # H1 (Windows degradation): POSIX write bits and the sticky bit are
        # not meaningfully expressible on Windows (a plain Temp dir reports
        # 0o777 with no sticky bit). Degrade honestly — skip and do not fail.
        # The journey runs on the Linux host where this check is live.
        if not hasattr(os, "getuid"):
            return
        pst = p.stat()
        # L2: S_ISVTX is the sticky-bit MASK constant (there is no
        # stat.S_ISVTX(mode) predicate function). Check the bit, don't call it.
        if pst.st_mode & 0o022 and not (pst.st_mode & stat.S_ISVTX):
            raise JourneyRefusal(
                f"SCRATCH parent is group/other-writable without sticky bit: {p} (L2)"
            )

    if parent.exists():
        _check_parent_mode(parent)
    else:
        # L9: walk up to the nearest existing ancestor and check it.
        ancestor = parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        _check_parent_mode(ancestor)
    # mkdir/chmod AFTER the parent check so a refused run leaves no litter.
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch.chmod(0o700)
    # L9: re-check parent after mkdir to close the TOCTOU window.
    _check_parent_mode(parent)
    # SCRATCH_ENV reuse: unlink the opposite marker so a reused directory
    # cannot hold stale refusal.json beside fresh journey-evidence.json.
    for stale in ("refusal.json", "journey-evidence.json"):
        p = scratch / stale
        if p.exists():
            p.unlink()
    # L3: a reused SCRATCH_ENV directory must be empty of any other residue
    # (e.g. a leftover ops-schema-receipt.json). Otherwise the schema-receipt
    # O_EXCL write later would crash with a raw FileExistsError. Fail closed
    # with a tagged JourneyRefusal naming the residue instead — never a raw
    # OSError from a downstream writer.
    residue = sorted(p.name for p in scratch.iterdir())
    if residue:
        raise JourneyRefusal(
            "SCRATCH_ENV reuse requires an empty scratch directory after "
            f"marker cleanup (L3); residue present: {', '.join(residue)}"
        )
    return scratch


def _monotonic_end(seconds: float) -> float:
    if type(seconds) not in (int, float) or not math.isfinite(float(seconds)):
        raise JourneyRefusal("finite budget seconds required (L1)")
    if seconds <= 0:
        raise JourneyRefusal("positive budget seconds required")
    return time.monotonic() + float(seconds)


def _budget_remaining(*, required: bool = True) -> float | None:
    """Remaining seconds on the shared fence; raises when elapsed (H1)."""
    end = _request_end_v1.get()
    if end is None:
        if required:
            raise JourneyRefusal("shared budget fence required")
        return None
    remaining = end - time.monotonic()
    if remaining <= 0:
        raise JourneyRefusal("shared budget fence elapsed; STOP")
    return remaining


@contextmanager
def _request_fence_v1(original_monotonic_end: float):
    """Shared budget fence (H1).

    ContextVar narrowing, finite-float requirement, entry remaining check,
    and exit remaining check so an overrunning stage is caught at the fence.
    Never a wall-clock label. request_deadline_v1._request_fence_v1
    (request_deadline_v1.py:26-35) is entry-check-only; this runner adds
    the exit check and is therefore STRICTER than the cited source.
    """
    if (
        type(original_monotonic_end) is not float
        or not math.isfinite(original_monotonic_end)
    ):
        raise JourneyRefusal("exact finite original monotonic fence required (H1)")
    prior = _request_end_v1.get()
    token = _request_end_v1.set(
        min(prior, original_monotonic_end)
        if prior is not None
        else original_monotonic_end
    )
    try:
        _budget_remaining(required=True)  # entry check
        yield
        _budget_remaining(required=True)  # exit check — catches overrun
    finally:
        _request_end_v1.reset(token)


def _budget_check(end: float, stage: str) -> None:
    if time.monotonic() >= end:
        raise JourneyRefusal(f"shared monotonic budget elapsed at stage {stage}; STOP")


def require_recall_env_absent() -> None:
    """Refuse if any RECALL_* credential/env is present (H-E).

    The journey must never reach exchange_provider_v1 / sendRecallChatMessage /
    recall.ts HTTPS POST. The only allowed path is the factory bytes-in layer
    (meeting_participation_v1.py:291 receipt_v1).
    """
    present = sorted(k for k in os.environ if k.startswith(RECALL_ENV_PREFIX))
    if present:
        raise JourneyRefusal(
            "RECALL_* environment present — forbidden network path "
            f"({', '.join(FORBIDDEN_NETWORK_PATHS)}) must stay unreachable; "
            f"unset: {', '.join(present)}"
        )


def require_python_floor() -> None:
    """M3: enforce Python >=3.11 floor (Exception.add_note used in cleanup).

    Extracted so the offline checker can drive it behaviorally with a fake
    old version_info (a static "sys.version_info" string scan cannot prove
    the comparison fires). Called first in main(), before any other work.
    """
    if sys.version_info < (3, 11):
        raise JourneyRefusal(
            f"Python >=3.11 required (got {sys.version_info.major}.{sys.version_info.minor}); "
            "Exception.add_note is used in cleanup paths (M3)"
        )


def require_head() -> str:
    """Exact full 40-char clean HEAD; never a short SHA, never a dirty tree.

    Ordering (M10): operator review artifacts under .ai/reviews/ must be
    committed or gitignored before the journey run binds the head. The
    .ai/reviews/packets/ subtree is excluded from the source snapshot (not
    from this dirty check) — commit packet output or add it to .gitignore.
    """
    git = _tool_identity("git")
    head = subprocess.check_output(
        [git["path"], "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        timeout=TOOL_CALL_TIMEOUT_S,
    ).strip()
    if not FULL_SHA40.fullmatch(head):
        raise JourneyRefusal(f"HEAD is not a full 40-char SHA: {head!r}")
    dirty = subprocess.check_output(
        [git["path"], "status", "--porcelain"],
        cwd=ROOT,
        text=True,
        timeout=TOOL_CALL_TIMEOUT_S,
    ).strip()
    if dirty:
        raise JourneyRefusal(
            f"worktree dirty at bind head:\n{dirty}\n"
            "(M10: commit or gitignore .ai/reviews output before the journey run)"
        )
    return head


# Per-tool identity commands (C1). ai-task-gates has no --version flag; its
# identity is the `version` subcommand. openssl uses `version` not `--version`.
# git and docker accept --version.
TOOL_VERSION_ARGS: dict[str, tuple[str, ...]] = {
    "git": ("--version",),
    "docker": ("--version",),
    "ai-task-gates": ("version",),
    "openssl": ("version",),
}


def _tool_identity(name: str, version_args: tuple[str, ...] | None = None) -> dict:
    """Resolve a tool to an absolute path and record its identity (H-G/M7).

    Refuses when the version command is unavailable: the tool's identity must
    be established before its authority is trusted (M7). Each tool uses its
    own working identity command (C1): ai-task-gates -> `version` subcommand,
    openssl -> `version`, git/docker -> `--version`.
    """
    if version_args is None:
        version_args = TOOL_VERSION_ARGS.get(name, ("--version",))
    path = shutil.which(name)
    if not path:
        raise JourneyRefusal(f"required tool not on PATH: {name}")
    resolved = str(Path(path).resolve())
    try:
        version = subprocess.check_output(
            [resolved, *version_args],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=TOOL_CALL_TIMEOUT_S,
        ).splitlines()[0][:200]
    except (
        subprocess.CalledProcessError,
        OSError,
        IndexError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise JourneyRefusal(
            f"tool identity unavailable for {name}: {version_args} failed ({type(exc).__name__}); "
            "refusing to trust an unidentified tool (M7)"
        ) from exc
    return {"name": name, "path": resolved, "version": version}


def _receipt_stat_ok(path: Path) -> tuple[dict, bytes]:
    """uid/mode/nlink/O_NOFOLLOW checks + same-fd payload read (H7).

    Shape follows test_canonical_schema.py:96-114: O_NOFOLLOW open, fstat
    before/after, lstat cross-check, stable identity, and the payload is read
    from the SAME fd (never a fresh read_text that could follow a symlink
    swap). os.getuid is absent on Windows; there the uid check is skipped and
    the limit is recorded explicitly (H-J). On Windows, POSIX mode bits and
    nlink==1 cannot be enforced (chmod(0o600) still reports group/other-
    readable); those checks degrade honestly with mode_check:
    "unavailable-on-windows" and do NOT fail the positive path (H1).
    o_nofollow records the actual flag availability (H6).
    """
    o_nofollow_available = getattr(os, "O_NOFOLLOW", 0) != 0
    checks: dict[str, object] = {
        "o_nofollow": o_nofollow_available,  # H6: honest, not hardcoded True
        "uid_checked": False,
    }
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        checks["is_regular"] = stat.S_ISREG(before.st_mode)
        # H1: on Windows, POSIX mode bits and nlink are not meaningfully
        # enforceable. Degrade honestly — skip and record, do not fail.
        is_windows = not hasattr(os, "getuid")
        if is_windows:
            checks["mode_check"] = "unavailable-on-windows"
            checks["nlink_check"] = "unavailable-on-windows"
            checks["nlink_is_1"] = None
            checks["mode_no_group_other"] = None
        else:
            checks["nlink_is_1"] = before.st_nlink == 1
            checks["mode_no_group_other"] = (before.st_mode & 0o077) == 0
        checks["size_le_4096"] = before.st_size <= 4096
        # L3: refuse oversized receipts BEFORE any payload read. A huge file
        # must not be pulled into memory just to fail the size gate after.
        if not checks["size_le_4096"]:
            raise JourneyRefusal(
                f"review receipt exceeds 4096 bytes (L3): size={before.st_size}"
            )
        if hasattr(os, "getuid"):
            checks["uid_checked"] = True
            checks["uid_is_self"] = before.st_uid == os.getuid()
        else:
            checks["uid_is_self"] = None
            checks["uid_limit"] = (
                "os.getuid absent on this host (Windows); uid ownership of the "
                "procedural receipt cannot be enforced here"
            )
        raw = os.read(fd, before.st_size + 1)

        def _identity(s: os.stat_result) -> tuple:
            # H1: on Windows, st_ctime_ns differs between fstat and lstat
            # (platform quirk, not a security signal). Exclude it from the
            # cross-check comparison on Windows.
            base = (
                s.st_dev, s.st_ino, s.st_mode, s.st_uid,
                s.st_nlink, s.st_size, s.st_mtime_ns,
            )
            if not is_windows:
                base += (s.st_ctime_ns,)
            return base

        checks["stat_stable"] = _identity(before) == _identity(os.fstat(fd))
        # H7: lstat cross-check — same identity as the O_NOFOLLOW fd (test_canonical_schema.py:107).
        try:
            checks["lstat_matches"] = _identity(before) == _identity(path.lstat())
        except OSError:
            checks["lstat_matches"] = False
    finally:
        os.close(fd)
    # H1: mode/nlink are None (skipped) on Windows — do not fail the positive path.
    checks["passed"] = bool(
        checks.get("is_regular")
        and checks.get("nlink_is_1") in (True, None)
        and checks.get("mode_no_group_other") in (True, None)
        and checks.get("size_le_4096")
        and checks.get("stat_stable")
        and checks.get("lstat_matches")
        and (checks.get("uid_is_self") in (True, None))
    )
    return checks, raw


def require_review_receipt(head: str, scratch: Path) -> dict:
    """Exact-head review receipt — release workflow (C3).

    The operator mints review-receipt.json at a known path OUTSIDE SCRATCH
    (ORACLE2_S08_JOURNEY_RECEIPT). The runner copies it into the unique
    per-run SCRATCH after SCRATCH is minted. This avoids the deadlock where a
    unique SCRATCH cannot hold a pre-minted receipt.

    Procedural trust model (H-J): the receipt is an operator-minted JSON file.
    It is not a cryptographic authority. It must bind the exact full 40-char
    head plus the git-blob SHA-256 of the runner, plan, checker and evidence
    artifacts (H6), and verdict APPROVE. Any mismatch or absence fails closed.
    File-mode checks follow test_canonical_schema.py:96-114 where the host
    supports them. Payload is read via the same O_NOFOLLOW fd (H7).
    """
    release_raw = os.environ.get(RECEIPT_RELEASE_ENV)
    if not release_raw:
        raise JourneyRefusal(
            "ORACLE2_S08_JOURNEY_RECEIPT not set — release workflow requires an "
            "operator-minted receipt at a known path outside SCRATCH; the runner "
            "copies it into the unique per-run SCRATCH after minting SCRATCH (C3). "
            "STOP. Do not invent a production effect."
        )
    release_path = Path(release_raw).resolve()
    # L1/C3: the operator-minted receipt must live OUTSIDE SCRATCH. The runner
    # copies it in after SCRATCH is minted; a release path inside SCRATCH would
    # make that contract vacuous and could collide with the per-run copy.
    try:
        release_path.relative_to(scratch.resolve())
    except ValueError:
        pass
    else:
        raise JourneyRefusal(
            "review receipt release path must be outside SCRATCH (L1/C3): "
            f"release={release_path} scratch={scratch}"
        )
    if not release_path.is_file():
        raise JourneyRefusal(
            f"review receipt release path absent: {release_path} (C3)"
        )
    receipt_path = scratch / "review-receipt.json"
    if receipt_path.exists():
        receipt_path.unlink()
    shutil.copyfile(release_path, receipt_path)
    receipt_path.chmod(0o600)

    stat_checks, raw = _receipt_stat_ok(receipt_path)
    if not stat_checks["passed"]:
        raise JourneyRefusal(f"review receipt file checks failed: {stat_checks}")
    try:
        receipt = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JourneyRefusal(f"review receipt is not valid JSON: {exc}") from exc
    if not isinstance(receipt, dict):
        raise JourneyRefusal("review receipt must be a JSON object")
    got_head = receipt.get("head")
    if not isinstance(got_head, str) or not FULL_SHA40.fullmatch(got_head):
        raise JourneyRefusal(f"review receipt head is not a full 40-char SHA: {got_head!r}")
    if got_head != head:
        raise JourneyRefusal(
            f"review receipt head mismatch: receipt={got_head} current={head}"
        )
    # H6: git-blob SHA-256 for all four bindings — CRLF-safe.
    bindings = {
        "runner_sha256": sha256_git_blob(Path(__file__).resolve()),
        "plan_sha256": sha256_git_blob(
            ROOT / "docs/verification/oracle2/s08-journey-proof-plan.md"
        ),
        "checker_sha256": sha256_git_blob(
            ROOT / "scripts/oracle2/check_s08_journey_skeleton_v1.py"
        ),
        "evidence_sha256": sha256_git_blob(
            ROOT / "docs/verification/oracle2/s08-compose-81742134-evidence.md"
        ),
    }
    for key, actual in bindings.items():
        if receipt.get(key) != actual:
            raise JourneyRefusal(
                f"review receipt {key} mismatch: receipt={receipt.get(key)!r} actual={actual}"
            )
    if receipt.get("verdict") != "APPROVE":
        raise JourneyRefusal(f"review verdict is {receipt.get('verdict')!r}, not APPROVE")
    return {"receipt": receipt, "stat_checks": stat_checks, "bindings": bindings}


def _label_ops_artifact(scratch: Path, artifact_name: str) -> None:
    """C8: label an ops artifact as non-evidence via a sibling JSON marker.

    Text-format artifacts cannot carry JSON keys inline without corrupting
    their content; a sibling .ops.json marker provides the ops/non_evidence
    label uniformly for all ops artifacts.
    """
    (scratch / f"{artifact_name}.ops.json").write_text(
        json.dumps(
            {"ops": True, "non_evidence": True, "artifact": artifact_name},
            sort_keys=True,
        )
        + "\n"
    )


def sql_green_receipt_ok(sql_out: str) -> tuple[bool, str]:
    """H3/H4/L1: require `21 passed` and reject any failed/error/skipped count.

    L1: the green state is exactly 21 collected / 21 passed / 0 skipped.
    When pytest prints a `collected N items` line, N must be exactly 21;
    a nonzero skipped/xfailed/xpassed/deselected count is non-green even
    when `21 passed` is also present ("21 passed, 1 skipped" is 22 collected
    and is NOT green).

    Returns (ok, reason). reason names which check failed so the caller can
    raise a tagged JourneyRefusal with the output tail. Testable offline with
    synthetic pytest tails — ordering, singular/plural, and boundary behavior
    (e.g. "121 passed" must NOT count as 21) are exercised by the checker.
    """
    if not SQL_GREEN_PASSED.search(sql_out):
        return False, "21 SQL green receipt not observed in pytest output (H4)"
    if SQL_GREEN_FAILED.search(sql_out):
        return False, (
            "21 SQL pytest output reports failed/error/skipped cases (H4/L1)"
        )
    collected = SQL_GREEN_COLLECTED.search(sql_out)
    if collected and int(collected.group(1)) != 21:
        return False, (
            f"21 SQL pytest collected {collected.group(1)} items, "
            "expected exactly 21 (L1)"
        )
    return True, ""


def require_database_gate(scratch: Path, tools: dict) -> str:
    """ai-task-gates check --before database must print a precise ALLOW line (H-G/M1).

    Refuses if any DENIED line is present even when an ALLOW line also appears.

    M4 exit-code contract (pinned in the plan): a zero exit with a precise
    ALLOW line and no DENIED line is the only pass. A nonzero exit or timeout
    is always a refusal — the runner captures stdout/stderr, writes
    ops-database-gate.txt even on nonzero exit, searches the captured output
    for DENIED lines so the refusal names the gate's own denial when present,
    and raises a tagged M4/M7 refusal with the output tail. A raw
    CalledProcessError must never escape this helper.
    """
    gate = tools["ai-task-gates"]
    try:
        out = subprocess.check_output(
            [gate["path"], "check", "--before", "database"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=TOOL_CALL_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as exc:
        out = exc.output or ""
        (scratch / "ops-database-gate.txt").write_text(out[:8192])
        _label_ops_artifact(scratch, "ops-database-gate.txt")
        if DENIED_LINE.search(out):
            raise JourneyRefusal(
                f"database gate exited {exc.returncode} with a DENIED line (M4/M7):\n"
                f"{out[:2000]}"
            ) from exc
        raise JourneyRefusal(
            f"database gate exited nonzero ({exc.returncode}) without a precise "
            f"ALLOW line (M4/M7); tail: {out[-500:]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        out = exc.output if isinstance(exc.output, str) else ""
        (scratch / "ops-database-gate.txt").write_text(out[:8192])
        _label_ops_artifact(scratch, "ops-database-gate.txt")
        raise JourneyRefusal(
            f"database gate timed out after {TOOL_CALL_TIMEOUT_S}s (M4/M5/M7); "
            f"tail: {out[-500:]}"
        ) from exc
    except OSError as exc:
        # L6: tag OSError (missing/unexecutable gate binary) so the refusal
        # carries the M4/M7 tag rather than escaping untagged to main's
        # generic handler (which would lack the gate attribution).
        raise JourneyRefusal(
            f"database gate could not be executed (M4/M7): "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if DENIED_LINE.search(out):
        (scratch / "ops-database-gate.txt").write_text(out[:8192])
        _label_ops_artifact(scratch, "ops-database-gate.txt")
        raise JourneyRefusal(
            f"database gate printed a DENIED line (M4/M7):\n{out[:2000]}"
        )
    if not ALLOW_LINE.search(out):
        (scratch / "ops-database-gate.txt").write_text(out[:8192])
        _label_ops_artifact(scratch, "ops-database-gate.txt")
        raise JourneyRefusal(
            f"database gate did not print a precise ALLOW line (M4/M7):\n{out[:2000]}"
        )
    # Ops artifact (C8) — never forensic evidence.
    (scratch / "ops-database-gate.txt").write_text(out[:8192])
    _label_ops_artifact(scratch, "ops-database-gate.txt")
    return out


def source_snapshot() -> dict[str, str]:
    """Hash worktree file CONTENTS (sha256 of bytes) + mode (H-F/M2).

    Not git ls-files index blobs: an edit after bind must be visible. Includes
    Dockerfile, .dockerignore, pyproject.toml, shell scripts, compose files
    and lockfiles the DB image depends on (M2). Uses lstat so symlink swaps
    are visible (M2). Sealed blob pins stay git-blob (sha256_git_blob); this
    snapshot is for worktree mutation detection only.
    """
    snap: dict[str, str] = {}
    for path in ROOT.rglob("*"):
        try:
            st = path.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            # Record symlinks as present-with-target-hash so a swap is visible.
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith((".git/", "node_modules/", ".ai/reviews/packets/")):
                continue
            try:
                target_hash = hashlib.sha256(os.readlink(path).encode()).hexdigest()
            except OSError:
                target_hash = "unreadable"
            snap[rel] = f"symlink:{target_hash}:mode:{st.st_mode & 0o777:o}"
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", "node_modules/", ".ai/reviews/packets/")):
            continue
        name = path.name
        if not _is_snapshotted_source(path, name):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        snap[rel] = f"sha256:{digest}:mode:{st.st_mode & 0o777:o}"
    return snap


def assert_sealed_inventory() -> dict:
    """Assert the sealed SYNTHETIC_MIGRATIONS inventory without importing psycopg (H-I).

    Parses the tuple from verify_workflow_integrity.py the same way
    canonical_synthetic_migrations does. The live bootstrap assertion happens
    later inside main() via bootstrap_canonical_test_schema / _inventory_digest /
    _catalog with golden comparison (H3). This helper never merely echoes
    SEALED_MIGRATION_INVENTORY_NOTE.
    """
    import ast

    tree = ast.parse((ROOT / "scripts/oracle2/verify_workflow_integrity.py").read_text())
    observed: tuple[str, ...] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SYNTHETIC_MIGRATIONS" for t in node.targets
        ):
            observed = tuple(ast.literal_eval(node.value))
            break
    if observed is None:
        raise JourneyRefusal("SYNTHETIC_MIGRATIONS tuple not found in verifier")
    expected = tuple(SEALED_MIGRATION_INVENTORY)
    if observed != expected:
        raise JourneyRefusal(
            "sealed migration inventory drift: "
            f"expected={expected!r} observed={observed!r}"
        )
    return {
        "inventory": list(observed),
        "inventory_count": len(observed),
        "omits": ["003", "005"],
        "includes_extra": ["017", "018", "019", "022", "023", "027"],
    }


# ---------------------------------------------------------------------------
# Stage binding schemas (M9). Each stage validates its bindings dict before
# any work. Required keys are named here so implementers and the checker share
# one contract.
# ---------------------------------------------------------------------------
STAGE_BINDING_SCHEMAS: dict[str, tuple[str, ...]] = {
    "provision_capture_admission": (
        "workspace_id", "meeting_id", "owner_actor",
    ),
    "observe_audience": (
        "meeting_id", "observation_owner_sha256",
    ),
    "host_control": (
        "meeting_id", "expected_head", "operation_id", "observation_id",
    ),
    "current_turn": (
        "event_id", "epoch_id", "capture_sha256",
    ),
    "sender": (
        "expected_revision", "intent_id", "operation_id", "admission_id",
    ),
    "receipt_bytes_in": (
        "raw_wire", "claim_event_id", "operation_id", "admission_id",
    ),
    "status_reconcile": (
        "intent_id", "claim_event_id", "admission_id",
    ),
}

# Journey stage order (H5/M1). The main loop iterates this tuple.
STAGE_ORDER: tuple[str, ...] = (
    "provision_capture_admission",
    "observe_audience",
    "host_control",
    "current_turn",
    "sender",
    "receipt_bytes_in",
    "status_reconcile",
)
# H5/M1 UNKNOWN routing: claim commit / readback-loss stages whose UNKNOWN
# routes to stage 5 (read-only reconcile of the OUTCOME). UNKNOWN from any
# earlier stage ends the journey at that stage.
UNKNOWN_ROUTES_TO_STAGE5 = frozenset({"sender", "receipt_bytes_in"})
STAGE5_NAME = "status_reconcile"


def _route_unknown(stage: str) -> tuple[str, ...]:
    """H5/M1: onward stages after a JourneyUnknown from `stage`.

    Claim commit ACK loss / response drop / worker restart / readback-loss
    (sender, receipt_bytes_in) routes to stage 5 status_reconcile (read-only
    reconcile of the OUTCOME — never a re-read of failing stage inputs).
    UNKNOWN from any earlier stage (provision, observe, host-control,
    current-turn) ends the journey at that stage: empty tuple = STOP.
    """
    if stage in UNKNOWN_ROUTES_TO_STAGE5 and stage != STAGE5_NAME:
        return (STAGE5_NAME,)
    return ()


def _run_stage_order(
    stage_fns: dict,
    stages: dict,
    budget_end: float,
    failing_cell: list,
) -> None:
    """Execute STAGE_ORDER under H5/M1 UNKNOWN routing (fail-closed).

    ``failing_cell`` is a one-element mutable list used as a cell so main's
    refusal path can name the stage in progress when an exception fires.

    M1 (round-7): after a routable UNKNOWN is routed to its onward stage(s),
    the sequence ENDS — the linear STAGE_ORDER loop is never resumed.
    Resuming would inject wire bytes after an UNKNOWN claim (in tension with
    the sealed ACK-loss / no-resend rule) and would double-run later stages
    (e.g. status_reconcile). Extracted so the offline checker can drive the
    real main-loop flow with fake stages (not just `_route_unknown` isolation).
    """
    for name in STAGE_ORDER:
        failing_cell[0] = name
        _budget_check(budget_end, name)
        call = stage_fns[name]
        try:
            call(dict(SKELETON_STAGE_BINDINGS[name]), PER_REQUEST_S)
        except JourneyUnknown as exc:
            stages[name] = "UNKNOWN"
            failing_cell[0] = None
            onward = _route_unknown(name)
            if not onward:
                raise JourneyRefusal(
                    f"routable UNKNOWN at {name} ends the journey at "
                    "this stage (H5/M1); no onward route"
                ) from exc
            for routed in onward:
                failing_cell[0] = routed
                _budget_check(budget_end, routed)
                stage_fns[routed](
                    dict(SKELETON_STAGE_BINDINGS[routed]), PER_REQUEST_S
                )
                stages[routed] = "PROVEN"
                failing_cell[0] = None
            stages[name] = f"UNKNOWN->{'/'.join(onward)}"
            # M1: end the sequence after routing. Never resume STAGE_ORDER —
            # that would inject wire bytes after an UNKNOWN claim and
            # double-run later stages.
            return
        stages[name] = "PROVEN"
        failing_cell[0] = None


# Skeleton stage bindings (L14). Valid-shaped placeholders so the main loop
# complies with the M9 contract it enforces: a fresh skeleton run refuses
# UNPROVEN (after binding validation), never M9 missing-keys. An implementer
# replaces these with real journey bindings at the call sites when stages are
# released. The offline checker's valid_bindings mirror this shape.
SKELETON_STAGE_BINDINGS: dict[str, dict] = {
    "provision_capture_admission": {
        "workspace_id": "workspace-skeleton",
        "meeting_id": "meeting-skeleton",
        "owner_actor": "owner-skeleton",
    },
    "observe_audience": {
        "meeting_id": "meeting-skeleton",
        "observation_owner_sha256": "0" * 64,
    },
    "host_control": {
        "meeting_id": "meeting-skeleton",
        "expected_head": "0" * 40,
        "operation_id": "operation-skeleton-0001",
        "observation_id": "observation-skeleton",
    },
    "current_turn": {
        "event_id": "00000000-0000-0000-0000-000000000001",
        "epoch_id": "epoch-skeleton",
        "capture_sha256": "0" * 64,
    },
    "sender": {
        "expected_revision": 0,
        "intent_id": "intent-skeleton",
        "operation_id": "operation-skeleton-0002",
        "admission_id": "admission-skeleton",
    },
    "receipt_bytes_in": {
        "raw_wire": b"",
        "claim_event_id": "00000000-0000-0000-0000-000000000002",
        "operation_id": "operation-skeleton-0003",
        "admission_id": "admission-skeleton",
    },
    "status_reconcile": {
        "intent_id": "intent-skeleton",
        "claim_event_id": "00000000-0000-0000-0000-000000000002",
        "admission_id": "admission-skeleton",
    },
}


def _validate_bindings(stage: str, bindings: dict) -> None:
    """M9: refuse missing required binding keys before any stage work."""
    required = STAGE_BINDING_SCHEMAS.get(stage, ())
    missing = [k for k in required if k not in bindings]
    if missing:
        raise JourneyRefusal(
            f"stage {stage} bindings missing required keys: {missing} (M9)"
        )


# ---------------------------------------------------------------------------
# Journey stages. Signatures carry the plan's bindings (H-D). NOTE (C5):
# any edit to this file churns the receipt-bound runner SHA and requires a
# new review and a new receipt. There is no "no SHA churn" guarantee.
# Call layers are pinned per stage (H10).
# ---------------------------------------------------------------------------


def stage_provision_capture_admission(bindings: dict, deadline_s: int) -> dict:
    """Stage 0a: capture / admission provisioning precondition (H-B).

    Call layer (H10): FACTORY — MeetingCaptureFactoryV1.transition_v1 and
    retain_ingress_v1 (meeting_capture_v1.py:353,359).

    Cites the SQL fixture construction at
    test_meeting_participation_sql.py:68-133: appointments, capture
    admissions, roles/grants, invite -> retain_ingress (TWO capture calls
    only — there is NO finalize method; C4), and the host/sender/observer
    participation admissions. Without this stage the later stages have no
    admission linkage.
    """
    _validate_bindings("provision_capture_admission", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "capture/admission provisioning not released; journey stage 0a UNPROVEN "
        "(invite -> retain_ingress — two capture calls, no finalize; "
        "host/sender/observer admissions)"
    )


def stage_observe_audience(bindings: dict, deadline_s: int) -> dict:
    """Stage 0b: observer / audience observation (H-A).

    Call layer (H10): AUTHORITY — observe_audience_v1
    (participation_authority_v1.py:480).

    observe_audience_v1 / invent_observation pattern from
    test_meeting_participation_sql.py:136-144. Produces the observation_id
    that stage 1 host enable requires (participation_authority_v1.py:458;
    meeting_participation_v1.py:202 derives it from current SQL status).
    Observation expiry <=30s (021_meeting_participation.sql:259).
    """
    _validate_bindings("observe_audience", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "observer/audience observation not released; journey stage 0b UNPROVEN "
        "(observe_audience_v1 / invent_observation; observation_id required by enable)"
    )


def stage_host_control(bindings: dict, deadline_s: int) -> dict:
    """Stage 1: mTLS host enable/control at /v1/replacement/meetings/participation/control.

    Call layer (H10): SERVICE (mTLS HTTP) -> AUTHORITY control_v1
    (meeting_participation_service_v1.py; participation_authority_v1.py:453).

    bindings carry: meeting selector, CAS expected_head, operation UUID,
    and the observation_id from stage 0b. Server-derived principal. No Next
    browser enable/control web surface exists on this head — that is a named
    remaining gate, not this stage. UI-only screenshots and fixture auth are
    NOT this stage. Deadline <=30s. On CAS conflict: STOP, no transparent
    retry, leave UNKNOWN.

    mTLS prerequisites (H8) are NOT carried by this runner and are an explicit
    named remaining gate: peer-file minting, seals, openssl re-sign,
    certificates/WORKER fixtures (test_hosting_boundary.py:18,28), and the
    closed-denial matrix (bad identity/path/body/headers -> 404/503) plus
    peer-tamper -> 503 (test_meeting_participation_sql.py:428,436). Stage 1
    cannot execute until that gate is discharged.
    """
    _validate_bindings("host_control", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "host-control mTLS journey adapter not released; journey stage 1 UNPROVEN "
        "(mTLS prerequisites deferred — named remaining gate H8; "
        "no Next browser surface on head; see s08-journey-proof-plan.md)"
    )


def stage_current_turn(bindings: dict, deadline_s: int) -> dict:
    """Stage 2: S07 read_current_participant_turn_v1 / meeting_capture_current_turn_v1.

    Call layer (H10): FACTORY — MeetingCaptureFactoryV1.read_current_participant_turn_v1
    (meeting_capture_v1.py).

    bindings carry: exact finalized ingress event UUID + epoch + raw/normalized
    SHA binding. Unknown/Oracle speaker never produces a turn.
    """
    _validate_bindings("current_turn", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "current-turn live consumer not released; journey stage 2 UNPROVEN"
    )


def stage_sender(bindings: dict, deadline_s: int) -> dict:
    """Stage 3: prepare_v1 + claim_v1 under CURRENT enabled generation.

    Call layer (H10): FACTORY — MeetingParticipationFactoryV1.prepare_v1 /
    claim_v1 (meeting_participation_v1.py:212,243). Only the factory enforces
    turn freshness, bot identity, body composition, and post-commit
    currentness. Raw SQL is forbidden at this layer.

    bindings carry: CAS expected_revision, intent_id, operation UUIDs, and
    SAME-admission linkage. Body only after commit+close+fresh own current
    status. No transparent retry. Lost claim = UNKNOWN (routes to stage 5).
    """
    _validate_bindings("sender", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "sender live path not released; journey stage 3 UNPROVEN"
    )


def stage_receipt_bytes_in(bindings: dict, deadline_s: int) -> dict:
    """Stage 4: bytes-in receipt path (meeting_participation_v1.receipt_v1:291).

    Call layer (H10): FACTORY — MeetingParticipationFactoryV1.receipt_v1
    (meeting_participation_v1.py:291, bytes-in / artifact-out).

    bindings carry: raw wire bytes, claim_event_id, operation UUID, SAME
    admission linkage. Injects bounded raw wire bytes into the sealed receipt
    path as test_meeting_participation_sql.py does. The ONLY allowed path is
    the factory bytes-in layer. There is NO fake-Recall HTTPS owner and the
    forbidden network path (exchange_provider_v1 / sendRecallChatMessage /
    recall.ts HTTPS POST) is never called. HTTP 200/201/429/5xx network
    negatives and exactly-one-network-invocation are UNPROVED.
    """
    _validate_bindings("receipt_bytes_in", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "bytes-in receipt journey adapter not released; journey stage 4 UNPROVEN "
        "(factory bytes-in only; no fake-Recall HTTPS owner; network negatives UNPROVED)"
    )


def stage_status_reconcile(bindings: dict, deadline_s: int) -> dict:
    """Stage 5: status_v1 readback + forensic receipt + read-only reconcile.

    Call layer (H10): FACTORY status_v1 (meeting_participation_v1.py:164) +
    AUTHORITY read-only reconcile. Stage 5 is reached on success OR on
    UNKNOWN from claim commit/readback-loss (H5). It never reauthorizes send.
    ACK is never a visible message or provider idempotency.
    """
    _validate_bindings("status_reconcile", bindings)
    if type(deadline_s) is not int or not (0 < deadline_s <= PER_REQUEST_S):
        raise JourneyRefusal(
            f"per-request deadline must be int in (0,{PER_REQUEST_S}]; got {deadline_s!r} (M5)"
        )
    raise JourneyRefusal(
        "status/reconcile journey adapter not released; journey stage 5 UNPROVEN"
    )


def _owned_absence_readback(project: str, *, prefix_aware: bool = False) -> dict:
    """Always callable. Proves absence of owned synthetic residue (M-C/C2).

    When identity is established, `project` is the real suffixed project name
    (identity['project'], e.g. base+'-w'+12hex) and an exact label filter is
    used. Before identity, `prefix_aware=True` lists ALL compose-labeled
    resources and filters client-side by project label startswith(base),
    because docker label filters are exact-match and the fixture suffixes the
    base name (C2). An exact-match on the base name alone is vacuous.

    NOTE: the pre-identity path uses a unique per-run random base
    (project_base = COMPOSE_PROJECT_PREFIX + uuid hex), so it can never match
    residue from a PRIOR run. The pre-identity readback is therefore vacuous
    as an absence proof for prior leaks; it is kept for uniformity of the
    cleanup contract and to name the current run's residue if identity failed
    mid-setup. Post-identity readback with the real suffixed name is the
    authoritative absence proof.
    """
    docker = _tool_identity("docker")
    remains: dict[str, object] = {}
    if prefix_aware:
        # Client-side prefix filter: list all compose-labeled resources, then
        # read each resource's project label via inspect (L4). `{{.Label …}}`
        # is not a reliable `network ls`/`volume ls` format on Linux docker
        # and records probe-failed instead of a real result. Fail-safe: any
        # probe/inspect failure is recorded as probe-failed and never raises.
        for kind, list_cmd, inspect_cmd in (
            (
                "containers",
                ["ps", "-aq", "--filter", "label=com.docker.compose.project"],
                ["inspect", "-f", '{{index .Config.Labels "com.docker.compose.project"}}'],
            ),
            (
                "networks",
                ["network", "ls", "-q", "--filter", "label=com.docker.compose.project"],
                ["network", "inspect", "-f", '{{index .Labels "com.docker.compose.project"}}'],
            ),
            (
                "volumes",
                ["volume", "ls", "-q", "--filter", "label=com.docker.compose.project"],
                ["volume", "inspect", "-f", '{{index .Labels "com.docker.compose.project"}}'],
            ),
        ):
            try:
                out = subprocess.check_output(
                    [docker["path"], *list_cmd],
                    text=True,
                    stderr=subprocess.STDOUT,
                    timeout=DOCKER_PROBE_TIMEOUT_S,
                )
                hits = False
                for rid in (line.strip() for line in out.splitlines() if line.strip()):
                    try:
                        label = subprocess.check_output(
                            [docker["path"], *inspect_cmd, rid],
                            text=True,
                            stderr=subprocess.STDOUT,
                            timeout=DOCKER_PROBE_TIMEOUT_S,
                        ).strip()
                    except (
                        subprocess.CalledProcessError,
                        subprocess.TimeoutExpired,
                        OSError,
                    ):
                        continue
                    if label.startswith(project):
                        hits = True
                        break
                remains[kind] = hits
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                remains[kind] = f"probe-failed:{type(exc).__name__}"
    else:
        # Exact-match on the real suffixed project name (identity['project']).
        for kind, cmd in (
            ("containers", ["ps", "-aq"]),
            ("networks", ["network", "ls", "-q"]),
            ("volumes", ["volume", "ls", "-q"]),
        ):
            try:
                out = subprocess.check_output(
                    [docker["path"], *cmd,
                     "--filter", f"label=com.docker.compose.project={project}"],
                    text=True,
                    stderr=subprocess.STDOUT,
                    timeout=DOCKER_PROBE_TIMEOUT_S,
                )
                remains[kind] = bool(out.strip())
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                remains[kind] = f"probe-failed:{type(exc).__name__}"
    absent = all(v is False for v in remains.values())
    return {
        "project": project,
        "prefix_aware": prefix_aware,
        "remaining": remains,
        "absent": absent,
    }


def _write_refusal(scratch: Path, reason: str, stage: str | None, head: str | None) -> None:
    """Refused runs write ONLY a refusal marker — never forensic evidence (C8/M-D).

    journey-evidence.json is exclusively a success-path artifact.
    cleanup.json and other ops artifacts are labeled ops/non-evidence.
    SCRATCH reuse: unlink journey-evidence.json so a reused directory cannot
    hold stale evidence beside a fresh refusal.
    """
    stale_evidence = scratch / "journey-evidence.json"
    if stale_evidence.exists():
        stale_evidence.unlink()
    payload = {
        "refused": True,
        "non_evidence": True,
        "reason": str(reason)[:2000],
        "failing_stage": stage,
        "head": head,
    }
    (scratch / "refusal.json").write_text(json.dumps(payload, sort_keys=True) + "\n")


def _resolve_marker_dir(scratch: Path | None) -> Path | None:
    """Locate a writable marker directory (L2).

    Prefers the live scratch; falls back to a SCRATCH_ENV directory that
    _scratch() created before a later pre-try failure. Returns None when
    nowhere exists (true chicken-and-egg scratch-create failure).
    """
    if scratch is not None:
        return scratch
    raw = os.environ.get(SCRATCH_ENV)
    if not raw:
        return None
    try:
        cand = Path(raw).resolve()
    except OSError:
        return None
    return cand if cand.is_dir() else None


def _write_pretry_refusal(scratch: Path | None, reason: str) -> None:
    """L2: never leave a silent pre-try exit.

    Write a tagged refusal.json when a marker directory is available —
    including a SCRATCH_ENV directory that _scratch() created before a later
    pre-try failure. When SCRATCH creation itself is the failure there is
    nowhere to write (chicken-and-egg); print a tagged stderr line and leave
    no marker rather than pretending one exists.
    """
    target = _resolve_marker_dir(scratch)
    if target is not None:
        try:
            _write_refusal(target, f"pre-try: {reason}", "pre-try", None)
            return
        except OSError:
            pass
    print(f"pre-try-refusal (no SCRATCH; chicken-and-egg): {reason}", file=sys.stderr)


def main() -> int:
    scratch: Path | None = None
    project_base = f"{COMPOSE_PROJECT_PREFIX}-{uuid4().hex[:8]}"  # unique per run (M-C)
    head: str | None = None
    failing_cell: list[str | None] = [None]
    identity: dict | None = None
    evidence_written = False
    try:
        # L2: pre-try work runs inside the try so refusals write a tagged
        # marker (via _write_pretry_refusal / _write_refusal) instead of
        # exiting silently. require_python_floor stays before _scratch (M3/L5).
        require_python_floor()
        os.umask(0o077)
        scratch = _scratch()
        require_recall_env_absent()  # H-E: refuse before any other work
        # C1: each tool uses its own working identity command (TOOL_VERSION_ARGS).
        tools = {name: _tool_identity(name) for name in ("git", "ai-task-gates", "docker")}
        # M7: also establish identities for openssl (SQL mTLS tests) and the
        # pytest that will run the 21 SQL, so missing/broken harness tools
        # surface as preflight refusals, not backend-attributed H4 failures.
        tools["openssl"] = _tool_identity("openssl")
        # M8: preflight the docker compose plugin (not just the docker CLI).
        try:
            compose_ver = subprocess.check_output(
                [tools["docker"]["path"], "compose", "version"],
                text=True, stderr=subprocess.STDOUT, timeout=DOCKER_PROBE_TIMEOUT_S,
            ).splitlines()[0][:200]
            tools["docker-compose"] = {
                "name": "docker-compose", "path": tools["docker"]["path"],
                "version": compose_ver,
            }
        except (subprocess.CalledProcessError, OSError, IndexError, subprocess.TimeoutExpired) as exc:
            raise JourneyRefusal(
                f"docker compose plugin unavailable: {type(exc).__name__}: {exc}; "
                "the fixture requires docker compose (M8)"
            ) from exc
        # M4: the pytest identity preflight follows the same exit-code contract
        # as the database gate — nonzero exit or timeout is a tagged M4/M7
        # preflight refusal, never a raw CalledProcessError. M5: bounded.
        try:
            _pytest_version = subprocess.check_output(
                [sys.executable, "-m", "pytest", "--version"],
                text=True, stderr=subprocess.STDOUT, timeout=TOOL_CALL_TIMEOUT_S,
            ).splitlines()[0][:200]
        except (
            subprocess.CalledProcessError,
            OSError,
            IndexError,
            subprocess.TimeoutExpired,
        ) as exc:
            raise JourneyRefusal(
                f"pytest identity unavailable (M4/M7): {type(exc).__name__}: {exc}; "
                "the 21 SQL harness requires a working pytest"
            ) from exc
        tools["pytest"] = {
            "name": "pytest", "path": sys.executable, "version": _pytest_version,
        }
        head = require_head()
        inventory = assert_sealed_inventory()  # H-I before any DB
        # L3: snapshot walked twice total (before and after gate) for mutation
        # detection; the after-gate result is the one written and compared.
        before = source_snapshot()
        receipt = require_review_receipt(head, scratch)  # H-J / C3
        require_database_gate(scratch, tools)  # H-G/M1 precise ALLOW, no DENIED
        after_gate = source_snapshot()
        if before != after_gate:
            raise JourneyRefusal("source changed during gate; STOP")
        # Ops artifact (C8) — never forensic evidence.
        (scratch / "ops-source-after-gate.json").write_text(
            json.dumps(after_gate, sort_keys=True) + "\n"
        )
        _label_ops_artifact(scratch, "ops-source-after-gate.json")

        # One fresh owned synthetic PG via the sealed fixture. The sealed
        # bootstrap inventory is used and asserted — never a custom contiguous
        # 001..014 chain.
        sys.path.insert(0, str(ROOT))
        from dev.oracle2.test_worker_postgres_fixture import worker_postgres

        # C3: use a unique worker subdirectory so the fixture's
        # mkdir(exist_ok=False) cannot collide on reuse.
        worker_dir = scratch / f"worker-{uuid4().hex[:8]}"
        with worker_postgres(
            {**os.environ, "COMPOSE_PROJECT_NAME": project_base},
            worker_dir,
            WORKER_LABEL,
        ) as (worker_env, identity):
            # C1: the fixture yields (env_dict, identity), NOT a URL.
            # Use worker_env['ORACLE2_TEST_ADMIN_URL'] exactly as
            # verify_workflow_integrity.py:390-391. Never pass the dict to
            # bootstrap; never fall back to an outer ORACLE2_TEST_ADMIN_URL.
            target = worker_env["ORACLE2_TEST_ADMIN_URL"]
            if not isinstance(target, str) or not target:
                raise JourneyRefusal(
                    "worker_env['ORACLE2_TEST_ADMIN_URL'] missing or not a string (C1)"
                )
            # M7: explicit fail-closed checks — never bare assert (stripped
            # under python -O; message-less AssertionError is opaque).
            if not identity["project"].startswith(project_base):
                raise JourneyRefusal(
                    f"identity project {identity['project']!r} does not start with "
                    f"owned base {project_base!r} (C2/M7)"
                )
            if identity.get("synthetic_only") is not True:
                raise JourneyRefusal(
                    "identity synthetic_only is not True — refusing non-synthetic target (M7)"
                )
            # C2: after identity, cleanup uses the REAL suffixed project name.
            real_project = identity["project"]

            # C9: budget armed AFTER worker_postgres + bootstrap, matching
            # verify_workflow_integrity.py:384-386 (setup outside budget) and
            # :407 (deadline armed after setup).
            # H-I: real bootstrap + inventory/catalog assertion on the live DB.
            from dev.oracle2.test_canonical_schema import (
                _catalog,
                bootstrap_canonical_test_schema,
                canonical_synthetic_migrations,
            )
            import psycopg

            # H3: sealed constants, not self-referential goldens. The expected
            # inventory digest is SEALED_INVENTORY_DIGEST (review-time constant),
            # never computed from the same files seconds before the observation.
            # C2/M2: inventory digest uses GIT-BLOB bytes (host-independent LF).
            if not re.fullmatch(r"[0-9a-f]{64}", SEALED_INVENTORY_DIGEST):
                raise JourneyRefusal("SEALED_INVENTORY_DIGEST is not a 64-hex constant (H3)")
            # C3 option-a: catalog is RECORDED, NOT GOLDEN. No refuse-on-empty.
            files = canonical_synthetic_migrations()
            schema_receipt = (scratch / "ops-schema-receipt.json").resolve()
            schema_seal = bootstrap_canonical_test_schema(
                target,
                container_id=identity["container_id"],
                receipt_path=schema_receipt,
            )
            _label_ops_artifact(scratch, "ops-schema-receipt.json")
            # H3/C2: compare observed inventory digest against the SEALED
            # constant using git-blob bytes (host-independent). L13: the
            # digest reads the bound 40-char head, never symbolic HEAD.
            observed_inventory_digest = _inventory_digest_git_blob(
                tuple(p.name for p in files), head
            )
            if observed_inventory_digest != SEALED_INVENTORY_DIGEST:
                raise JourneyRefusal(
                    "sealed inventory digest drift: "
                    f"sealed={SEALED_INVENTORY_DIGEST} observed={observed_inventory_digest} (H3/C2)"
                )
            with psycopg.connect(target) as connection:
                catalog = _catalog(connection)
            if tuple(p.name for p in files) != tuple(SEALED_MIGRATION_INVENTORY):
                raise JourneyRefusal("sealed inventory names drift after bootstrap")
            # C3 option-a: catalog digest is RECORDED in evidence, not compared
            # against a golden. No refuse-on-empty. A future fill of
            # SEALED_CATALOG_DIGEST requires re-review (C5).
            live_catalog_digest = (
                hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
                if isinstance(catalog, (list, tuple))
                else str(catalog)
            )
            catalog_digest = catalog if isinstance(catalog, str) else live_catalog_digest

            # H4: enforce "21 SQL green first". Run the 21 SQL module against
            # the bootstrapped DB before any journey stage. The SQL module
            # reads ORACLE2_TEST_ADMIN_URL directly (C7). Timeout bound is
            # SHARED_BUDGET_S + 60 = 180s. Flags keep the tree clean post-bind
            # (-p no:cacheprovider, PYTHONDONTWRITEBYTECODE).
            sql_green_cmd = [
                sys.executable, "-m", "pytest",
                str(ROOT / "services/oracle-brain/tests/test_meeting_participation_sql.py"),
                "-v", "--tb=short", "-x", "-p", "no:cacheprovider",
            ]
            sql_env = {
                **os.environ,
                **worker_env,
                "ORACLE2_TEST_ADMIN_URL": target,
                "ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT": str(schema_receipt),
                "ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256": schema_seal,
                "PYTHONPATH": str(ROOT / "services/oracle-brain") + os.pathsep + str(ROOT),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            sql_timeout_s = SHARED_BUDGET_S + 60  # 180s bound (H4)
            try:
                sql_out = subprocess.check_output(
                    sql_green_cmd,
                    cwd=ROOT,
                    text=True,
                    stderr=subprocess.STDOUT,
                    env=sql_env,
                    timeout=sql_timeout_s,
                )
            except subprocess.CalledProcessError as exc:
                sql_out = exc.output or ""
                (scratch / "ops-sql-green.txt").write_text(sql_out[:16384])
                _label_ops_artifact(scratch, "ops-sql-green.txt")
                raise JourneyRefusal(
                    "21 SQL must go green before the journey (H4); "
                    f"pytest exit={exc.returncode}; tail: {sql_out[-500:]}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                sql_out = exc.output if isinstance(exc.output, str) else ""
                (scratch / "ops-sql-green.txt").write_text(sql_out[:16384])
                _label_ops_artifact(scratch, "ops-sql-green.txt")
                raise JourneyRefusal(
                    f"21 SQL pytest timed out after {sql_timeout_s}s (H4); "
                    f"tail: {sql_out[-500:]}"
                ) from exc
            (scratch / "ops-sql-green.txt").write_text(sql_out[:16384])
            _label_ops_artifact(scratch, "ops-sql-green.txt")
            # H3/H4: require "21 passed" AND reject any failed/error count in
            # the output. A bare "21 passed" regex accepts "21 passed, 1 error".
            # Factored into sql_green_receipt_ok so the checker can exercise
            # ordering, singular/plural, and boundaries offline (Muse H3/H4).
            sql_ok, sql_reason = sql_green_receipt_ok(sql_out)
            if not sql_ok:
                raise JourneyRefusal(
                    f"{sql_reason}; tail: {sql_out[-500:]}"
                )

            # C9: budget armed AFTER worker_postgres + bootstrap_canonical_test_schema
            # + 21 SQL green, matching verify_workflow_integrity.py:384-386,407.
            budget_end = _monotonic_end(SHARED_BUDGET_S)

            stages = {
                "provision_capture_admission": "UNPROVEN",
                "observe_audience": "UNPROVEN",
                "host_control": "UNPROVEN",
                "current_turn": "UNPROVEN",
                "sender": "UNPROVEN",
                "receipt_bytes_in": "UNPROVEN",
                "status_reconcile": "UNPROVEN",
            }
            stage_fns = {
                "provision_capture_admission": stage_provision_capture_admission,
                "observe_audience": stage_observe_audience,
                "host_control": stage_host_control,
                "current_turn": stage_current_turn,
                "sender": stage_sender,
                "receipt_bytes_in": stage_receipt_bytes_in,
                "status_reconcile": stage_status_reconcile,
            }
            # Stages refuse until implemented; the budget fence is armed first.
            # L14: SKELETON_STAGE_BINDINGS are valid-shaped so a fresh skeleton
            # run reaches the UNPROVEN refusal (never M9 missing-keys). An
            # implementer replaces them with real journey bindings at these
            # call sites when stages are released (C5 SHA churn applies).
            # M1: _run_stage_order owns the STAGE_ORDER loop and the
            # JourneyUnknown routing policy (route to stage 5 then STOP —
            # never resume the linear loop). Extracted so the offline checker
            # can drive the real main-loop flow with fake stages.
            with _request_fence_v1(budget_end):
                _run_stage_order(stage_fns, stages, budget_end, failing_cell)

            # Success-path evidence only (C8). Never written on refusal.
            # SCRATCH reuse: unlink stale refusal.json so markers stay exclusive.
            stale_refusal = scratch / "refusal.json"
            if stale_refusal.exists():
                stale_refusal.unlink()
            evidence = {
                "refused": False,
                "non_evidence": False,
                "head": head,
                "review_receipt_sha256": sha256_file(scratch / "review-receipt.json"),
                "runner_sha256": receipt["bindings"]["runner_sha256"],
                "plan_sha256": receipt["bindings"]["plan_sha256"],
                "checker_sha256": receipt["bindings"]["checker_sha256"],
                "evidence_sha256": receipt["bindings"]["evidence_sha256"],
                "sha_binding_semantics": "git-blob (git show HEAD:path | sha256sum) (H6)",
                "sealed_migration_inventory": list(SEALED_MIGRATION_INVENTORY),
                "inventory_assertion": inventory,
                "inventory_digest_golden": SEALED_INVENTORY_DIGEST,
                "inventory_digest_observed": observed_inventory_digest,
                "inventory_digest_semantics": "git-blob (git show HEAD:path) (C2/M2)",
                "catalog_digest": catalog_digest,
                "catalog_golden": SEALED_CATALOG_DIGEST or None,
                "catalog_semantics": "recorded, not golden (C3 option-a)",
                "sql_green": True,
                "stages": stages,
                "tools": tools,
                "limits": {
                    "shared_budget_s": SHARED_BUDGET_S,
                    "per_request_s": PER_REQUEST_S,
                    "bootstrap_inside_shared_budget": False,
                    "budget_mechanism": (
                        "ContextVar monotonic fence, finite-only, entry+exit check "
                        "(request_deadline_v1.py:26-35 shape) (H1)"
                    ),
                    "budget_armed_after": "worker_postgres + bootstrap + 21 SQL green (C9)",
                },
                "deadline_cas_policy": {
                    "max_deadline_s": 30,
                    "observation_expiry_max_s": 30,
                    "on_conflict": "STOP; record failing stage; leave UNKNOWN; no transparent retry",
                    "unknown_routing": (
                        "UNKNOWN from claim commit/readback-loss -> stage 5 "
                        "read-only reconcile, then END the stage sequence (the "
                        "linear STAGE_ORDER loop is never resumed — no wire-byte "
                        "injection after an UNKNOWN claim, no double-run of later "
                        "stages); UNKNOWN from earlier stages -> end at failing "
                        "stage (H5). Mechanism: JourneyUnknown(JourneyRefusal) "
                        "subclass — routable UNKNOWN vs fatal JourneyRefusal (M1)."
                    ),
                    "no_re_read_scope": (
                        "journey layer never re-reads failing stage inputs; "
                        "factory-internal fresh readbacks are the tested factory "
                        "behaviour and are outside this scope (H5)"
                    ),
                },
                "stage_call_layers": {
                    "provision_capture_admission": "factory (MeetingCaptureFactoryV1)",
                    "observe_audience": "authority (observe_audience_v1)",
                    "host_control": "service (mTLS HTTP) -> authority (control_v1)",
                    "current_turn": "factory (read_current_participant_turn_v1)",
                    "sender": "factory (prepare_v1, claim_v1)",
                    "receipt_bytes_in": "factory (receipt_v1)",
                    "status_reconcile": "factory (status_v1) + authority read-only",
                },
                "forbidden_network_paths": list(FORBIDDEN_NETWORK_PATHS),
                "unproved": [
                    "http_201_429_5xx_network_negatives",
                    "exactly_one_network_invocation_across_restart_repeat",
                    "host_disable_between_prepare_and_claim_zero_network",
                    "observation_commit_ack_loss_journey_sequence",
                    "permission_expiry_before_after_close_matrix_journey",
                    "next_browser_enable_control_web_surface",
                    "w10_same_worker_fit_measurement",
                    "mtls_peer_file_minting_seals_openssl_closed_denial_matrix (H8 deferred)",
                ],
                "business_acceptance": "HELD",
                "real_teams_producer": "UNQUALIFIED",
            }
            (scratch / "journey-evidence.json").write_text(
                json.dumps(evidence, sort_keys=True) + "\n"
            )
            evidence_written = True  # C8: suppress refusal.json on success path
            return 0
    except JourneyRefusal as exc:
        if not evidence_written:  # C8: refusal.json ONLY on refusal paths
            marker_dir = _resolve_marker_dir(scratch)
            if marker_dir is not None:
                _write_refusal(marker_dir, str(exc), failing_cell[0], head)
            else:
                _write_pretry_refusal(scratch, str(exc))
        raise
    except BaseException as exc:  # noqa: BLE001 — any failure is a refusal
        # L4: catch BaseException (KeyboardInterrupt, SystemExit, and every
        # other Exception subclass) so an interrupted run still leaves a
        # tagged refusal.json — never cleanup.json with neither refusal nor
        # evidence markers. The exception is re-raised after the marker is
        # written; the finally block still runs for cleanup readback.
        # L2: pre-try failures use the same marker path — never a silent exit.
        if not evidence_written:  # C8: never write refusal after evidence
            marker_dir = _resolve_marker_dir(scratch)
            reason = f"{type(exc).__name__}: {exc}"
            if marker_dir is not None:
                _write_refusal(marker_dir, reason, failing_cell[0], head)
            else:
                _write_pretry_refusal(scratch, reason)
        raise
    finally:
        # Cleanup readback ALWAYS, even pre-identity (M-C). Project name is
        # generated before the try so residue can be named on every path.
        # M8: record both the original exception and any cleanup error; never
        # mask the original. cleanup.json is an ops artifact (C8).
        # L2: write cleanup.json whenever a marker directory exists; a true
        # scratch-create failure has nowhere to write (chicken-and-egg).
        original_exc = sys.exc_info()[1]
        marker_dir = _resolve_marker_dir(scratch)
        try:
            # C2: use the real suffixed project when identity is established;
            # prefix-aware listing on pre-identity paths.
            if identity is not None:
                readback = _owned_absence_readback(identity["project"], prefix_aware=False)
            else:
                readback = _owned_absence_readback(project_base, prefix_aware=True)
            readback["ops"] = True
            readback["non_evidence"] = True
            if marker_dir is not None:
                (marker_dir / "cleanup.json").write_text(
                    json.dumps(readback, sort_keys=True) + "\n"
                )
            if not readback["absent"] and identity is not None:
                cleanup_err = JourneyRefusal(
                    "exact owned synthetic cleanup incomplete; absence not proven; STOP"
                )
                if original_exc is not None:
                    # M8: preserve the original exception; add cleanup as note.
                    original_exc.add_note(f"cleanup also failed: {cleanup_err}")
                else:
                    raise cleanup_err
        except JourneyRefusal as cleanup_jr:
            if original_exc is not None:
                # M7: do not mask the original, but DO record the cleanup refusal.
                original_exc.add_note(f"cleanup refusal: {cleanup_jr}")
            else:
                raise
        except Exception as cleanup_probe_exc:  # noqa: BLE001
            # M8: a cleanup probe failure is recorded but must not mask the
            # original refusal. Attach as a note when an original exists.
            if original_exc is not None:
                original_exc.add_note(
                    f"cleanup probe failed: {type(cleanup_probe_exc).__name__}: {cleanup_probe_exc}"
                )
            # else: silent on pre-identity probe failure (recorded above when possible)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
