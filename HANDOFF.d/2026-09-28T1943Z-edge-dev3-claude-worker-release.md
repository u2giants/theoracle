---
issue: 50
status: OPEN
owner: the session that executes the worker release dispatch
---

# Legacy worker production release — handoff

## What this is
Albert asked (Claude chat, 2026-09-28): "release the workers" and "let's put z.ai on hold
for now and use the others." The exact plan is
`docs/operations/2026-09-28-worker-release-dispatch.md`; tracking issue #50.

## State
- Prod worker `20260909.1` (`28e8eb7`), 25 tasks. Nothing has been deployed.
- Deploy target pinned: `1ab6d0cd1abbba8fb17791364a28e7237c88880f` (revision 5).
- The dispatch must carry an APPROVE verdict from the independent reviewer on its exact
  commit before anyone executes it. `.ai/reviews/` is local scratch; the verdict line,
  review run id and reviewed commit are posted on #50 and copied into dispatch §Result
  at step 0.
- META_MUSE_API_KEY and STEPFUN_API_KEY are already in Trigger prod (#49); ZAI_API_KEY is not (on hold).
- Selecting Muse/StepFun in a pool is Albert's call, asked on #50.

## Next step
Once approved: execute dispatch §6 steps 0–7, watch to close-out, fill §Result, comment
on #50, and keep this file and #50 open until the dispatch §6 "Issue and handoff
stay open" conditions are met; then tick #50 and delete this file (successor rule, AGENTS.md §3a).
