#!/usr/bin/env python3
"""
Bounded restart operator for Coolify native app vhmcdkdk23dgvjvcvhyhcjzd.
One outcome: genuine restart with pre/post StartedAt proof.
GET metadata + one POST restart. No authority renewal, no job replay.
"""
import json, os, sys, urllib.request, urllib.error, datetime, hashlib, time

BASE = "http://100.66.37.58:8000/api/v1"
APP_UUID = "vhmcdkdk23dgvjvcvhyhcjzd"  # oracle-public-invented-native-pr102
token = os.environ.get("COOLIFY_RW_TOKEN", "")
if not token:
    print("FATAL: COOLIFY_RW_TOKEN not set", file=sys.stderr)
    sys.exit(2)

RECEIPTS = []

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def api(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

def receipt(kind, status, detail):
    rec = {"ts": now(), "kind": kind, "status": status, "detail": detail}
    RECEIPTS.append(rec)
    print(json.dumps(rec))
    return rec

# --- Phase 1: pre-restart metadata ---
st, body = api("GET", f"/applications/{APP_UUID}")
if st != 200:
    receipt("pre-get-app", st, body[:300].decode("utf-8", "replace"))
    print("FATAL: cannot read app before restart", file=sys.stderr)
    sys.exit(1)
app = json.loads(body)
pre_status = app.get("status")
pre_updated = app.get("updated_at")
receipt("pre-app", st, {"uuid": app.get("uuid"), "name": app.get("name"),
                         "status": pre_status, "updated_at": pre_updated,
                         "git_commit_sha": app.get("git_commit_sha")})

# --- Phase 2: POST restart (the one mutation) ---
receipt("restart-attempt", "begin", {"app": APP_UUID, "action": "POST /applications/{}/restart".format(APP_UUID)})
st, body = api("POST", f"/applications/{APP_UUID}/restart")
receipt("restart-response", st, body[:500].decode("utf-8", "replace"))

if st not in (200, 201, 202):
    receipt("restart", "FAILED", {"http": st})
    print(json.dumps({"result": "NOT_PROVED", "reason": "restart http %s" % st, "receipts": RECEIPTS}))
    sys.exit(1)

# --- Phase 3: post-restart metadata (wait briefly for Coolify to act) ---
time.sleep(8)
st, body = api("GET", f"/applications/{APP_UUID}")
post = json.loads(body) if st == 200 else {}
receipt("post-app", st, {"uuid": post.get("uuid"), "status": post.get("status"),
                          "updated_at": post.get("updated_at"),
                          "git_commit_sha": post.get("git_commit_sha")})

result = {
    "result": "RESTART_ISSUED",
    "app": APP_UUID,
    "pre_status": pre_status,
    "post_status": post.get("status"),
    "pre_updated_at": pre_updated,
    "post_updated_at": post.get("updated_at"),
    "note": "Coolify restart accepted. Container StartedAt must be read via SSH docker inspect for genuine proof.",
    "receipts_sha256": hashlib.sha256(json.dumps(RECEIPTS, sort_keys=True).encode()).hexdigest(),
}
print(json.dumps(result))
