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
- Deploy target pinned: `a12e25e2db6090776f3c2494bcdd36cc77cbcaac`.
- The dispatch must carry an APPROVE verdict from the independent reviewer on its exact
  commit before anyone executes it. Check the latest review file under `.ai/reviews/`
  and #50 comments.
- No Meta Muse / Z.ai / StepFun key is in Trigger prod, so this release activates no new
  provider. Activating Meta Muse is a separate env write Albert must name.

## Next step
Once approved: execute dispatch §6 steps 0–7, watch to close-out, fill §Result, comment
on #50, tick it, and delete this file (successor rule, AGENTS.md §3a).
