---
issue: 604
status: OPEN
owner: claude/bot-interview-conversation-diagnosis-9c163b
---

# Handoff — interview bot rebuild as a real serial conversation (plan written, nothing built)

The full build spec is the plan:
[plan_interview_conversation_rebuild.md](../plan_interview_conversation_rebuild.md)
(GitHub: https://github.com/u2giants/theoracle/blob/main/plan_interview_conversation_rebuild.md
once the plan PR merges; until then on branch
`claude/bot-interview-conversation-diagnosis-9c163b`). **Read its STATUS table first; do
not re-derive or re-plan.** This file only registers the plan and carries what the plan
does not.

## 0. Business decisions only the owner can make

Put these to Albert in ONE message before starting; none blocks Steps 1–9.

*A wrong guess is recoverable:*
1. **How long is one sitting?** The plan assumes The Oracle stops after 5 exchanges
   with one person and comes back no sooner than the next working day. Recommendation:
   keep 5. Affects only two settings (plan §8 O1). Asked 2026-11-18; unanswered.
2. **Who are the two volunteers** for the live trial after Albert's own chat (plan
   Step 11)? Recommendation: one English speaker and one Chinese speaker who have
   answered the bot before. Blocks only the last half of Step 11.

*Already settled — do NOT re-ask:*
- Serial, one message at a time; answer processed before the next message; each reply
  must use the answer (Albert, 2026-11-18).
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
- Committed and pushed on branch `claude/bot-interview-conversation-diagnosis-9c163b`
  with a PR into `main` containing only the plan, this file and one router line in
  `AGENTS.md`.

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

1. Ask Albert the two questions in §0 in one message. *Worked when:* answers are
   recorded on issue 604.
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
- Whether two workers can extract side by side safely (plan Step 4 test decides).
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
   two (sitting length, volunteers); the remaining "open" items are technical and are
   assigned to plan steps or #520.
