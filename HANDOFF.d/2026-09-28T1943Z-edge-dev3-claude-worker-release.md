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
- Deploy target pinned: `5a441199925d0ddb5a76374f44b8c3243a303214` (revision 6).
- The dispatch must carry an APPROVE verdict from the independent reviewer on its exact
  commit before anyone executes it. `.ai/reviews/` is local scratch; the approval record
  (verdict line, review file, reviewed commit) is posted on #50, never written into the
  dispatch file.
- META_MUSE_API_KEY and STEPFUN_API_KEY are already in Trigger prod (#49); ZAI_API_KEY is not (on hold).
- Model selection is Albert's on the settings page; the release does not depend on it.

## Next step
Once approved: execute dispatch §6 steps 0–8. Post the approval record and every result
on #50; never edit the dispatch file except the step-8 `Status:` line in the post-
execution docs PR. Keep this file and #50 open until the dispatch's "#50 and the handoff
stay open" conditions are met; then tick #50 and delete this file (AGENTS.md §3a). If
you end before then, write your own handoff naming #50 per §6 step 7 "Watch ownership".
