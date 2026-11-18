---
issue: 604
status: OPEN
owner: claude/bot-interview-conversation-diagnosis-9c163b
---

# Handoff — interview bot rebuild as a real serial conversation (plan written, nothing built)

The full build spec is the plan:
[plan_interview_conversation_rebuild.md](../plan_interview_conversation_rebuild.md)
(GitHub: https://github.com/u2giants/theoracle/blob/main/plan_interview_conversation_rebuild.md,
on `main`). **Read its STATUS table first; do
not re-derive or re-plan.** This file only registers the plan and carries what the plan
does not.

## 0. Business decisions only the owner can make

None — nothing in this workstream needs the owner (both earlier questions were
answered 2026-11-18; see below).

*Already settled — do NOT re-ask:*
- Serial, one message at a time; answer processed before the next message; each reply
  must use the answer (Albert, 2026-11-18).
- No limit on conversation length "as long as it's flowing and making sense. we just
  can't go back to the spamming that we got last week" (Albert, 2026-11-18; plan L9).
- First employees after Albert's own chat: Ilona, Jen, Carlos, Jessica (Albert,
  2026-11-18; plan L10). Albert will start the build in a new session himself.
- One question at a time at human pace; no dedupe against old question text; questions
  go to the relevant department (Albert, 2026-11-10/11, issue #518).

## 1. What this application is

The Oracle (https://github.com/u2giants/theoracle) builds a map of how POP Creations
works from documents, meetings and employee interviews. A Teams bot ("theoracle")
interviews staff in 1:1 chats. Brain: Python service `apps/brain` on Coolify
(https://oracle-brain.designflow.app/health). Web and Teams endpoints: Next.js
`apps/web` on Vercel. Database: its own Supabase Postgres (schema `cmap`); FalkorDB is
a rebuildable graph copy. Detail: plan §2.

## 2. What this session set out to do

Albert reported the bot "gives a generic response" and "doesn't seem to be having a
continuous conversation", asked for a diagnosis without changes, then asked for real
conversations to be checked and a plan to rebuild it as a serial back-and-forth, and
asked whether FalkorDB / the database is designed for that.

## 3. Current state

- Diagnosis complete, verified read-only against production on 2026-11-18. Findings
  and real examples: plan §6.
- Plan written and self-audited. Issue opened:
  https://github.com/u2giants/theoracle/issues/604 (plan Step 0 done).
- **No code, schema or production data was changed.** The bot is still ON in its
  current form (71 active, 3 paused; 545 open / 50 asked / 29 answered questions).
- Plan, this file and one router line in `AGENTS.md` are merged to `main`
  (https://github.com/u2giants/theoracle/pull/605,
  https://github.com/u2giants/theoracle/pull/606,
  https://github.com/u2giants/theoracle/pull/612).
- 2026-11-18: a Muse second opinion debated the plan against the code (two rounds,
  verdict "sound with changes"). Every accepted change is folded into the steps; the
  record is plan §13a. Do not re-run that debate.

## 4. What did NOT work / dead ends

- The Supabase, Vercel and Trigger MCP servers would not connect this session. Reading
  production with psql through the 1Password run-with-secret tool, in a read-only
  session, worked.
- First query assumed `cmap.job.status`; the column is `state`.
- Design dead ends (nine of them, with reasons) are in plan §7 — most importantly:
  replying inside the Teams web request, a priority flag on the single worker, and
  waiting for the whole chain are all non-starters.

## 5. Root causes and key findings

Plan §6. In one line each: the reply is a fixed string
(https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/inbound.py#L486);
no conversation record exists; Teams message ids are dropped on send
(https://github.com/u2giants/theoracle/blob/main/apps/web/app/api/teams/bot/proactive/route.ts#L188-L189)
and on receive
(https://github.com/u2giants/theoracle/blob/main/apps/web/app/api/teams/bot/messages/route.ts#L88-L123),
so quote-replies are filed on the wrong question; answers queue behind everything else
in one worker
(https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/worker.py#L57-L66);
questions are only created by a ~75-minute whole-map rebuild. Database verdict: the
stores are sound; the conversation machinery around them is missing.

## 6. Exact next steps

1. (Done 2026-11-18 — both owner questions answered; see §0.)
2. Execute the plan from Step 1 using its lead launch prompt (end of the plan).
   *Worked when:* each STATUS row cites its artefact and Step 11's evidence is on the
   issue.
3. When the plan's last step is proven, delete this file in that commit and fix the
   `AGENTS.md` line.

## 7. Constraints and gotchas

Plan §11. Especially: never push to `main`; production read-only outside the plan's
Steps 10–11; no hard-coded model names; English and zh-CN for every bot string; prove
the tick cannot double-send before any deploy (the 2026-11-10 flood).

## 8. Access and environment

Plan §12 (1Password vault `vibe_coding`, items by id; values never written down).
Bot history and operations notes:
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-11T1229Z-edge-dev3-claude-interview-bot-switch-on.md

## 9. Open questions and risks

- Exact shape of a Teams quote reply (plan Step 2 captures one before coding).
- Two workers side by side: decided in plan Step 4 (one advisory lock around
  orphan cleanup and resolve's write phase); its tests must pass before deploy.
- Teams behaviour nobody could verify from the repository (plan Step 2 captures it
  first): the id shape of sent and quoted messages, and how long a typing indicator
  shows.
- Out of scope but real, owned by #520: `communities` failed 13 of 48 runs and
  `process_pass` 14 of 16 in the 14 days to 2026-11-18; two confirmed mis-filed
  answers (plan §6.3) need re-filing. These are technical items for the repair plan,
  not owner questions.

## Self-audit (2026-11-18)

1. Newcomer can pick up without skipping a beat — yes: §3 state, §6 steps, and the
   plan's §5/§9 carry every file and gate.
2. As well as this session could — yes: all findings and rejected designs are in plan
   §6–§7; the only session-only knowledge (MCP failures, column name) is in §4 here.
3. Every detail for flawless execution — yes: goal plan §1, state §3, failures §4,
   decisions plan §8, risks §9 and plan §13, gates per step.
4. Owner reading only §0 sees every business decision — yes: a line-by-line pass found
   two (sitting length, volunteers), both answered the same day and moved to "already
   settled"; the remaining "open" items are technical and are
   assigned to plan steps or #520.
