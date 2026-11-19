---
issue: 607
status: OPEN
owner: claude/intake-1-4-5-1-status
---

# Handoff — PM message intake: cleaning and email done, gate probe next (2026-11-18)

Issue [u2giants/theoracle#607](https://github.com/u2giants/theoracle/issues/607). The plan is the brief: [plan_pm_message_intake.md](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md), STATUS first. Do not re-plan. Owner decisions: none open (see plan STATUS and §8).

## State (merged to main)

- 0.1–1.4 and 5.1 done. PR #633: `brain/intake/clean.py` (drop-only; `apply(conn, origin, signatures)` cleans staged rows in place) and `brain/intake/graph_mail.py` (plain-text `uniqueBody`, thread per conversation, message in both mailboxes stored once). The Teams reader now stores the same converted text as cleaning expects.
- Email live dry run on #607 (comment 6999532003): ~20,535 passages after cleaning, about 20x Teams + ClickUp. No real rows written yet; no paid call made.

## Next steps

1. Build the private signature allowlist (private store only, never git) and pass it to `clean.apply`.
2. Step 1.5: run the 200-thread probe on all three origins, email especially; build the gate only if it predicts ≥30% of tokens dropped.
3. Then 1.6, 2.1–2.5, 3.1, 4.1 in plan order; every paid run passes `intake_spend_cap`.

## Did not work

- `$select=meetingMessageType` on `/users/{id}/messages` returns 400 (it is an eventMessage field). Calendar mail is detected from `@odata.type` instead.
- Long reads exceed the 1Password MCP run timeout: launch with `nohup … &` inside op_run and write counts to a `$TMPDIR` file.
- `op` CLI is not signed in on edge-dev; op_run with `op://vibe_coding/...` works (vault by name, not id).

## Constraints

Public repo: counts and dollars only. Spend cap every run. Branch and PR; the AI merges. Times in EST.
