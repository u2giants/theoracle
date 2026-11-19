---
issue: 607
status: OPEN
owner: claude/intake-handoff-1-6
---

# Handoff — PM message intake: phase 1 done, phase 2 next (2026-11-19)

Issue [u2giants/theoracle#607](https://github.com/u2giants/theoracle/issues/607). Plan: [plan_pm_message_intake.md](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md), STATUS first. Do not re-plan.

## Owner decisions

Settled 2026-11-19 8:18 AM EST: *"ok, keep exact words through the pilot"*. No summaries as evidence; the pilot (3.1) reports cost per kept thread plus an all-employee projection so the owner can decide afterwards. Nothing open.

## State (all merged)

- Phase 1 done: collectors (1.2, 1.3, 5.1), cleaning (1.4, with same-subject chain line dedupe and a private signature allowlist at `~/.config/oracle-private/intake_signatures.json` on edge-dev, mode 600, never git), gate not needed (1.5), ingest (1.6, PR #643, merge f7dc8140).
- Private staging holds all three sources, cleaned: 3,373 pending threads (#607 comment 7000436774). No sources ingested yet; no paid model call made.
- `sql/038_intake_sources.sql` goes live only when the brain is redeployed (Coolify deploys the tag in `BRAIN_IMAGE_TAG`; it is not automatic). Do that at the start of 3.1, then confirm the two constraints include `message_record` and `intake_update`.

## Next steps (plan order)

1. Phase 2 is a context cut point: start fresh. 2.1 gold sample (private store on edge-dev3), 2.2, 2.3, 2.4, 2.5.
2. 3.1 pilot with `BRAIN_INTAKE_MAX_USD`; run `python -m brain.intake.ingest --limit N`; report the owner's cost numbers.

## Did not work / gotchas

- The 1Password MCP run tool times out after ~2 minutes: start long runs with `nohup … &` inside it.
- `ai-task-gates` escalates any `apps/brain/brain/sql/*.sql` change to class `shared-db`; declare it before waiting on the PR.
- ScaleDown summarize: 403 on the account.

## Constraints

Public repo: counts and dollars only. Spend cap on every paid run. Branch and PR; the AI merges. Times in EST.
