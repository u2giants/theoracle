"""S11 Next/multiemployee one-shot proof runner (Linux-only, edge-dev3).

Sealed into PR #201 so every fail-closed claim is inspectable:
  - exact-head pin          : receipt.head == git rev-parse HEAD of the execution worktree
  - clean-tree check        : git status --porcelain must be empty (uncommitted edits refuse)
  - receipt fields          : head, verdict=APPROVE, reviewer, reviewed_at
  - STOP exit 2             : every pre/post-gate failure prints a reason and exits 2
  - owned cleanup           : compose-project absence proof (containers/networks/volumes)
  - source-before/after     : sha256 over all git-tracked files (content+mode) is equal after the run

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

Receipt honesty (Muse Medium M3):
  The review receipt at /tmp is an operator-minted, unsigned JSON file. It is a
  procedural gate, not an integrity-bound signature. Plan/note/JSON/status/
  measure-script content digests are recorded in result.json so a reviewer can
  verify the sealed set matches the reviewed head.

Platform: Linux only (/proc probing in the sealed drivers). Invent fixtures only.
No production, no company originals, no paid providers, no real employees.

Live-lock contract (path-scoped; post-PR201 false-positive):
  A process is a live apps/web/.next/dev lock holder ONLY when its cwd, an open
  fd, or its argv actually references THIS worktree's apps/web or .next/dev
  path. Host-level node / chromium / playwright / claude name-or-args matches
  never count (Playwright MCP, chrome_crashpad, claude-headroom and disclaimer
  wrappers previously false-STOPped the pre-check). Directory existence alone is
  never a lock — Next leaves apps/web/.next/dev behind after clean exit. Real
  holders (cwd under the owned apps/web, or .next/dev fds) still STOP fail-closed.
"""
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import re
import signal
import subprocess
import sys

# Authoring parent of this seal. The reviewed seal SHA is bound by the Muse
# receipt and by docs/verification/oracle2/pr201-next-status.md; the pin below
# is the checked-out execution HEAD vs receipt.head.
AUTHORING_PARENT = "ac1a848edaa3570070abaeef5627b8d33cfd3685"

# Per-invocation wall clock. test-setup-only; NOT the W10 120s budget.
ONE_SHOT_WALL_S = 300

# M4: whole-worktree content+mode hash replaces the narrow path list.  The
# documented sealed set below is retained for human readers; the actual
# equality gate covers every git-tracked file so mid-run mutation of any
# executed product source (workflows, hosting, SQL, shared, proxy) is detected.
SEALED_SOURCE_PATHS = (
    # Sealed companion artifacts (Muse-readable at this head)
    "docs/verification/oracle2/s11-actual-next-proof-plan.md",
    "docs/verification/oracle2/s11-next-dist-lock-note.md",
    "docs/verification/oracle2/s11-setup-batch-measurement-01.json",
    "docs/verification/oracle2/pr201-next-status.md",
    "scripts/oracle2/measure-s11-setup-batch-01.py",
    # Test / driver sources
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
    "services/oracle-brain/tests/test_s11_live_lock_path_scope.py",
    # Product source the proof executes (M4)
    "dev/oracle2/compose.yaml",
)

root = Path(__file__).resolve().parents[2]
_ops = Path(os.environ.get("ORACLE2_S11_OPS_ROOT", "/tmp/oracle-parent24-wy02uT"))
scratch = _ops / "s11-next-multiemployee-proof-01"
receipt_path = _ops / "s11-next-multiemployee-review-receipt.json"

# H4: broader process tokens for the leak-detection backstop scan ONLY.
# These tokens must NEVER decide live_lock_present: host Playwright MCP,
# chrome_crashpad, claude-headroom, disclaimer wrappers etc. match them and
# are not holders of this worktree's apps/web/.next/dev. Lock claims use the
# path-scoped predicate below.
PROCESS_TOKENS = (
    "next dev",
    "next-server",
    "turbopack",
    "playwright",
    "chromium",
    "tsx",
    "headless_shell",
    "chrome",
    "workspace-next-recipients-proof",
    "recommendation-next-auth-proof",
    "invented-auth-service",
)


# ---------------------------------------------------------------------------
# Path-scoped live-lock detection (PR201 one-shot false-positive fix)
# ---------------------------------------------------------------------------
def _norm_text(path: Path) -> str:
    try:
        return str(path.resolve()).replace("\\", "/")
    except OSError:
        return str(path).replace("\\", "/")


def _norm_sep(text: str) -> str:
    return text.replace("\\", "/")


def _is_path_word_char(ch: str) -> bool:
    return ch.isalnum() or ch in "-_.+"


def _path_string_refs(text: str, root_s: str) -> bool:
    """True when text names root_s or a path under it (boundary-aware)."""
    if not text or not root_s:
        return False
    if text == root_s or text.startswith(root_s + "/"):
        return True
    idx = text.find(root_s)
    while idx != -1:
        end = idx + len(root_s)
        before_ok = idx == 0 or not _is_path_word_char(text[idx - 1])
        after_ok = end == len(text) or text[end] == "/" or not _is_path_word_char(text[end])
        if before_ok and after_ok:
            return True
        idx = text.find(root_s, idx + 1)
    return False


def _rel_segment_refs(text: str, segment: str) -> bool:
    """True when text carries the relative path segment with path boundaries."""
    if not text or not segment:
        return False
    idx = text.find(segment)
    while idx != -1:
        end = idx + len(segment)
        before_ok = idx == 0 or not _is_path_word_char(text[idx - 1])
        after_ok = end == len(text) or text[end] == "/" or not _is_path_word_char(text[end])
        if before_ok and after_ok:
            return True
        idx = text.find(segment, idx + 1)
    return False


def process_facts_reference_owned(
    *,
    cwd: str | None,
    argv: list[str],
    fd_targets: list[str],
    base: Path,
) -> bool:
    """Path-scoped lock-holder predicate.

    A process counts as a live holder only when it actually binds the owned
    worktree's apps/web (cwd under it, fd under it, argv naming it). Host-level
    node/chromium/playwright/claude processes with no owned-path reference are
    NOT holders.
    """
    base_s = _norm_text(base)
    apps_web_s = _norm_text(base / "apps/web")
    next_dev_s = _norm_text(base / "apps/web/.next/dev")

    under_base = False
    if cwd:
        cwd_s = _norm_sep(cwd).rstrip("/")
        if cwd_s == apps_web_s or cwd_s.startswith(apps_web_s + "/"):
            return True
        if cwd_s == next_dev_s or cwd_s.startswith(next_dev_s + "/"):
            return True
        under_base = cwd_s == base_s or cwd_s.startswith(base_s + "/")

    for target in fd_targets:
        if not target:
            continue
        t = _norm_sep(target).split(" (deleted)")[0].rstrip("/")
        if t == apps_web_s or t.startswith(apps_web_s + "/"):
            return True
        if t == next_dev_s or t.startswith(next_dev_s + "/"):
            return True
        if _path_string_refs(t, apps_web_s) or _path_string_refs(t, next_dev_s):
            return True

    for arg in argv:
        if not arg:
            continue
        arg_s = _norm_sep(arg)
        if _path_string_refs(arg_s, apps_web_s) or _path_string_refs(arg_s, next_dev_s):
            return True
        # Relative argv (cwd under the worktree root) can still name the tree.
        if under_base and (
            _rel_segment_refs(arg_s, "apps/web/.next/dev")
            or _rel_segment_refs(arg_s, "apps/web")
        ):
            return True
    return False


def scan_owned_lock_holders(base: Path) -> dict:
    """Walk /proc for processes that path-reference the owned apps/web tree.

    holders lists ONLY path-scoped matches. A failed /proc walk is reported via
    scan_failed (never smuggled into holders as a pseudo-process).
    """
    holders: list[str] = []
    scanned = 0
    unreadable = 0
    try:
        pid_dirs = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except OSError as e:
        return {
            "holders": [],
            "scanned": 0,
            "unreadable": 0,
            "scan_failed": True,
            "scan_error": str(e),
            "matching_rule": (
                "path-scoped: cwd/fd/argv reference to this worktree's apps/web or "
                ".next/dev; host name/token scans never count as live_lock"
            ),
        }
    for pid_dir in pid_dirs:
        scanned += 1
        argv: list[str] = []
        cwd: str | None = None
        fd_targets: list[str] = []
        try:
            raw = (pid_dir / "cmdline").read_bytes()
            argv = [x.decode("utf-8", "replace") for x in raw.split(b"\0") if x]
        except OSError:
            unreadable += 1
        try:
            cwd = os.readlink(pid_dir / "cwd")
        except OSError:
            pass
        try:
            for fd in (pid_dir / "fd").iterdir():
                try:
                    fd_targets.append(os.readlink(fd))
                except OSError:
                    continue
        except OSError:
            pass
        if process_facts_reference_owned(
            cwd=cwd, argv=argv, fd_targets=fd_targets, base=base
        ):
            preview_argv = argv[:6]
            holders.append(f"{pid_dir.name} cwd={cwd!r} argv={preview_argv!r}")
    return {
        "holders": holders,
        "scanned": scanned,
        "unreadable": unreadable,
        "scan_failed": False,
        "matching_rule": (
            "path-scoped: cwd/fd/argv reference to this worktree's apps/web or "
            ".next/dev; host name/token scans never count as live_lock"
        ),
    }


def stop(msg: str) -> None:
    """M1/M6: every pre/post-gate failure prints a reason and exits 2 (STOP)."""
    print(f"STOP: {msg}")
    sys.exit(2)


def require_linux_proc() -> None:
    """Linux-only: sealed drivers probe /proc (FileNotFoundError off-Linux)."""
    if not Path("/proc").is_dir():
        stop("Linux-only runner (/proc required); use edge-dev3")


# ---------------------------------------------------------------------------
# H5: executable resource preflight (replaces the dead RESOURCE_PRECHECK dict)
# ---------------------------------------------------------------------------
def preflight_resources(base: Path) -> dict:
    """Check hard runner dependencies before any DB/Next work. Exit 2 on failure."""
    checks = {}

    # DNS: localhost.localdomain must resolve
    import socket as _socket

    try:
        _socket.getaddrinfo("localhost.localdomain", None)
        checks["dns_localhost_localdomain"] = "ok"
    except OSError as e:
        stop(f"DNS: localhost.localdomain does not resolve ({e})")

    # ::1 loopback must be available
    try:
        s = _socket.socket(_socket.AF_INET6, _socket.SOCK_STREAM)
        s.bind(("::1", 0))
        s.close()
        checks["ipv6_loopback"] = "ok"
    except OSError as e:
        stop(f"IPv6 loopback ::1 not available ({e})")

    # Binary dependencies on PATH
    for name, cmd in [
        ("openssl", ["openssl", "version"]),
        ("docker", ["docker", "--version"]),
        ("git", ["git", "--version"]),
        ("ps", ["ps", "--version"]),
    ]:
        try:
            subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10)
            checks[name] = "ok"
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            stop(f"{name} not available on PATH ({e})")

    # pnpm / tsx (TS proof drivers)
    for name in ("pnpm", "tsx"):
        try:
            subprocess.check_output(["which", name], stderr=subprocess.DEVNULL, timeout=10)
            checks[name] = "ok"
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            stop(f"{name} not found on PATH ({e})")

    # Chromium (browser proof)
    chromium_found = False
    for candidate in ("chromium", "chromium-browser", "google-chrome", "headless_shell"):
        try:
            subprocess.check_output(["which", candidate], stderr=subprocess.DEVNULL, timeout=10)
            checks["chromium"] = candidate
            chromium_found = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue
    if not chromium_found:
        stop("Chromium not found (chromium / chromium-browser / google-chrome / headless_shell)")

    # Fixed venv path with psycopg + pytest (hard runner dependency)
    venv_path = Path("/tmp/pglast-venv-20261023")
    if not venv_path.is_dir():
        stop(f"venv path {venv_path} does not exist")
    venv_py = venv_path / "lib" / "python3.14" / "site-packages"
    if not venv_py.is_dir():
        stop(f"venv site-packages {venv_py} does not exist")
    # psycopg and pytest must be importable from the venv
    sys.path.insert(0, str(venv_py))
    for mod_name in ("psycopg", "pytest"):
        try:
            __import__(mod_name)
            checks[mod_name] = "ok"
        except ImportError as e:
            stop(f"{mod_name} not importable from {venv_py} ({e})")

    # Compose file present (FalkorDB / TLS fixtures are provisioned at runtime)
    compose_file = base / "dev/oracle2/compose.yaml"
    if not compose_file.is_file():
        stop(f"compose file {compose_file} not found")
    checks["compose_file"] = "ok"

    # FalkorDB image availability is verified at provisioning time; compose file
    # presence and docker on PATH are the pre-conditions checkable here.
    checks["falkordb"] = "deferred-to-provisioning"
    checks["tls_fixtures"] = "deferred-to-provisioning"

    checks["budget_label"] = "test-setup-only; NOT the W10 120s budget"
    checks["setup_inside_wall_clock"] = False
    return checks


# ---------------------------------------------------------------------------
# M4: whole-worktree source digest (content + mode) for mid-run mutation detection
# ---------------------------------------------------------------------------
def source_digest(base: Path) -> str:
    h = hashlib.sha256()
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=base, text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        stop(f"git ls-files failed for source digest: {e}")
    files = sorted(f for f in raw.split("\0") if f)
    for rel in files:
        p = base / rel
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        if p.is_file():
            h.update(p.read_bytes())
            h.update(b"\0")
            h.update(oct(p.stat().st_mode).encode("utf-8"))
        else:
            h.update(b"<absent>")
        h.update(b"\0")
    return h.hexdigest()


def sealed_content_digests(base: Path) -> dict:
    """Bind the documented sealed-set file SHAs for M3 receipt evidence."""
    digests = {}
    for rel in SEALED_SOURCE_PATHS:
        p = base / rel
        if p.is_file():
            digests[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            digests[rel] = "<absent>"
    return digests


# ---------------------------------------------------------------------------
# H4: post_run_scan with broader tokens + port/socket inspection
# ---------------------------------------------------------------------------
def post_run_scan(base: Path, label: str) -> dict:
    """Additive cleanup evidence beyond the drivers' ppid==child.pid scan.

    Known gap (named): the sealed drivers assert no remaining processes by
    scanning ppid == child.pid only; grandchildren reparent to init and pass
    that assertion. The name/port scan is leak evidence only — it must NEVER
    set live_lock_present (host Playwright MCP / chrome_crashpad / claude
    wrappers match those tokens). live_lock_present is path-scoped.
    """
    name_hits = []
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,comm,args"], text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines()[1:]:
            low = line.lower()
            if any(tok in low for tok in PROCESS_TOKENS):
                name_hits.append(line.strip())
    except BaseException as e:  # noqa: BLE001 - evidence collection, never masks main result
        name_hits.append(f"<ps-failed:{e}>")

    # H4: port/socket inspection via ss (fallback lsof) — leak evidence only.
    ports = []
    try:
        ss_out = subprocess.check_output(
            ["ss", "-tlnp"], text=True, stderr=subprocess.DEVNULL
        )
        for line in ss_out.splitlines()[1:]:
            if "next" in line.lower() or "node" in line.lower() or "chromium" in line.lower():
                ports.append(line.strip())
    except BaseException:
        try:
            lsof_out = subprocess.check_output(
                ["lsof", "-i", "-P", "-n"], text=True, stderr=subprocess.DEVNULL
            )
            for line in lsof_out.splitlines()[1:]:
                low = line.lower()
                if any(tok in low for tok in ("next", "node", "chromium", "tsx")):
                    ports.append(line.strip())
        except BaseException as e2:  # noqa: BLE001
            ports.append(f"<port-scan-failed:{e2}>")

    # Path-scoped live holders only. Directory existence is NOT a lock.
    # A failed /proc walk cannot prove absence — treat as live (fail-closed).
    scoped = scan_owned_lock_holders(base)
    holders = list(scoped["holders"])
    lock_dir = base / "apps/web/.next/dev"
    live_lock = bool(holders) or bool(scoped.get("scan_failed"))
    return {
        "label": label,
        "matching_processes": holders,
        "matching_rule": scoped.get("matching_rule", ""),
        "name_scan_processes": name_hits,
        "matching_ports": ports,
        "next_dev_dir_exists": lock_dir.exists(),
        "live_lock_present": live_lock,
        "scan_failed": scoped.get("scan_failed", False),
        "process_scan_clean": not name_hits and not any(
            p for p in ports if not p.startswith("<port-scan-failed")
        ),
        "known_gap": (
            "drivers' ppid==child.pid scan misses reparented grandchildren; "
            "the name/port scan is leak evidence only; live_lock is path-scoped"
        ),
    }


# ---------------------------------------------------------------------------
# C3 + path scope: stale_lock_precheck — live path-scoped holder, not a
# host-wide name scan and not mere directory existence
# ---------------------------------------------------------------------------
def stale_lock_precheck(base: Path, label: str) -> dict:
    """Refuse only when a live process binds this worktree's apps/web tree.

    Path-scoped contract (fail-closed for real holders, quiet for host noise):
      * STOP when cwd is under the owned apps/web (including .next/dev),
        an open fd points under it, or argv names that absolute path.
      * NEVER count host-level node/chromium/playwright/claude processes that
        merely contain those words (Playwright MCP, chrome_crashpad,
        claude-headroom, disclaimer wrappers).
      * Directory existence alone is NOT a lock: any clean Next run creates
        apps/web/.next/dev and leaves it behind.
    """
    scoped = scan_owned_lock_holders(base)
    holders = list(scoped["holders"])
    scan_failed = bool(scoped.get("scan_failed"))
    live = bool(holders) or scan_failed
    lock_dir = base / "apps/web/.next/dev"
    return {
        "label": label,
        "next_dev_dir_exists": lock_dir.exists(),
        "live_lock_present": live,
        "matching_processes": holders,
        "matching_rule": scoped.get("matching_rule", ""),
        "scan_failed": scan_failed,
        "scan_error": scoped.get("scan_error"),
        "proc_scanned": scoped.get("scanned", 0),
        "proc_unreadable": scoped.get("unreadable", 0),
        "ok": not live,
    }


# ---------------------------------------------------------------------------
# M2: Required natural unblock preconditions (procedural / operator-minted)
# ---------------------------------------------------------------------------
# These preconditions are documented in the plan as procedural gates.  The
# runner records whether they are asserted by the operator; it does not
# independently verify main-landed source, worktree freshness, or ALLOW.
# A receipt with verdict=APPROVE implies the reviewer confirmed these.
NATURAL_UNBLOCK_FIELDS = (
    "main_landed_source",
    "new_worktree",
    "source_declaration_allow",
)


def check_natural_unblock(receipt: dict) -> dict:
    """M2: enforce or explicitly mark procedural. We mark procedural and record."""
    return {
        "enforced": False,
        "mode": "procedural-operator-minted",
        "fields": {f: receipt.get(f, "<not-provided>") for f in NATURAL_UNBLOCK_FIELDS},
        "note": (
            "main-landed source, worktree freshness, and ALLOW are operator "
            "preconditions confirmed by the reviewer who minted the receipt; "
            "this runner does not independently re-verify them"
        ),
    }


# ---------------------------------------------------------------------------
# H1: clean-tree check
# ---------------------------------------------------------------------------
def clean_tree_check(base: Path) -> dict:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=base, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError as e:
        stop(f"git status failed: {e}")
    if out:
        lines = out.splitlines()
        preview = "; ".join(lines[:5])
        more = f" (+{len(lines) - 5} more)" if len(lines) > 5 else ""
        stop(f"uncommitted changes in worktree refuse sealed proof: {preview}{more}")
    return {"clean": True}


if __name__ == "__main__":
    require_linux_proc()

    # ===========================================================================
    # Main
    # ===========================================================================

    # H1: clean-tree check before anything else
    clean_tree = clean_tree_check(root)

    # Exact head binding before any work.
    try:
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError as e:
        stop(f"git rev-parse HEAD failed: {e}")

    # M3: sealed content digests (for receipt evidence / result.json binding)
    sealed_digests_before = sealed_content_digests(root)

    # Review-receipt requirement: exact-head APPROVE must exist before DB/Next.
    if not receipt_path.is_file():
        stop(f"review receipt required before execution; expected: {receipt_path}")
    try:
        receipt = json.loads(receipt_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        stop(f"malformed receipt JSON at {receipt_path}: {e}")

    if receipt.get("head") != actual:
        stop(f"receipt head {receipt.get('head')!r} != checked-out HEAD {actual!r}")
    if receipt.get("verdict") != "APPROVE":
        stop(f"receipt verdict {receipt.get('verdict')!r} != 'APPROVE'")
    if not receipt.get("reviewer"):
        stop("receipt missing 'reviewer' field")
    if not receipt.get("reviewed_at"):
        stop("receipt missing 'reviewed_at' field")

    # M2: natural unblock is procedural (recorded, not independently re-verified)
    natural_unblock = check_natural_unblock(receipt)

    digest_before = source_digest(root)

    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "services/oracle-brain"))
    sys.path.insert(0, str(root / "services/oracle-brain/tests"))
    sys.path.insert(0, "/tmp/pglast-venv-20261023/lib/python3.14/site-packages")
    os.umask(0o077)
    if scratch.exists():
        stop(f"scratch already exists; move it aside before re-run: {scratch}")
    scratch.mkdir(mode=0o700, exist_ok=False)

    from dev.oracle2.test_worker_postgres_fixture import (  # noqa: E402
        worker_postgres,
        owned_worker_database,
    )
    import psycopg  # noqa: E402
    from psycopg import sql  # noqa: E402

    # H5: executable resource preflight (fail-closed before any DB/Next)
    preflight = preflight_resources(root)

    (scratch_pre := Path("/tmp/oracle-parent24-wy02uT")).mkdir(parents=True, exist_ok=True)

    identity = None
    scans = []
    results = []
    timed_out = False
    compose_command = None
    compose_env = None
    falkor_port = None
    graph_url = None

    try:
        with worker_postgres(
            {
                **os.environ,
                "COMPOSE_PROJECT_NAME": "oracle2-synthetic-p24s11-next-me",
            },
            scratch / "worker",
            "event",  # C1: legal label matching (?:documentary-[0-9]{2}|event)
        ) as (tls, identity):
            project = identity["project"]
            base = tls["ORACLE2_TEST_ADMIN_URL"]

            # C2: bring up FalkorDB (falkor-candidate) alongside postgres.
            # worker_postgres only ups postgres; invocation A requires
            # ORACLE2_OPERATING_TEST_GRAPH_URL and the falkor-candidate container.
            compose_env = {
                **os.environ,
                "COMPOSE_PROJECT_NAME": project,
                "ORACLE2_POSTGRES_PORT": "0",
                "ORACLE2_CANDIDATE_PORT": "0",
            }
            compose_command = (
                "docker", "compose",
                "-f", str(root / "dev/oracle2/compose.yaml"),
                "-p", project,
            )
            try:
                subprocess.check_output(
                    [*compose_command, "up", "-d", "--wait", "falkor-candidate"],
                    env=compose_env, text=True, stderr=subprocess.PIPE, timeout=120,
                )
            except subprocess.CalledProcessError as e:
                stop(f"falkor-candidate provisioning failed: {e.stderr}")
            except subprocess.TimeoutExpired:
                stop("falkor-candidate provisioning timed out (120s)")

            # Resolve the falkor-candidate host port and build the graph URL.
            try:
                falkor_cid = subprocess.check_output(
                    [*compose_command, "ps", "-q", "falkor-candidate"],
                    env=compose_env, text=True, stderr=subprocess.PIPE, timeout=30,
                ).strip()
            except subprocess.CalledProcessError as e:
                stop(f"cannot list falkor-candidate container: {e.stderr}")
            if not re.fullmatch(r"[0-9a-f]{64}", falkor_cid):
                stop(f"falkor-candidate container id invalid: {falkor_cid!r}")
            try:
                falkor_details = json.loads(
                    subprocess.check_output(
                        ["docker", "inspect", falkor_cid],
                        text=True, stderr=subprocess.PIPE, timeout=15,
                    )
                )[0]
            except (subprocess.CalledProcessError, IndexError, json.JSONDecodeError) as e:
                stop(f"cannot inspect falkor-candidate: {e}")
            falkor_ports = falkor_details["NetworkSettings"]["Ports"].get("6379/tcp") or []
            if not falkor_ports or not any(p.get("HostIp") == "127.0.0.1" for p in falkor_ports):
                stop("falkor-candidate has no 127.0.0.1-mapped 6379/tcp port")
            falkor_port = int(falkor_ports[0]["HostPort"])
            graph_url = f"redis://:oracle2_candidate_local_only@127.0.0.1:{falkor_port}"

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
                # C2: graph URL + port for the FalkorDB-dependent invocation A
                "ORACLE2_OPERATING_TEST_GRAPH_URL": graph_url,
                "ORACLE2_CANDIDATE_PORT": str(falkor_port),
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
            for idx, (suite, rel) in enumerate(invocations):
                # C3: stale-lock pre-check between the two Next runs — LIVE lock only.
                pre = stale_lock_precheck(root, f"pre-{suite}")
                scans.append(pre)
                if not pre["ok"]:
                    stop(f"live process holds apps/web/.next/dev lock before {suite}: {pre}")

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

                # H3: Popen with start_new_session=True so we can killpg on timeout.
                with out_txt.open("w") as f:
                    proc = subprocess.Popen(
                        args,
                        cwd=root,
                        env=env,
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        proc.wait(timeout=ONE_SHOT_WALL_S)
                        returncode = proc.returncode
                        suite_timeout = False
                    except subprocess.TimeoutExpired:
                        suite_timeout = True
                        timed_out = True
                        # H3: kill the process group (start_new_session=True => pgid)
                        try:
                            pgid = os.getpgid(proc.pid)
                            os.killpg(pgid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError, OSError):
                            try:
                                proc.kill()
                            except OSError:
                                pass
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                        returncode = proc.returncode if proc.returncode is not None else -1

                # H2: JUnit totals — parse if present; if missing, report real failure.
                totals = None
                xml_error = None
                if xml.is_file():
                    try:
                        import xml.etree.ElementTree as ET

                        totals = {
                            k: sum(
                                int(s.get(k, 0))
                                for s in ET.parse(xml).getroot().iter("testsuite")
                            )
                            for k in ("tests", "failures", "errors", "skipped")
                        }
                    except Exception as e:  # noqa: BLE001 - report, do not traceback
                        xml_error = f"JUnit XML parse error: {e}"
                else:
                    xml_error = "JUnit XML file missing"

                result_entry = {
                    "suite": suite,
                    "returncode": returncode,
                    "timeout": suite_timeout,
                    "totals": totals,
                    "xml_error": xml_error,
                    "wall_clock_s": ONE_SHOT_WALL_S,
                    "budget_label": "test-setup-only; NOT the W10 120s budget",
                }
                if xml_error or suite_timeout:
                    # H2: report stderr tail so the real failure is visible
                    tail = ""
                    if out_txt.is_file():
                        tail = out_txt.read_text(errors="replace")[-3000:]
                    result_entry["output_tail"] = tail
                results.append(result_entry)
                scans.append(post_run_scan(root, f"post-{suite}"))
                print("EXACT_JUNIT", suite, totals if totals is not None else xml_error)

                if suite_timeout:
                    # H3: record and stop — do not continue to second invocation
                    break

                # H2: assert JUnit totals
                if totals is None:
                    stop(f"{suite}: cannot verify JUnit totals ({xml_error}); output tail recorded")
                if totals["tests"] <= 0:
                    stop(f"{suite}: tests={totals['tests']} (expected > 0)")
                if totals["failures"] != 0 or totals["errors"] != 0 or totals["skipped"] != 0:
                    stop(
                        f"{suite}: F/E/S={totals['failures']}/{totals['errors']}/{totals['skipped']} "
                        "(expected 0/0/0)"
                    )

                # M1: explicit returncode check (not bare assert)
                if returncode != 0:
                    stop(f"{suite}: returncode={returncode} (expected 0)")

            # Write result.json with full evidence
            (scratch / "result.json").write_text(
                json.dumps(
                    {
                        "head": actual,
                        "authoring_parent": AUTHORING_PARENT,
                        "receipt_head": receipt["head"],
                        "receipt_reviewer": receipt["reviewer"],
                        "receipt_reviewed_at": receipt["reviewed_at"],
                        "receipt_note": (
                            "procedural/operator-minted unsigned /tmp JSON; "
                            "not an integrity-bound signature (M3)"
                        ),
                        "natural_unblock": natural_unblock,
                        "clean_tree": clean_tree,
                        "sealed_content_digests": sealed_digests_before,
                        "preflight": preflight,
                        "database": name,
                        "project": identity["project"],
                        "falkor_port": falkor_port,
                        "graph_url": graph_url,
                        "invocations": results,
                        "timeout_any": timed_out,
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

            if timed_out:
                stop(f"invocation timed out after {ONE_SHOT_WALL_S}s; see result.json")

    finally:
        try:
            digest_after = source_digest(root)
            (scratch / "source-equality.json").write_text(
                json.dumps(
                    {
                        "before": digest_before,
                        "after": digest_after,
                        "equal": digest_before == digest_after,
                        "method": "whole-worktree git ls-files content+mode sha256",
                    },
                    indent=2,
                )
                + "\n"
            )
            if digest_before != digest_after:
                # M1: explicit check with reason, not bare assert
                stop("sealed source mutated during run (before/after digest mismatch)")

            project = identity["project"] if identity is not None else None
            if project is None:
                (scratch / "cleanup.json").write_text(
                    json.dumps({"observation": "UNKNOWN", "absence_proven": False}, indent=2)
                    + "\n"
                )
                stop("no identity yielded from worker_postgres; cleanup state unknown")

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

            # M5: write scans.json AFTER the post-cleanup scan is appended
            (scratch / "scans.json").write_text(json.dumps(scans, indent=2) + "\n")

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
            if any(remains.values()):
                stop(f"compose project resources remain after cleanup: {remains}")
        except SystemExit:
            raise
        except BaseException as e:
            (scratch / "cleanup.json").write_text(
                json.dumps(
                    {"observation": "UNKNOWN", "absence_proven": False, "error": str(e)},
                    indent=2,
                )
                + "\n"
            )
            # M6: exit 2 on cleanup failure, not traceback exit 1
            stop(f"cleanup failed: {e}")
