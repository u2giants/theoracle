# S07 Create-child fresh invented proof plan (runner packet)

Prepared only. No database, provider, native, or production effect is authorized by this file.
Root release after independent exact source + one resource-plan assessment is required before any run.

## Exact inputs

| Input | Value |
|---|---|
| Current main with diagnostics | `e9531f98` (includes PR196 fixture-only diagnostics) |
| Diagnostic evidence note | `docs/verification/oracle2/s07-create-child-fixture-diagnostics.md` |
| Failing historical run | 39760061151 (5370 cases, 1 failure) |
| Known child signal | exit 2, `stage:exchange`, `state:UNKNOWN`, protected channel refused `http-headers` then `closed-wire` |
| Hypothesis | second `current_v1` inside `beforeWrite` during `exchange_provider_v1` gets 503 from protected service |

## What the next run must capture (already in source)

- Driver catch: `error_type` (exception constructor name) with `state`/`remote_stop_proven`/`stage`
- Create worker server handler: status/header fields to `create-server-responses.jsonl`
- Before assertion: supervisor witness results, claim-time DB state, stage/error_type, server response log in `create-child-diagnostics.json`

## Constraints (unchanged)

- Do not suppress strict framing/currentness
- Do not refresh the original window
- Do not resend an uncertain claim
- Keep UNKNOWN/no-resend semantics
- Keep all meaningful positives and negatives
- No production public error leak
- No guard change, no retry, no fallback

## Gate before one fresh invented instance

1. Independent exact SOURCE assessment of current main diagnostic delta (PR196 bytes) + this plan
2. Independent ONE resource-plan assessment (fresh PG + owned graph, canonical once, owned phase)
3. True database gate with a review receipt binding this exact HEAD
4. Root one-fresh release decision
5. Execute one fresh invented instance under original limits
6. Read the new diagnostics and either name the exact cause or record the remaining UNKNOWN with evidence
7. Only then author a permanent fix; a rerun with no cause is not a repair

## Success check

Exact cause found and permanently repaired while the same capabilities, strict framing, currentness, UNKNOWN and no-resend retain meaningful positives and negatives, and full current-main W10 (5370+changed population) is clean with 0 F/E/S and all ten workers under 120s.

Posted by MiMo chat on edge-dev3.
