---
issue: 520
status: OPEN
owner: claude/oracle-code-audit-c1b3b1
---

# Handoff — Oracle audit done, repair and consultant-upgrade plan written, nothing built yet (2026-11-11)

Written 2026-11-11, 7:50 AM EST, edge-dev3, Claude (Fable 5.2).
Plan (read its STATUS table first; do not re-derive or re-plan):
[plan_oracle_repair_and_consultant_upgrade.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_repair_and_consultant_upgrade.md).
Evidence: [docs/audit-2026-11-11-oracle-goals.md](https://github.com/u2giants/theoracle/blob/main/docs/audit-2026-11-11-oracle-goals.md).
Program issue: https://github.com/u2giants/theoracle/issues/520.

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Put this whole list to Albert in ONE message before starting. Every item has a default, so only the last one blocks anything.

**A wrong guess is recoverable (work proceeds on the default):**
- **The list of business functions the Oracle sorts knowledge into** (plan step C1). Recommendation: accept the 13 proposed in the plan and let him rename or merge them on the site.
- **Who is on the licensing team** (carried from issue #474). Recommendation: let the Oracle derive it from the staff directory and documents; he corrects it on the site.
- **Who receives the Monday briefing** (step I4). Recommendation: Albert only.
- **How old a fact must be before it is marked "possibly out of date"** (step D4). Recommendation: 18 months for who-does-what, 36 months for rules.
- **Approve the test questions on the Oracle site's eval page** (step B1). Recommendation: approve the drafts as written.

**Blocks one step (J1 only):**
- **Which business numbers the Oracle should read first, and from which system.** Recommendation: order-to-ship lead times and late shipments.

**Already settled — do NOT re-ask:**
- 2026-10-27: no per-fact approval, no permissions beyond login + admin, the graph database stays, nothing fed in is secret.
- 2026-10-30: the conversation model is the Claude model; heavy work uses a cheaper one.
- 2026-11-10: the weekly interview question quota stays on; eval questions are approved on the site, never as chat files.
- 2026-11-11: knowledge is segmented by part/function of the company so unrelated material stays out of an answer.
- The document corpus is complete per the owner; meeting transcripts grow through the meeting-triage plan.
- The interview bot stays off until issue https://github.com/u2giants/theoracle/issues/518 says otherwise.

## 1. What this application is

**The Oracle** — POP Creations' company adviser. It reads company documents, diagrams and meeting transcripts, interviews employees over Microsoft Teams, builds a Company Map of how work flows, answers questions with sources, and recommends changes. Web: https://oracle.designflow.app (Vercel, `apps/web`). Brain: https://oracle-brain.designflow.app (Coolify service `oracle-brain`, Python, `apps/brain`). Repo https://github.com/u2giants/theoracle (public). Data: the Oracle's own Supabase project, schema `cmap`; FalkorDB graph `company` is rebuilt from it.

## 2. What we set out to do this session, and why

Albert asked for an audit of the code against seven goals (learn from documents; learn from interviews; know what to ask; segment into data domains; relationships between processes; the big picture; anything else an all-knowing consultant should do), then asked: "write up a plan to fix everything and also think of improvements that i didn't even think of and include those".

## 3. Current state — what is true right now

- Audit complete and written to the audit file above. Verdict: not perfect; self-test 0.38 against a 0.6 target; data domains unused when answering; three goals met only on paper.
- Plan written: 10 phases (A–J), 51 steps, every row ⬜ open. **No code has been changed.** Nothing deployed.
- This PR adds only: the plan, the audit, this handoff, and router links in `AGENTS.md`, `docs/agents/03-documentation-map.md`, `docs/agents/15-pending-work.md`.
- Live data read 2026-11-11 7:36 AM EST: 57 sources (12 documents, 45 transcripts), 303 passages, 2,070 things (1,790 in one source only), 2,311 relationships; 1,178 area and 23 company summaries stored where the current map has 32 and 1; 7 failed jobs; 10,074 dismissed questions; interview bot off; no source has a date.

## 4. Everything we tried that did NOT work

Nothing was attempted in code. Dead ends inherited from earlier sessions and recorded in the plan §7 so they are not repeated: removing the weekly question cap (flooded staff on 2026-11-10); two model bake-offs (structure, not model strength, limits quality); whole-document prompts (Oracle 2, could not scale); atomic-claim approval (Oracle 1, never saw the whole). During the audit, two live queries failed on wrong names — the relationship table is `cmap.relation` (not `edge`) and the entity type column is `entity_type`.

## 5. Root causes and key findings

Full table with file:line in plan §5–§6. The seven that matter most:
1. Company-wide answers load every past summary — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/answer/answer.py#L725-L731 has no version filter and summaries are never deleted. Confirmed in live data.
2. One failed model call discards a source's whole extraction while it still shows as read; failed jobs never retry — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/extract/flat.py#L435-L451 and https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/worker.py#L87-L99.
3. The passage splitter drops text — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/read/chunk.py#L60-L70 (demonstrated by running it).
4. Answering never consults domains — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/answer/answer.py#L410-L451.
5. Relationships must sit inside one passage — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/extract/relations.py#L247-L250.
6. Interview questions come only from a by-product of summary writing — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/graph/communities.py#L766.
7. Review flags are read by nothing — https://github.com/u2giants/theoracle/blob/3c7e2e39/apps/brain/brain/api/flags.py.
Items the audit marked inferred (not reproduced): Office files with links/charts rejected; a question posted into a group chat; deleting an interview-answer source raising a database error. Each step that fixes one starts by reproducing it in a test.

## 6. Exact next steps

1. Present §0 to Albert in one message. You'll know it worked when his answers are recorded in the plan's §13.
2. Open the plan, start at step A1 (first ⬜ row). You'll know A1 worked when `test_global_ignores_superseded_reports` passes and the live count of stored summaries is about one build's worth.
3. Continue A2–A7, then A8 (re-read everything, record the baseline score in `docs/verification/repair/A8-baseline.md`). You'll know Phase A worked when no source shows as read with nothing extracted, no jobs are failed, and the new score is recorded.
4. Start a fresh session after A8 (plan cut point), then Phase B, then C–J per the STATUS table's "needs" column.
5. Tick the phase on issue #520 only with a live-proof artifact.

## 7. Constraints and gotchas in force

All in plan §11. The ones most likely to bite: `cmap` schema changes are new idempotent files under `apps/brain/brain/sql/` (next number 016), not `shared-db`; no model ids in code; never push to `main`; the bot stays off; the repo is public; production state changes only through the deployed app's own actions; do not weaken quote validation, the weekly cap, or any guard to pass a test.

## 8. Access and environment

Plan §12. `gh` as `u2giants`; Supabase MCP server `supabase-oracle` for read-only SQL; secrets in 1Password vault `vibe_coding` (locations only); local stack via `apps/brain/compose.dev.yaml`.

## 9. Open questions and risks

- Unknown until measured: whether Phase A alone lifts the score to 0.6 (2026-11-11).
- How a reused summary's version number is stamped was not verified; step A1 tells the implementer to confirm before filtering (2026-11-11).
- The plan is large; it is cut into phases with fresh-session cut points after A8, C5, E5, F6 and H5.
- The successor that finishes step A8 retires this file under the successor rule (the plan's STATUS table is the durable record).

## Self-audit

1. Newcomer can pick up without a question: yes — §1, §3, §6 plus the plan. 2. As effectively as the author: yes — every finding is in the audit and plan §5 with file:line; inferred items are labelled in §5 here. 3. Every detail for flawless execution: yes — goals §2, state §3, failures §4, decisions §0, constraints §7, risks §9, next steps with gates §6. 4. §0 sweep: walked §1–§9; the owner-judgement items are the six in §0 (functions list, licensing team, briefing recipients, staleness age, eval-question approval, first numbers); no technical approval is asked of him.
