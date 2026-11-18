---
issue: 607
status: OPEN
owner: claude/oracle-test-data-10bac2
---

# Handoff — project-manager message intake: plan written, nothing built (2026-11-18)

Tracking issue: [u2giants/theoracle#607](https://github.com/u2giants/theoracle/issues/607). Parent programme: [#520](https://github.com/u2giants/theoracle/issues/520).
The plan is the brief: [plan_pm_message_intake.md](../plan_pm_message_intake.md)
([GitHub](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md)). Read its STATUS table first; do not re-derive or re-plan.

## 0. Business decisions only the owner can make

Put all of these to Albert in **one** message before starting work.

**Blocking (one part of the work only):**
1. **May The Oracle read the two project managers' mailboxes?** Recommendation: yes, limited to those two mailboxes. Until he answers, email stays out; Teams chats and ClickUp go ahead without it. Blocks plan step 5.1 only.

**A wrong guess is recoverable:**
2. **Should private one-to-one chats be read, or only group chats? And should the two managers be told first?** Recommendation: tell them, then include one-to-one chats. The plan's default is "included, not announced by the system"; if he says group chats only, it is a one-line restriction (plan §8, O4) and already-loaded one-to-one threads are deleted by origin.
3. **How far back?** Assumed: the last 90 days, after a two-week pilot. Recommendation: keep. Widen only if the picture is still thin.

**Not part of this work and nobody is on it:** none found.

**Update 2026-11-18 (owner answered):** questions 1 and 2 are settled — mailboxes yes, one-to-one and group chats yes, ClickUp yes, and no frontier model anywhere in the pipeline (plan L9, L10). The only part of question 2 still open is whether the two managers are told first. Step 5.1 is now blocked only on the mailbox permission (technical, `Blocked —` on #607).

**Already settled — do NOT re-ask:**
- 2026-11-18: who — the two project managers; what — email, Teams messages, ClickUp; method — ScaleDown first, then the cheapest of his four named models that passes (plan STATUS quotes him verbatim).
- 2026-11-16: "we need to collect WAY more information".
- The interview bot stays off (#518).

Technical items (mailbox permission needs tenant admin consent; no tenant-admin credential is reachable by AI) are `Blocked —` on #607, not an ask for the owner beyond question 1.

## 1. What this application is

The Oracle is POP Creations' evidence-backed company adviser: it reads company sources, builds a Company Map of who does what and how work flows, answers questions with sources, and interviews employees over Teams. Repo [u2giants/theoracle](https://github.com/u2giants/theoracle) (**public**). Python brain in [apps/brain](https://github.com/u2giants/theoracle/tree/main/apps/brain) on Coolify; Next.js web in [apps/web](https://github.com/u2giants/theoracle/tree/main/apps/web) on Vercel; Supabase Postgres schema `cmap`; FalkorDB graph. Full description: plan §2.

## 2. What this session set out to do, and why

Albert said the brain has too little good data to judge the questions it asks employees. He chose the two project managers as the people to learn from, and said their email, Teams messages and ClickUp data would be very expensive to process with a large model; he asked for a design that uses ScaleDown first and then the cheapest of four named models, "impeccable job with the least amount of cost". This session's job: evaluate, design, write the plan. Not build.

## 3. Current state — what is true right now

- **Done and verifiable:** the ScaleDown evaluation ([docs/company-map/scaledown-report-2026-11-18.md](https://github.com/u2giants/theoracle/blob/main/docs/company-map/scaledown-report-2026-11-18.md)); access probes (results on #607 and in plan STATUS row A); the plan; this handoff; the router pointer in [AGENTS.md](https://github.com/u2giants/theoracle/blob/main/AGENTS.md).
- **Not started:** every plan step from 0.1 on. No code, schema, env var or seat was changed. No paid model call was made. No message content was read — probes requested counts and status codes only.
- **Committed / pushed:** via the docs PR linked from #607 (branch `docs/pm-message-intake-plan`). Nothing deployed; nothing to deploy.

## 4. Everything tried that did NOT work

- **ScaleDown plugin tool server** would not start in the session ("Connection closed", package-cache error on that machine). Worked around by running the already-installed copy of the same tool directly. The session's connection itself was not repaired; a fresh session may connect normally.
- **ClickUp probe returned 400/401** at first: the vault item's field named `credential` is empty. The working key is in the field labelled `api token`.
- **Mail read returned 403** (`ErrorAccessDenied`) for both managers: the Entra app has no `Mail.Read` application role. Not worked around.
- **`ai-task-gates` signature helper** (`ai-gh-signature`) is absent on this machine and `$AI_GH_SIGNATURE` was unset; posts were signed by hand in the same format as earlier posts.
- Design dead ends are in plan §7 (eight rejected approaches with reasons).

## 5. Root causes and key findings

- Cost is driven by one chat call per passage in two stages plus one date call per source: [relations.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py), [flat.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/flat.py), [dates.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/read/dates.py).
- Evidence must be verbatim, so summaries and compression can only triage, never feed extraction.
- The transcript reader ([transcript.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/read/transcript.py)) is reused, but only through its JSON turn list (speaker lines cannot carry timestamps), and short messages must be packed into full passages. Transcript sources make no date call. Both corrections came from the Muse second opinion on 2026-11-18 and are in the plan (steps 1.5, 1.6, 2.1, 2.3, 2.4).
- No batch path exists; all chat goes through OpenRouter, which gives no batch discount.
- Teams chat read and ClickUp read already work with existing credentials. Channel posts and email do not.
- Three other vault items mention ClickUp ("ClickUp MCP Server - official remote setup", "clickup.com for ai", "Cloudflare D1 API - ClickUp monitoring data (The Oracle)"). They were **not** opened. Before building the collector (plan step 1.2), check whether the last one means ClickUp data is already being collected somewhere and reuse it if so.

## 6. Exact next steps

1. Put the §0 questions to Albert in one message. *Worked when:* his answers are recorded on #607.
2. Start a lead session with the launch prompt at the end of the plan. *Worked when:* plan step 0.1's forecast (counts and dollars) is on #607.
3. Follow the plan's STATUS table in order; update it in each PR. *Worked when:* every row but 5.1 is done with an artifact.
4. When the mailbox permission exists, do step 5.1.
5. When #607 closes, delete this file under the successor rule and fix the AGENTS.md pointer in the same commit.

## 7. Constraints and gotchas

Plan §11 lists them. The ones most likely to bite: public repo (no message content, names, ids or addresses anywhere in git, issues, PRs or logs); no paid call before the forecast; cleaning is drop-only; the bot stays off; never push to `main`; wait on checks with `gh pr checks --watch` if `ai-pr-wait` crashes.

## 8. Access and environment

Plan §12. `gh` is authenticated as the owner's personal identity. Secrets are in 1Password vault `vibe_coding` (item titles in the plan; never values). In this session the Supabase, Trigger and Recall tool connections were down and Vercel needed sign-in; none was needed for planning, but the build will need Supabase.

## 9. Open questions and risks

- Volume is unknown until step 0.1; the 90-day default (2026-11-18) may change with it.
- ScaleDown summarize may not be enabled on the account (plan step 1.5 has the fallback).
- Whether any of the four named models passes the relations gate on chat-shaped text is unproven; the plan says what to do if none does.
- Privacy of one-to-one chats — §0 question 2.
- Decisions dated 2026-11-18 are in plan §8 (locked L1–L8, open O1–O4).

## Self-audit

All ten sections present; §0 sweep run over the plan and this file (three owner items, each with a recommendation; settled list included); a newcomer can continue from the plan's launch prompt without asking; dead ends and unopened leads are written down; file references are GitHub URLs; no secret values.
