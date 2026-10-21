"""Validate the compose embedded in docs/implementation/falkordb-coolify-deploy-plan.md.

Exact-equality gate: each role's block is rendered, normalized by `docker compose config --format json`
(fixed dummy env values), and compared field-for-field and byte-for-byte (entrypoint/command scripts
included) with a committed golden fixture `golden/falkordb-<role>.json`. Any difference fails with a diff.
Regenerate goldens only deliberately: `--write-golden`, then review the fixture diff.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE.parents[2] / "docs/implementation/falkordb-coolify-deploy-plan.md"
GOLDEN = HERE / "golden"
ROLES = {"confirmed": (6390, 16390), "candidate": (6391, 16391)}
DUMMY_ENV = {"FALKORDB_PASSWORD": "invented-placeholder", "FALKORDB_SERVER_TLS_B64": "aW52ZW50ZWQ="}


def compose_block(text: str | None = None) -> str:
    blocks = re.findall(r"```yaml\n(.*?)```", PLAN.read_text() if text is None else text, re.S)
    blocks = [b for b in blocks if "<ROLE>" in b]
    if len(blocks) != 1:
        raise ValueError(f"expected 1 compose yaml block containing <ROLE>, found {len(blocks)}")
    return blocks[0]


def _private_controlplane_host():
    from urllib.parse import urlsplit
    sys.path.insert(0, str(HERE.parents[2] / 'services' / 'oracle-brain'))
    from oracle_brain.private_targets import read_private_target
    return urlsplit(read_private_target('coolify_api_base_url')).hostname


HOST_MARKER = 'PRIVATE_HOST_SHA256_69e08d69438f83a96aefc4a9f82450e9244100f6db11b1e2cae8f3b956f054ae'


def render(role: str, block: str | None = None) -> str:
    port, pub = ROLES[role]
    source = compose_block() if block is None else block
    if source.count(HOST_MARKER) != 1 or re.search(r'PRIVATE_HOST_SHA256_(?!69e08d69438f83a96aefc4a9f82450e9244100f6db11b1e2cae8f3b956f054ae)', source):
        raise ValueError('exact pinned controlplane marker required')
    source = source.replace(HOST_MARKER, _private_controlplane_host())
    return (source.replace("<ROLE>", role)
            .replace("<PUBPORT>", str(pub)).replace("<PORT>", str(port)))


def normalize(rendered: str) -> str:
    """`docker compose config` as sorted, indented JSON; raises on any compose error."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "FALKORDB_"))}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d, "compose.yaml")
        path.write_text(rendered)
        out = subprocess.run(["docker", "compose", "-f", str(path), "config", "--format", "json"],
                             env={**env, **DUMMY_ENV}, capture_output=True, text=True, cwd=d)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "docker compose config failed")
    document = json.loads(out.stdout)
    # One defined legacy-real binding only: wrong hosts must fail, never redact into approval.
    bindings = document['services']['tailnet-fwd']['ports']
    if len(bindings) != 1 or bindings[0]['host_ip'] != _private_controlplane_host():
        raise ValueError('exact pinned controlplane binding required')
    bindings[0]['host_ip'] = HOST_MARKER
    return json.dumps(document, indent=1, sort_keys=True) + "\n"


def compose_version() -> str:
    try:
        out = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True)
    except FileNotFoundError:
        return "unavailable"
    return out.stdout.strip() if out.returncode == 0 else "unavailable"


def version_note() -> str | None:
    """Note (never a failure) when the local Compose differs from the goldens' generator."""
    try:
        meta = json.loads((GOLDEN / "meta.json").read_text())
    except Exception as exc:
        return f"note: golden meta unreadable ({type(exc).__name__})"
    have = compose_version()
    if have != meta.get("generator_compose_version"):
        return f"note: compose {have} differs from golden generator {meta.get('generator_compose_version')}"
    return None


def check(role: str, rendered: str) -> list[str]:
    try:
        want = (GOLDEN / f"falkordb-{role}.json").read_text()
    except OSError as exc:
        return [f"golden fixture unavailable: {type(exc).__name__}: {exc}"]
    try:
        got = normalize(rendered)
    except FileNotFoundError as exc:  # docker CLI absent
        return [f"tooling unavailable: {exc}"]
    except Exception as exc:  # compose rejected the rendered block → controlled FAIL
        return [f"malformed compose: {type(exc).__name__}: {exc}"]
    if got == want:
        return []
    diff = difflib.unified_diff(want.splitlines(), got.splitlines(), "golden", "rendered", lineterm="", n=1)
    return ["golden mismatch:\n" + "\n".join(diff)]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        block = compose_block()
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    if argv == ["--write-golden"]:
        meta = json.loads((GOLDEN / "meta.json").read_text()) if (GOLDEN / "meta.json").exists() else {}
        if meta and compose_version() != meta.get("generator_compose_version"):
            print("FAIL: refusing to regenerate goldens with a different Compose version than the recorded generator")
            return 1
        GOLDEN.mkdir(parents=True, exist_ok=True)
        try:
            rendered = {role: normalize(render(role, block)) for role in ROLES}
        except Exception as exc:
            print(f"FAIL: cannot normalize: {type(exc).__name__}: {exc}")
            return 1
        for role, text in rendered.items():
            (GOLDEN / f"falkordb-{role}.json").write_text(text)
        (GOLDEN / "meta.json").write_text(json.dumps({"generator_compose_version": compose_version()}, indent=1) + "\n")
        print("golden fixtures written; review their diff before committing")
        return 0
    note = version_note()
    if note:
        print(note)
    bad = 0
    for role in ROLES:
        try:
            errs = check(role, render(role, block))
        except Exception as exc:
            errs = [f"malformed compose: {type(exc).__name__}: {exc}"]
        print(f"{role}: {'PASS' if not errs else 'FAIL ' + '; '.join(errs)}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
