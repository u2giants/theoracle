---
issue: none
status: OPEN
owner: mimo/ah-desktop-chinese-plan
---

<!--
issue: none — this handoff REGISTERS an unimplemented plan (plan_chinese_integration.md).
When implementation starts, open one tracking issue for the Chinese integration
need and move this handoff's checklist there; do not open issues from here
preemptively. Plan and handoff link each other (required by the
implementation-plan standard).
-->

# Handoff — Chinese (Mandarin) integration plan registered (2026-11-08)

Written 2026-11-08, 12:25 PM EST, ah-desktop, MiMo. The plan:
[plan_chinese_integration.md](../plan_chinese_integration.md) — **read its STATUS
table first; do not re-derive or re-plan.**

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

None blocking the plan itself — the plan is complete and self-audited. When the
work lands, two owner moments remain (both already inside the plan's steps):

1. **Step 2.3/4.2:** pick the China-office acceptance reader (plan suggests
   Emma Li as the obvious candidate; the choice is Albert's).
2. **Step 4.2 acceptance:** the chosen reader does the 10-minute Chinese Map +
   chat pass and marks what is wrong.

### Already settled — do NOT re-ask

- 2026-11-08, Albert, verbatim: "can this system understand and speak chinese
  (to our china employees)?" — the need is China (Ningbo) employees served in
  Mandarin; this plan is the authorized answer to it.
- Standing rules that bind: questions go on the Oracle site (eval questions are
  approved on the site's eval page, never as chat files); @popcre.com work
  emails; every M365 tenant employee can reach the Oracle over Teams; login +
  `is_admin` only; FalkorDB stays; reviews are advice only; one brain (no
  separate Chinese map); quotes never translated; UI chrome stays English.

## 1. What this application is

The Oracle — POP Creations' evidence-backed company adviser (web
https://oracle.designflow.app on Vercel + `apps/brain` on Coolify as
oracle-brain; Supabase Postgres schema `cmap`; FalkorDB graph `company`). Full
glossary in the plan §2.

## 2. What we set out to do this session, and why

Answer Albert's three China/data questions, then — on his explicit request —
write a standalone implementation plan for Chinese integration using the
implementation-plan-writer standard. The session also assessed his meeting-
transcript triage sketch (Graph listing → ScaleDown relevance → summary list →
approve → de-fluff → ingest): feasible, most plumbing exists (Graph transcript
functions in `apps/web/lib/microsoft-graph.ts`, Recall.ai ingest path,
ScaleDown /classify + /compress), missing work is the staging queue, review
list, approve button and cleaning pass — NOT planned here (out of scope, plan
§4; separate plan if he asks).

## 3. Current state — what is true right now

- `plan_chinese_integration.md` is written on branch
  `docs/chinese-integration-plan`, 14 STATUS rows all ⬜ open, self-audit
  preserved at the end (passed).
- Everything the plan claims about current code was verified live this session
  against `main` @ `8b58e174` (plan §5 has every `file:line`).
- No implementation code exists for Chinese; the zh-CN locale column/admin
  dropdown exist but nothing reads them (plan §5).

## 4. Everything we tried that did NOT work

N/A (planning session, no implementation attempts). Approach rejections are
recorded in plan §7 so nobody retries them.

## 5. Root causes and key findings

Eight findings with evidence live in plan §6 (ASCII-era text utilities destroy
CJK input; speaker regex misses full-width colons; sentence splitter has no CJK
branch; prompts demand English; English morphology in name normalization; no
cross-lingual identity; locale is a dead wire; china_imp.md is prior art for a
retired system).

## 6. Exact next steps

1. Implementer session starts at plan STATUS row **0.1** and proceeds in order,
   phase by phase (re-read the plan at each phase boundary).
2. Before implementation edits: `ai-task-gates start --class code`; open ONE
   tracking issue for the need and keep `- [ ] live proof` on it until step
   4.2's `docs/verification/chinese/live-proof.md` exists.
3. Land each step as its own PR (branch off `main`); update STATUS in the same
   PR; migrate with `python -m brain.migrate` explicitly (deploys do not).
4. Do nothing from plan §4's out-of-scope list — especially the meeting-triage
   pipeline and the Company Map step-14 owner gates.

You'll know each step worked when its §9 verification gate fires.

## 7. Constraints and gotchas in force

Plan §11 carries them all. The traps worth repeating here: the repo is PUBLIC;
`cmap` is The Oracle's own database (never route these migrations through
popcre/shared-db); a Coolify deploy silently runs old code unless
`BRAIN_IMAGE_TAG` is PATCHed first; quotes are evidence and must round-trip
byte-for-byte.

## 8. Access and environment

Plan §12 (machines, gh identity as `u2giants`, 1Password `vibe_coding` items by
title only — `oracle_session_pooler` field is the working DB URL, brain API
headers `x-brain-token` + `x-user-id`, local test/migrate commands).

## 9. Open questions and risks

Plan §13 (ScaleDown Chinese quality unknown — measured at step 1.1 with the
frontier fallback as mitigation; cross-lingual false-merge risk; CJK token cost;
O1–O4 open decisions with criteria).
