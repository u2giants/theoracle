"""Offline pure proof of the path-scoped live-lock contract (no /proc, no DB, no Next).

PR201 one-shot false-positive fix: the sealed runner's stale-lock pre-check must
STOP only when a process actually binds THIS worktree's apps/web / .next/dev
(cwd under it, fd under it, or argv naming that absolute path). Host-level
node / chromium / playwright / claude name-or-args matches must NEVER count —
Playwright MCP, chrome_crashpad_handler, claude-headroom and disclaimer
wrappers previously matched PROCESS_TOKENS and STOPped the journey before any
DB/Next work. Directory existence alone is still not a lock. Real holders
remain fail-closed STOP.

This test loads the sealed runner module and exercises the pure predicate
``process_facts_reference_owned`` with injected process facts.
"""
from pathlib import Path
import importlib.util
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "scripts" / "oracle2" / "run-s11-next-multiemployee-proof-01.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_s11_next_multiemployee_proof_01", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses/typing edge cases can resolve.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


@pytest.fixture
def base(tmp_path_factory):
    # A synthetic worktree root shaped like the edge-dev3 execution tree.
    root = tmp_path_factory.mktemp("pr201-s11")
    (root / "apps" / "web").mkdir(parents=True)
    return root


HOST_NOISE_CASES = [
    (
        "playwright-mcp-guard",
        {
            "cwd": "/home/ahazan",
            "argv": [
                "/usr/bin/node",
                "/home/ahazan/.config/ai-devops/mcp-session-guard.mjs",
                "npx",
                "-y",
                "@playwright/mcp@0.0.79",
            ],
            "fd_targets": ["/dev/null", "socket:[12345]"],
        },
    ),
    (
        "chrome-crashpad",
        {
            "cwd": "/home/ahazan",
            "argv": [
                "/usr/lib/claude-desktop/chrome_crashpad_handler",
                "--monitor-self-annotation=ptype=crashpad-handler",
                "--database=/home/ahazan/.config/Claude/Crashpad",
            ],
            "fd_targets": ["pipe:[999]"],
        },
    ),
    (
        "claude-headroom-denied-chrome-tools",
        {
            "cwd": "/home/ahazan/repos/shared-db",
            "argv": [
                "/home/ahazan/.config/Claude/claude-code/2.1.308/f8b3641a8d36/claude.headroom-real",
                "--output-format",
                "stream-json",
                "--disallowedTools=claude-in-chrome,claude_for_Chrome,Claude_Preview",
                "--project-config-root",
                "/home/ahazan/repos/shared-db",
            ],
            "fd_targets": [],
        },
    ),
    (
        "disclaimer-playwright-wrapper",
        {
            "cwd": "/",
            "argv": [
                "/usr/lib/claude-desktop/resources/disclaimer",
                "--pgroup",
                "--",
                "node",
                "/home/ahazan/.npm/_npx/51691537fc71f2b0/node_modules/.bin/playwright-mcp",
            ],
            "fd_targets": [],
        },
    ),
    (
        "other-worktree-apps-web-not-owned",
        {
            "cwd": "/tmp/other-project/apps/web",
            "argv": ["node", "next", "dev"],
            "fd_targets": ["/tmp/other-project/apps/web/.next/dev/lock"],
        },
    ),
]


def test_host_level_node_chromium_playwright_claude_never_count(runner, base):
    for name, facts in HOST_NOISE_CASES:
        assert runner.process_facts_reference_owned(base=base, **facts) is False, name


def test_cwd_under_owned_apps_web_is_fail_closed_holder(runner, base):
    assert (
        runner.process_facts_reference_owned(
            cwd=str(base / "apps/web"),
            argv=["node", "next", "dev"],
            fd_targets=[],
            base=base,
        )
        is True
    )
    assert (
        runner.process_facts_reference_owned(
            cwd=str(base / "apps/web/.next/dev"),
            argv=[],
            fd_targets=[],
            base=base,
        )
        is True
    )
    assert (
        runner.process_facts_reference_owned(
            cwd=str(base / "apps/web/tests/oracle2"),
            argv=["tsx", "workspace-next-recipients-proof.ts"],
            fd_targets=[],
            base=base,
        )
        is True
    )


def test_fd_holding_owned_next_dev_is_fail_closed_holder(runner, base):
    lock = str(base / "apps/web/.next/dev/lock")
    assert (
        runner.process_facts_reference_owned(
            cwd="/tmp",
            argv=["/usr/bin/node", "some-unrelated-server"],
            fd_targets=["/dev/null", lock],
            base=base,
        )
        is True
    )
    deleted = lock + " (deleted)"
    assert (
        runner.process_facts_reference_owned(
            cwd="/tmp",
            argv=["node"],
            fd_targets=[deleted],
            base=base,
        )
        is True
    )


def test_argv_absolute_owned_path_is_fail_closed_holder(runner, base):
    owned = str(base / "apps/web/.next/dev")
    assert (
        runner.process_facts_reference_owned(
            cwd="/",
            argv=["node", "next", "--distDir", owned],
            fd_targets=[],
            base=base,
        )
        is True
    )
    embedded = str(base / "apps/web") + "/next.config.ts"
    assert (
        runner.process_facts_reference_owned(
            cwd="/",
            argv=["node", "next", "--file=" + embedded],
            fd_targets=[],
            base=base,
        )
        is True
    )


def test_relative_argv_with_worktree_cwd_is_fail_closed_holder(runner, base):
    assert (
        runner.process_facts_reference_owned(
            cwd=str(base),
            argv=["pnpm", "exec", "tsx", "apps/web/tests/oracle2/invented-auth-service.ts"],
            fd_targets=[],
            base=base,
        )
        is True
    )
    assert (
        runner.process_facts_reference_owned(
            cwd=str(base / "services"),
            argv=["node", "next", "dev", "--dir", "apps/web"],
            fd_targets=[],
            base=base,
        )
        is True
    )


def test_path_boundary_rejects_lookalike_trees(runner, base):
    lookalike = str(base) + "-extra/apps/web/.next/dev"
    assert (
        runner.process_facts_reference_owned(
            cwd="/",
            argv=["node", "next", "--distDir", lookalike],
            fd_targets=[lookalike],
            base=base,
        )
        is False
    )
    sibling = str(base / "apps/web-extra")
    assert (
        runner.process_facts_reference_owned(
            cwd=sibling,
            argv=["node"],
            fd_targets=[],
            base=base,
        )
        is False
    )


def test_directory_existence_alone_is_not_a_live_lock(runner, base, monkeypatch):
    # Next leaves apps/web/.next/dev behind after clean exit. Directory
    # existence alone must never set live_lock; only a live path-scoped holder
    # does. Host name matches are irrelevant.
    (base / "apps/web/.next/dev").mkdir(parents=True, exist_ok=True)
    assert (base / "apps/web/.next/dev").is_dir()
    assert (
        runner.process_facts_reference_owned(
            cwd="/",
            argv=["/usr/bin/node", "/home/ahazan/.config/ai-devops/mcp-session-guard.mjs"],
            fd_targets=[],
            base=base,
        )
        is False
    )
    monkeypatch.setattr(
        runner,
        "scan_owned_lock_holders",
        lambda _base: {
            "holders": [],
            "scanned": 1,
            "unreadable": 0,
            "scan_failed": False,
            "matching_rule": "path-scoped",
        },
    )
    pre = runner.stale_lock_precheck(base, "pre-invented")
    assert pre["next_dev_dir_exists"] is True
    assert pre["live_lock_present"] is False
    assert pre["ok"] is True


def test_scan_failure_is_fail_closed_not_a_free_pass(runner, base, monkeypatch):
    monkeypatch.setattr(
        runner,
        "scan_owned_lock_holders",
        lambda _base: {
            "holders": [],
            "scanned": 0,
            "unreadable": 0,
            "scan_failed": True,
            "scan_error": "invented /proc walk failure",
            "matching_rule": "path-scoped",
        },
    )
    pre = runner.stale_lock_precheck(base, "pre-invented")
    assert pre["scan_failed"] is True
    assert pre["live_lock_present"] is True
    assert pre["ok"] is False

