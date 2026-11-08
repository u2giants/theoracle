---
issue: none
status: OPEN
owner: mimo/ah-desktop-meeting-triage-plan
---

<!--
issue: none — this handoff REGISTERS an unimplemented plan
(plan_meeting_triage_pipeline.md). When implementation starts, open ONE tracking
issue for the need and keep `- [ ] live proof` on it until step 3.1's
docs/verification/meetings/live-proof.md exists (plan §13). Plan and handoff
link each other (required by the implementation-plan standard).
-->

# Handoff — meeting-transcript triage pipeline plan registered (2026-11-08)

Written 2026-11-08, 1:15 PM EST, ah-desktop, MiMo. The plan:
[plan_meeting_triage_pipeline.md](../plan_meeting_triage_pipeline.md) — **read
its STATUS table first; do not re-derive or re-plan.**

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

None blocking the plan. Two owner moments live inside it:

1. **Step 3.1 acceptance:** Albert reviews real rows on `/map/meetings` and
   clicks Ingest on one — that is the closing gate.
2. **O4 (later):** after two weeks of Phase 1 he decides whether ad-hoc "Meet
   Now" coverage (step 3.2) is worth building.

### Already settled — do NOT re-ask

- 2026-11-08, Albert, verbatim: *"unfortunately, i think you already have all of
  our documents."* — the document corpus is COMPLETE; corpus growth is meetings
  and Teams. Recorded on issue #255 comment 6725102695. Do not re-ask for
  document uploads.
- 2026-11-08, Albert, verbatim (the spec, his spelling preserved): *"automatically
  list every meeting transcript (using microsoft graph), then have scaledown.ai
  assess whether it's something that involves the company process or something
  that will assist in one of the system's data domains, then if so have scaledown
  create a 2-sentence summary of what's in that transcript and put them into a
  list on the Oracle website, then if i decide to ingest, remove the 'fluff' or
  useless text and inhest into The Brain"*.
- Standing rules that bind: questions on the Oracle site; login + `is_admin`
  only; reviews advice only; evidence quotes verbatim (cleaning is drop-only);
  every ingest is Albert-approved.

## 1. What this application is

The Oracle — POP Creations' evidence-backed company adviser (web
https://oracle.designflow.app on Vercel + `apps/brain` on Coolify as
oracle-brain; Supabase Postgres schema `cmap`; FalkorDB graph `company`). Full
glossary in the plan §2.

## 2. What we set out to do this session, and why

Answer "is recall.ai working?" with live evidence, then write the standalone
implementation plan for Albert's meeting-triage pipeline (his verbatim spec
above). Motivation: the documents are in; meetings are the corpus-growth path.

## 3. Current state — what is true right now

- `plan_meeting_triage_pipeline.md` is written on branch
  `docs/meeting-triage-plan`, 12 STATUS rows all ⬜ open (3.2 optional), self-
  audit preserved at the end (passed).
- Recall.ai verdict (live-proven 2026-11-08): API key valid (`GET /api/v1/bot/`
  200 — 7 bots, all 2026-06-08..23, 6 recorded, none since 2026-06-23); webhook
  secret configured (unsigned POST → 400 `invalid_signature`, not 503); the
  cmap ingest path has never fired (zero meeting transcripts in the 47-source
  live list). Built, healthy, unexercised under the current system.
- Microsoft Graph transcript functions exist in `apps/web/lib/microsoft-graph.ts`
  but have no product-code callers; no enumeration function exists yet (plan
  §5). No meeting has ever reached the Company Map.
- Plan §5 pins all of this with `file:line` at `main` @ `4db52531`.

## 4. Everything we tried that did NOT work

N/A (planning session; the Recall/Graph probes succeeded). Rejected approaches
are recorded in plan §7 so nobody retries them.

## 5. Root causes and key findings

Plan §6 (Graph feed never wired + Recall never triggered; enumerable scheduled
vs subscription-only ad-hoc; `/compress/raw/` is the summary tool and
classify-drop is the cleaning tool; notify-without-resource-data avoids the
certificate machinery).

## 6. Exact next steps

1. Implementer session starts at plan STATUS row **0.1** (prove Graph transcript
   access + wire `AZURE_*` into the brain env) and proceeds in order, phase by
   phase (re-read the plan at each phase boundary).
2. Before implementation edits: `ai-task-gates start --class code`; open ONE
   tracking issue for the need (plan §13) with `- [ ] live proof`.
3. Land each step as its own PR; update STATUS in the same PR; migrations via
   `python -m brain.migrate` (deploys do not apply them).
4. Do nothing from plan §4's out-of-scope list — especially auto-ingest (L1) and
   any transcript rewriting (L2).

You'll know each step worked when its §9 verification gate fires.

## 7. Constraints and gotchas in force

Plan §11 carries them all. Traps worth repeating: repo is PUBLIC (no real
meeting content in commits or screenshots); `cmap` migrations are The Oracle's
own (never shared-db); Coolify deploys silently run old code unless
`BRAIN_IMAGE_TAG` is PATCHed first; the Graph transcript resource is
preview/beta (retry beta on 4xx); cleaning may only drop, never rewrite.

## 8. Access and environment

Plan §12 (machines, gh identity `u2giants`, 1Password `vibe_coding` items by
title — "recall.ai API key" field `credential`, "Designflow - Azure Graph client
secret (AZURE_CLIENT_SECRET)", DB field `oracle_session_pooler`; brain API
headers `x-brain-token` + `x-user-id`; Graph diagnostic scripts in `scripts/`).

## 9. Open questions and risks

Plan §13 + §8 O1–O5 (summary language, chatter threshold, sweep lookback,
whether 3.2 subscriptions run, collapsed section). Risks: Graph preview drift,
triage misclassification (mitigated by listing everything), cleaning
over-dropping (raw preserved), sensitive meetings on an admin-only list.
