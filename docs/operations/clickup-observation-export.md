# Bounded private ClickUp observation export — review input

Owner: Oracle coordinator, existing issue #27 / W07–W08. Prepared October 12, 2026, 1:05 PM EDT. This record authorizes nothing by itself. Assigned independent reviewer APPROVE of this exact head, script hash, target, metadata pin and read/persistence action is required before root executes. No payload export has run.

## Exact action and target

One read-only export from existing Cloudflare account `8303d11002766bf1cc36bf2f07ba6f20`, D1 database `c37aeb36-e16e-416b-b699-c910f6f8dc10` (`clickup-events`), `events`, predicate `event_type='taskStatusUpdated' AND workspace_id='2298436'`, sorted capture IDs, maximum 817 fetched rows with exact 816 expected / 360 task cases. All 816 originals remain in existing D1; no full-body duplication. Existing documented D1-read credential is injected through protected operator environment; neither credential value nor vault reference appears in code.

The protected preparatory metadata snapshot contains only capture ID, task ID, received_at and UTF-8 payload byte length. Canonical sorted-key compact JSON SHA256 is `37657c579e5b2aeb8011f4e81ba527d5bbd8ca682e852a0be7fc22f791d6bf7b`. Source count/metadata drift stops; original bytes are hashed during approved execution and read again before private persistence. Metadata pin does not prove payload immutability prior to first approved read. Export preserves that limitation. Maximum original bytes 4 MiB; observed aggregate 511,954 bytes.

Persist only private minimized events and original-reference receipts under a new absolute directory (0700/files0600): native webhook_id:history_item_id identity; native task ID; status-before/status-after, status activity; native epoch milliseconds normalized UTC; actor ID only; capture ID, original SHA256 and receipt time. No names, email, titles, comments, customer/product text, interview questions or full original bodies. Native original evidence stays addressable by fixed D1 database/capture ID/hash. No list or space binding; no current task lookup; no inferred workflow_stage/checkpoint map.

## Evidence limits and acceptance scope

The stored 816 payloads have ClickUp event shape, stable native IDs/timestamps/actors and next statuses; only 531 have observed prior status, while 285 preserve missing/null predecessor explicitly. Official primary documentation defines native date as Unix milliseconds and recommends webhook_id:history_item_id idempotency: https://developer.clickup.com/docs/webhooktaskpayloads and https://developer.clickup.com/docs/webhooks .

Capture authenticity remains UNVERIFIED: live Workers catalog on the same account returned successful empty list. No deployed producer/signature-enforcement identity was available. This is stored ClickUp-shaped observation history; it must not be called authenticated capture or complete enterprise workflow history without further proof. Root must explicitly accept this provenance limitation or leave intake blocked. No credential/Worker changes, new webhook, connector, auth consent, source writes or provider dispatch are authorized.

Observation-only process identifier `clickup-workspace-2298436-task-status-observation` denotes export scope, not a business workflow match. Native time window is 1774912663018 through 1791568623421 epoch milliseconds. Capture continuity, missed/deleted events, first case state, legal completion state and right/left/history censoring remain unproved. Explicitly prohibit complete-cycle, conformance, ROI, personnel grading and company-question generation claims. Raw observation export cannot itself close W07/W08 business acceptance. Root independently reviews source permission digest/census, documentary mapping, immutability custody and metric rights later.

## Execution and recovery

The root checks exact assigned approval and task gates, script hash below and metadata pin, then injects the existing read credential only via env into this protected operator. Root passes new protected destination plus the literal pinned fingerprint. Re-read compares complete selected original rows byte-for-byte before persistence; any added/corrected/deleted row fails. Files use exclusive creation, private permissions and fsync. A filesystem failure may leave partial files; absent final manifest means unusable export and no acceptance. Source is unchanged; recovery preserves partial receipts and retries only into another new directory under a fresh read/review if inputs changed. No stdout private content; errors fail generically.

Local synthetic fixture tests passed six tests: event normalization/private minimization/original hash linkage, count/order refusal, workspace/task/event/actor mismatch, native ID duplicate rejection, byte budget/multiple-history shape refusal. These are script checks, not live intake proof. Actual original payload export has not run.

Script SHA256: `4005b9a9482ad45fe5a907d14196113df4775f672d088f4e86f4858346b2e812`.

```python
"""Pinned read-only Oracle ClickUp original export. Root review required before run."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

ACCOUNT = "8303d11002766bf1cc36bf2f07ba6f20"
DATABASE = "c37aeb36-e16e-416b-b699-c910f6f8dc10"
WORKSPACE = "2298436"
REVIEWED_METADATA_SHA = "37657c579e5b2aeb8011f4e81ba527d5bbd8ca682e852a0be7fc22f791d6bf7b"
EXPECTED_ROWS = 816
EXPECTED_CASES = 360
MAX_BYTES = 4 * 1024 * 1024
PREDICATE = "event_type='taskStatusUpdated' AND workspace_id='2298436'"

def sha(value):
    return hashlib.sha256(value).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("redirect refused")

def query(sql, params=None):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/d1/database/{DATABASE}/query",
        data=canonical({"sql": sql, "params": params or []}),
        headers={"Authorization": "Bearer " + os.environ["D1_READ_TOKEN"], "Content-Type": "application/json"},
        method="POST")
    with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
        result = json.load(response)
    if not result.get("success") or len(result.get("result", [])) != 1 or not result["result"][0].get("success"):
        raise ValueError("read failed")
    return result["result"][0]["results"]

def normalize(rows):
    if len(rows) != EXPECTED_ROWS:
        raise ValueError("original count drift")
    seen, cases, capture_ids, events, originals = set(), set(), set(), [], []
    previous = -1
    total = 0
    for row in rows:
        capture = row["id"]
        if not isinstance(capture, int) or capture <= previous or capture in capture_ids:
            raise ValueError("capture order drift")
        previous = capture
        capture_ids.add(capture)
        payload_bytes = row["payload"].encode("utf-8")
        total += len(payload_bytes)
        if total > MAX_BYTES:
            raise ValueError("payload budget exceeded")
        payload = json.loads(row["payload"])
        if payload.get("event") != "taskStatusUpdated" or str(payload.get("team_id")) != WORKSPACE or str(payload.get("task_id")) != str(row["task_id"]):
            raise ValueError("original identity drift")
        webhook = payload.get("webhook_id")
        items = payload.get("history_items")
        if not isinstance(webhook, str) or not webhook or not isinstance(items, list) or len(items) != 1:
            raise ValueError("native event shape drift")
        item = items[0]
        if item.get("field") != "status" or not item.get("id"):
            raise ValueError("status identity absent")
        identity = webhook + ":" + str(item["id"])
        if identity in seen:
            raise ValueError("duplicate event")
        seen.add(identity)
        case = str(payload["task_id"])
        if not case:
            raise ValueError("case absent")
        cases.add(case)
        millis = item.get("date")
        if not isinstance(millis, str) or not millis.isdigit() or len(millis) != 13:
            raise ValueError("timestamp shape drift")
        timestamp = dt.datetime.fromtimestamp(int(millis) / 1000, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        before, after = item.get("before"), item.get("after")
        actor = item.get("user", {}).get("id")
        if not isinstance(before, dict) or not isinstance(after, dict) or (before.get("status") is not None and not isinstance(before.get("status"), str)) or not isinstance(after.get("status"), str) or not isinstance(actor, int) or isinstance(actor, bool):
            raise ValueError("native status/actor absent")
        events.append({"event_id": identity, "case_id": case, "activity": after["status"], "timestamp": timestamp, "timestamp_ms": millis, "before_status": before.get("status"), "before_state": "observed" if isinstance(before.get("status"), str) else "unobserved", "before_status_field": "missing" if "status" not in before else ("null" if before["status"] is None else "value"), "after_status": after["status"], "actor_id": str(actor), "process_id": "clickup-workspace-2298436-task-status-observation", "original_capture_id": capture, "original_sha256": sha(payload_bytes)})
        originals.append({"capture_id": capture, "received_at": row["received_at"], "sha256": sha(payload_bytes)})
    if len(cases) != EXPECTED_CASES:
        raise ValueError("case count drift")
    return events, originals

def inventory(rows):
    return [{"id": r["id"], "task_id": r["task_id"], "received_at": r["received_at"], "payload_bytes": len(r["payload"].encode("utf-8"))} for r in rows]

def read():
    rows = query(f"SELECT id,task_id,payload,received_at FROM events WHERE {PREDICATE} ORDER BY id LIMIT 817")
    normalize(rows)
    return rows

def save(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def main():
    # Root passes the independently reviewed inventory fingerprint. No review bypass default.
    if len(sys.argv) != 3 or sys.argv[2] != REVIEWED_METADATA_SHA:
        raise ValueError("protected destination and reviewed original fingerprint required")
    destination = Path(sys.argv[1])
    if not destination.is_absolute() or destination.exists():
        raise ValueError("fresh absolute destination required")
    rows = read()
    fingerprint = sha(canonical(inventory(rows)))
    if fingerprint != sys.argv[2]:
        raise ValueError("reviewed original fingerprint mismatch")
    events, originals = normalize(rows)
    # Compare originals twice. Any correction/insertion/deletion fails closed before persistence.
    if canonical(read()) != canonical(rows):
        raise ValueError("concurrent original drift")
    destination.mkdir(mode=0o700)
    raw = canonical(originals)
    normalized = canonical(events)
    save(destination / "original-references.json", raw)
    save(destination / "events.json", normalized)
    manifest = {"account_id": ACCOUNT, "database_id": DATABASE, "workspace_id": WORKSPACE, "row_count": len(rows), "case_count": len({e["case_id"] for e in events}), "reviewed_metadata_fingerprint": fingerprint, "original_references_sha256": sha(raw), "events_sha256": sha(normalized), "native_window_ms": [min(e["timestamp_ms"] for e in events), max(e["timestamp_ms"] for e in events)], "capture_window": [min(r["received_at"] for r in rows), max(r["received_at"] for r in rows)], "scope": "raw task status observation only", "censoring": "capture continuity, case starts/ends, missed/deleted events and complete cycles unproved", "rights": "private read-only source intake; no generation, grading, conformance, personnel evaluation or ROI rights", "capture_authenticity": "stored webhook shape proven; deployed producer/signature verification not yet proven"}
    save(destination / "manifest.json", canonical(manifest))
    print(json.dumps({"rows": len(rows), "cases": manifest["case_count"], "events_sha256": manifest["events_sha256"]}))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Export refused; protected operator must inspect the cause without disclosing payloads.", file=sys.stderr)
        sys.exit(1)
```

Correction: reviewed first read refused before persistence because 285 originals lack prior status text. Preserve all 816 observations, with before_status null/before_state unobserved and before_status_field missing or null; 531 observed predecessors remain verbatim. No inferred predecessor, exclusion or completeness claim. Fresh independent review required before execution.
