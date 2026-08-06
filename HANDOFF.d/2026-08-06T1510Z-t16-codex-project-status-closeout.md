# Oracle project status closeout

Created: 2026-08-06 15:10 UTC on machine `t16` by Codex.
Workstream status: OPEN because the macro-first redesign and several owner-gated checks remain.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
use it to ask company questions and upload documents; administrators review claims, gaps,
translations, workflow maps, model behavior, and quality results. The system extracts statements
with exact source evidence and is being expanded into a durable model of company processes,
responsibilities, systems, decisions, exceptions, and changes.

The code is the `u2giants/theoracle` TypeScript/pnpm monorepo at `C:\repos\oracle`, branch `main`.
The Next.js application runs at `https://oracle.designflow.app`; Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn` runs workers; Supabase project `eqccjfbyrywsqkxxpjvg` stores production
data and authentication. `MACRO_FIRST_IMPLEMENTATION_PLAN.md` is the architectural plan of record.
The complete pre-2026-08-06 operational history was preserved verbatim in
`HANDOFF.d/2026-08-06T1510Z-t16-codex-legacy-migrated-handoff.md`.

## 2. What we set out to do this session, and why

This session resumed an older request to run a real Pop-style workflow verification and then
answered where the entire Oracle project stands. The purpose was to distinguish the retired
2026-07-04 outline/macro harness from the current macro-first reader, establish which production
claims are supported by durable evidence, and identify the actual next decision rather than
restarting obsolete work.

No product code, production data, infrastructure, model setting, or deployment was changed in this
session. Closeout only migrated the legacy root handoff to the concurrency-safe `HANDOFF.d/`
layout and recorded this current status.

## 3. Current state - what is true right now

Production is operational. The web release recorded by the current project handoff is `a7637f7`,
with GitHub Actions run `30445659590` green. Later commits through current repository HEAD
`6cd634f24655c205b353a2794b397420b2747b39` are documentation/tooling closeout work. At closeout,
local `main` matched `origin/main` and the tree was clean before these handoff-only edits.

The canonical Pop swimlane fixture is document `9d09fa89-3a46-465e-a98b-837287c9e22a`, file
`Pop Creations Flow 12112025 (1).png`. The current workflow-reader gate passed in production:
active map `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8` contains 63 nodes, 71 edges, 14 lanes, and one
path; it recovered 9/9 expected stage groups and retained 149/149 emitted elements. Evidence and
run IDs are in `evals/macro-first-battery.md` under the 2026-07-07 Stage 2 gate. The obsolete
`workflowTrace`/outline/macro/coverage harness was retired by the macro-first redesign and must not
be rerun.

The macro-first program is incomplete. `MACRO_FIRST_IMPLEMENTATION_PLAN.md` records R0, R0.1, and
R1 as production-verified. R2's released deeper responsibility reader scored 12/30 against the
frozen 27/30 acceptance threshold in Trigger run `run_06fqnh151dmai294bc2uble701`, map
`193376a7-848e-48e8-b5ec-8cca51285b3f`. Merge/apply remain deliberately disabled and R3-R10 are
blocked. The exact R2 state and controls are in `plan_r2_deeper_responsibility_architecture.md`.

Outside macro work, most audited product/reliability items are released. Remaining items are:
REL-2 needs an owner-authorized ERR-005 contradiction fixture; REL-6 needs an approved
non-sensitive image; REL-7 release automation waits on REL-2; REL-8 waits for macro R10. GAP-1
awaits its first natural approved taxonomy apply; GAP-2 remains off because 2,963 ms p95 exceeds
the 2,500 ms gate; GAP-3 needs an Authentik product decision; GAP-4 needs five independently
labeled Chinese positive examples plus one negative control; GAP-6 and GAP-9 require explicit
owner approval. The three canonical status tables are
`plan_repo_reliability_and_release_gaps.md`, `plan_deferred_product_and_infrastructure_gaps.md`,
and `MACRO_FIRST_IMPLEMENTATION_PLAN.md`.

## 4. Everything we tried that did not work

The earlier session spawned a verification sub-agent for the retired Pop workflow harness. The
attempted Trigger `source-outline` dispatch aborted before it ran, so it provided no live proof.
When this session checked that agent (`019f2f6d-bc45-7941-9c9f-17e2cc9a061e`), it no longer
existed. Do not cite that agent or aborted dispatch as successful verification.

The old planned query expected the pre-Stage-3 `source_workflow_maps` shape and candidate
`workflowTrace` links. Current source and handoff history show that path was intentionally retired;
restarting it would test deleted ownership rather than the production architecture. The valid
replacement evidence is the 2026-07-07 workflow-reader gate and subsequent R0/R0.1 production
replays.

The R2 deeper-reader architecture itself did not meet its goal. Although its deterministic
inventory/repair controls passed local and CI checks, the single authorized production gate scored
12/30. It was not a token or cost exhaustion failure: the preceding evidence used only a fraction
of the available budget. The hard stop correctly prevented a second gate and any business-model
merge/apply.

## 5. Root causes and key findings

The original Pop failure was structural: image transcription and atomic extraction fragmented one
workflow into disconnected claims. The current source-workflow reader fixes that class by capturing
the graph once and validating exact evidence; see `evals/macro-first-battery.md` and
`MACRO_FIRST_IMPLEMENTATION_PLAN.md` sections 1 and R0.

Passing the process-diagram fixture does not prove general business understanding. The present
bottleneck is responsibility documents: strict field completeness and repair still fail to retain
enough correct owner/action/target/system/timing/direction records. The frozen production result is
12/30, so later durable business-model stages cannot safely proceed.

The project documentation has two time layers. `fix_enhancement.md` is diagnosis/history and its
old section 6.9 is not a current task list. Current authority is the status table at the top of
`MACRO_FIRST_IMPLEMENTATION_PLAN.md`, then the focused R2/reliability/deferred-gap plans. The
legacy handoff is valuable evidence but its older next-action blocks are historical.

## 6. Exact next steps

1. Read `MACRO_FIRST_IMPLEMENTATION_PLAN.md` and
   `plan_r2_deeper_responsibility_architecture.md`; preserve the frozen fixture, answer key,
   `field-aware-v3` scorer, 27/30 threshold, budgets, and disabled merge/apply controls. You will
   know this gate is respected when no production run or code change occurs before Albert selects
   one of the two recorded R2 paths.
2. Ask Albert to choose between the bounded model bake-off and another deeper-architecture step.
   Recommend the bounded model bake-off because the latest architecture gate scored 12/30 without
   exhausting its budget. You will know the decision is complete when it is dated in the R2 plan
   and one path has explicit scope and stop conditions.
3. If Albert selects the bake-off, follow `MODEL_BAKEOFF_SPEC.md` exactly and run only the bounded,
   qualified model comparison authorized there. Do not change the scorer or prompt to fit the
   answer key. You will know it worked when a candidate reaches at least 27/30 under the frozen
   gate and the run/model/map/cost evidence is appended to `evals/r2-responsibilities.md`.
4. Only after R2 passes, advance R3 in the canonical macro plan. Keep business-model merge/apply
   disabled until that stage's own gate authorizes it. You will know the transition is valid when
   R2 is marked done with production evidence and R3's entry conditions all pass.
5. Independently close owner-gated reliability work only with explicit authorization: obtain a
   contradiction fixture for ERR-005 and a non-sensitive image for REL-6. You will know each is
   complete when its canonical status row cites the production run and expected evidence.
6. Observe, but do not manufacture, the remaining product gates: first natural taxonomy apply,
   faster GAP-2 rerun, five Chinese labels plus negative control, and owner decisions for Authentik,
   Vertex storage, and secret rotation. You will know each is complete only when its frozen status
   gate passes and the corresponding canonical plan is updated.

## 7. Constraints and gotchas in force

Use `main` only for this repository. GitHub is source of truth; database changes use the journaled
`pnpm db:migrate` path and worker changes deploy through Trigger.dev. Do not mutate production or
shared cloud resources without the exact owner authorization required by the standing rules.

Preserve exact quote evidence, immutable/superseding workflow maps, frozen R2 evaluation controls,
and disabled macro merge/apply. Do not revive deleted source-outline, lens, macro-relationship, or
coverage writers. Do not treat `fix_enhancement.md` as the forward implementation sequence.

Handoffs are now concurrency-safe. Root `HANDOFF.md` is a static pointer. Each session creates its
own timestamped file under `HANDOFF.d/` and never edits another session's file. Presence means an
open workstream; deletion after verified completion is the archive mechanism. Do not add a shared
index or `.gitattributes merge=union` rule.

All commits must be authored and committed as
`Albert Hazan <u2giants@users.noreply.github.com>`. Never expose secret values in logs, handoffs,
commits, or chat.

## 8. Access and environment

Local checkout: `C:\repos\oracle`, branch `main`, Windows PowerShell on machine `t16`. Production
web: `https://oracle.designflow.app`. Supabase project: `eqccjfbyrywsqkxxpjvg`. Trigger.dev project:
`proj_wgpzsvhmsopqhvwqaycn`. Vercel project: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.

The machine has authenticated GitHub tooling and connected Trigger.dev/Vercel/Supabase tooling as
documented in `AGENTS.md` and the legacy handoff. Durable credentials belong in 1Password vault
`vibe_coding`; use item names documented by the project and never copy values into repository
files. Production database access uses the current N. Virginia project, not the retired Ohio
project.

## 9. Open questions and risks

- 2026-08-06: Albert has not selected the next R2 path. Continuing automatically would violate the
  production hard stop.
- 2026-08-06: The recommended bounded model bake-off may show that model choice is not sufficient;
  retain the frozen scorer so a low result remains honest evidence for another architecture step.
- 2026-08-06: The application is operational, but it is not yet the finished enterprise business
  brain. R3-R10, including durable merge/review/serving and cleanup, remain blocked by R2.
- 2026-08-06: GAP-2's quality is promising but enabling it before its latency gate passes would
  knowingly degrade chat responsiveness.
- 2026-08-06: Chinese retrieval, contradiction handling, and image ingestion lack representative
  live samples; absence of a fixture is not evidence of success or failure.
- 2026-08-06: The migrated legacy handoff remains an open file because it contains unresolved
  workstreams. A future closeout should delete it only after every plan it routes to is proven
  complete or intentionally rejected.

## Self-audit

1. **Yes, a brand-new developer can continue without this chat.** Sections 1-3 define the product,
   runtimes, authoritative plans, deployed evidence, current commit, completed Pop gate, failed R2
   gate, and every remaining workstream. Sections 6 and 8 provide ordered actions and access.
2. **Yes, the handoff preserves all session knowledge needed to continue as effectively as this
   session.** Section 4 records the aborted sub-agent/Trigger dead end and retired harness; section
   5 records the structural diagnosis, current bottleneck, and document-authority hierarchy.
3. **Yes, every execution-critical dimension is covered.** Background and goals are in sections
   1-2; state and evidence in section 3; failures in section 4; findings in section 5; gated next
   actions in section 6; constraints in section 7; access without secret values in section 8; and
   dated decisions/risks in section 9. No gap was found on the final reread.
