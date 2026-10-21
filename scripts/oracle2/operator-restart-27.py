#!/usr/bin/env python3
"""
Bounded restart operator for Coolify native app vhmcdkdk23dgvjvcvhyhcjzd.
One outcome: genuine restart with pre/post StartedAt proof from docker inspect.
Reads use the read-only token; the single mutation uses the read/write token.
No authority renewal, no job replay, no freshness weakening.

Transport note: Coolify uses its exact privately pinned API endpoint.
That address is reachable only over the encrypted Tailscale overlay; the
owner explicitly issued the read/write token for this managed-platform route
(Albert, 2026-10-14). SSH metadata uses BatchMode key auth to vps2.

Invocation: python3 operator-restart-27.py --confirm-restart
Without --confirm-restart the script only reads metadata and exits 0.
"""
import json, os, sys, urllib.request, urllib.error, datetime, hashlib, time, subprocess

# Metadata resolution never grants restart authority.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services' / 'oracle-brain'))
from oracle_brain.private_targets import read_private_target
BASE = read_private_target('coolify_api_base_url')
APP_UUID = "vhmcdkdk23dgvjvcvhyhcjzd"
APP_NAME = "oracle-public-invented-native-pr102"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=15", "vps2"]

RECEIPTS = []

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def receipt(kind, status, detail):
    rec = {"ts": now(), "kind": kind, "status": status, "detail": detail}
    RECEIPTS.append(rec)
    print(json.dumps(rec, default=str), flush=True)
    return rec

def api(method, path, token, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

def safe_json(raw):
    try:
        return json.loads(raw)
    except Exception as e:
        return {"_parse_error": str(e), "_raw_preview": raw[:200].decode("utf-8", "replace")}

def ssh_inspect_startedat():
    """Read-only docker inspect of oracle-native-vhmcdkdk containers. Returns list of role dicts."""
    cmd = (
        "for c in $(docker ps -a --filter name=oracle-native-vhmcdkdk --format '{{.ID}}'); do "
        "docker inspect --format "
        "'{{.Name}}|{{.State.Status}}|{{.State.StartedAt}}|{{.State.FinishedAt}}|{{.State.ExitCode}}|{{.RestartCount}}' "
        "$c; done"
    )
    try:
        p = subprocess.run(SSH + [cmd], capture_output=True, timeout=30, text=True)
    except Exception as e:
        return {"_error": str(e)}
    rows = []
    for line in p.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) >= 6:
            rows.append({
                "name": parts[0], "status": parts[1], "started_at": parts[2],
                "finished_at": parts[3], "exit_code": parts[4], "restart_count": parts[5],
            })
    return {"rows": rows, "count": len(rows), "rc": p.returncode}

def main():
    confirm = "--confirm-restart" in sys.argv
    ro = os.environ.get("COOLIFY_RO_TOKEN", "")
    rw = os.environ.get("COOLIFY_RW_TOKEN", "")
    if not ro:
        receipt("env", "FATAL", "COOLIFY_RO_TOKEN not set")
        return 2

    # Phase 1: pre metadata (RO token)
    st, body = api("GET", f"/applications/{APP_UUID}", ro)
    app = safe_json(body) if st == 200 else {}
    if app.get("uuid") and app.get("uuid") != APP_UUID:
        receipt("identity", "MISMATCH", {"expected": APP_UUID, "got": app.get("uuid")})
        return 1
    pre_app = {
        "uuid": app.get("uuid"), "name": app.get("name"), "status": app.get("status"),
        "updated_at": app.get("updated_at"), "git_commit_sha": app.get("git_commit_sha"),
    }
    receipt("pre-app", st, pre_app)

    pre_containers = ssh_inspect_startedat()
    receipt("pre-containers", pre_containers.get("count", 0), pre_containers)

    if not confirm:
        receipt("mode", "read-only", "pass --confirm-restart to mutate")
        print(json.dumps({"result": "READ_ONLY_OK", "pre_app": pre_app,
                          "pre_container_count": pre_containers.get("count"),
                          "receipts_sha256": hashlib.sha256(json.dumps(RECEIPTS, sort_keys=True, default=str).encode()).hexdigest()}))
        return 0

    # Phase 2: single mutation (RW token)
    if not rw:
        receipt("env", "FATAL", "COOLIFY_RW_TOKEN required for --confirm-restart")
        return 2
    receipt("restart-attempt", "begin", {"app": APP_UUID, "method": "POST", "path": f"/applications/{APP_UUID}/restart"})
    st, body = api("POST", f"/applications/{APP_UUID}/restart", rw)
    receipt("restart-response", st, body[:500].decode("utf-8", "replace"))
    if st not in (200, 201, 202):
        receipt("restart", "NOT_PROVED", {"http": st})
        print(json.dumps({"result": "NOT_PROVED", "reason": f"restart http {st}"}))
        return 1

    # Phase 3: post metadata (RO token + SSH)
    time.sleep(10)
    st2, body2 = api("GET", f"/applications/{APP_UUID}", ro)
    post_app = safe_json(body2) if st2 == 200 else {}
    if post_app.get("uuid") and post_app.get("uuid") != APP_UUID:
        receipt("identity-post", "MISMATCH", {"expected": APP_UUID, "got": post_app.get("uuid")})
    receipt("post-app", st2, {
        "uuid": post_app.get("uuid"), "status": post_app.get("status"),
        "updated_at": post_app.get("updated_at"), "git_commit_sha": post_app.get("git_commit_sha"),
    })

    post_containers = ssh_inspect_startedat()
    receipt("post-containers", post_containers.get("count", 0), post_containers)

    # Compare StartedAt: at least one long-running role must show a newer StartedAt
    def started_map(c):
        return {r["name"]: r["started_at"] for r in c.get("rows", []) if r.get("started_at")}
    pre_s, post_s = started_map(pre_containers), started_map(post_containers)
    changed = []
    for name, t in post_s.items():
        if name in pre_s and pre_s[name] != t:
            changed.append({"name": name, "pre": pre_s[name], "post": t})
    identical = len(pre_s) > 0 and pre_s == post_s

    if identical or not changed:
        receipt("startedat-compare", "NOT_PROVED", {
            "reason": "no StartedAt changed (restart may be no-op)",
            "pre_count": len(pre_s), "post_count": len(post_s),
        })
        print(json.dumps({"result": "NOT_PROVED", "reason": "StartedAt unchanged",
                          "pre_s": pre_s, "post_s": post_s,
                          "receipts_sha256": hashlib.sha256(json.dumps(RECEIPTS, sort_keys=True, default=str).encode()).hexdigest()}))
        return 1

    receipt("startedat-compare", "PROVED", {"changed_count": len(changed), "changed": changed[:20]})
    result = {
        "result": "PROVED_RESTART",
        "app": APP_UUID,
        "pre_status": pre_app.get("status"),
        "post_status": post_app.get("status"),
        "changed_startedat": changed,
        "receipts_sha256": hashlib.sha256(json.dumps(RECEIPTS, sort_keys=True, default=str).encode()).hexdigest(),
    }
    print(json.dumps(result, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
