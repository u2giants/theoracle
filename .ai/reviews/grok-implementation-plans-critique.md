# Oracle Implementation Plans — Independent Read-Only Critique

Review mode: read-only. No files edited, no shell, no secrets, no production mutations.
Workspace: `C:\repos\oracle`. Plans and code claims checked against the tree as present. Commit pin `609f217…` was not shell-verified.

---

## 1. Verdict

**ready after corrections**

Macro R0.1 and the R1 read-only audit are implementable. Reliability REL-2 / REL-3 and parts of GAP-1 are **not** executable as written because they target deleted workers or misstate current code. Fix those plan rows before a session starts them. Do not redesign the whole plan set.

---

## 2. Blocking corrections

### B1. REL-2 targets deleted workers and an obsolete architecture

- **Plan/file:** `plan_repo_reliability_and_release_gaps.md` §REL-2; `AGENT_ERROR_LOG.md` ERR-003 / ERR-004
- **Evidence:**
  - `apps/workers/src/trigger/` has no `source-outline.ts`, `document-lens-extraction.ts`, `macro-relationship-extraction.ts`, or `source-coverage-audit.ts`.
  - `AGENTS.md` states those writers were deleted in macro-first Stage 3.
  - Migration `89_map_directed_extraction_cleanup.sql` deletes lens/outline settings.
  - Current path is `generateSourceWorkflowMap` + `mapElementRef` in `document-ingestion.ts`, not outline → lens → macro → coverage.
  - `workflowTrace` / edge-trace candidate paths are not present in current `document-ingestion.ts`.
- **Correction:** Rewrite REL-2 around current code:
  - Close ERR-003 as **FIXED by deletion of lens fan-out**, with evidence that those tasks no longer exist and settings were removed.
  - Restate ERR-004 as map-directed ingestion proof: non-empty `source_workflow_maps`, map guidance, `mapElementRef` membership, coverage gaps via `map-coverage-gaps.ts` — not “deterministic macro rows from outline.”
  - Keep ERR-005 as a document-only contradiction rerun on `contradiction-watcher.ts` (channel insert only when `channelCtx` exists — still valid).
- **Why blocking:** A fresh session will fail searching for missing files, waste time “proving” dead paths, or rebuild deleted architecture.

### B2. REL-3 points at query builders that no longer live in workers

- **Plan/file:** REL-3; REL file map rows for `macro-relationship-extraction` / `source-coverage-audit`
- **Evidence:** No such trigger files. Support SQL smoke still exists as `packages/db/src/verify-macro-support-queries.ts` (`pnpm --filter @oracle/db verify:macro-support-queries`).
- **Correction:** Retarget REL-3 to that script (or extract shared query helpers if still needed). Or mark ERR-002 regression **done / N/A for deleted writers** after proving the smoke is wired into CI if still desired.
- **Why blocking:** “Extract builders from deleted files” cannot run.

### B3. R2 entry criteria omit R0.1 while status table requires it

- **Plan/file:** `MACRO_FIRST_IMPLEMENTATION_PLAN.md` status table vs §R2 Entry
- **Evidence:** Status: “R2 blocked on R0.1 and R1.” R2 Entry: “R0 and R1 green” only. §18 and R0.1 correctly require R0.1 before R2.
- **Correction:** R2 Entry must say: **R0, R0.1, and R1 green.**
- **Why blocking:** A session reading only R2 can start the next reader without quote-repair proof and multiply the copy defect.

### B4. HANDOFF mid-document “next action” contradicts the registry and top next steps

- **Plan/file:** `HANDOFF.md` “CANONICAL PLAN UPDATE — 2026-07-21” vs top “Exact next steps” and macro §18
- **Evidence:** Mid block says next action is only R1 audit and does not name R0.1. Top and macro plan say R0.1 ∥ R1 audit, R0.1 before R2. Brief says top wins, but agents often scan “LATEST” / “CANONICAL” blocks.
- **Correction:** Stamp mid blocks with **historical / superseded**; single next-action list = R0.1 + R1 audit only.
- **Why blocking:** Sessions can skip R0.1 or invent order.

### B5. GAP-1 misstates current taxonomy apply path

- **Plan/file:** GAP-1; `apps/web/app/admin/taxonomy/_actions.ts`; `apps/workers/src/trigger/taxonomy-reclassification.ts`
- **Evidence:**
  - Worker `taxonomy-reclassification` already exists with apply/skip handlers.
  - Approve path marks proposal `approved`, logs `approve_pending_reclassification_*`, and **never** `tasks.trigger('taxonomy-reclassification')`.
  - Splits intentionally skip as manual.
- **Correction:** Rewrite GAP-1 as: audit existing worker + change-log contract; wire approve (or explicit admin “Apply”) to trigger; UI state `approved` vs `applied` / `skipped`; finish incomplete types; tests for idempotency. Do not “add a new task from zero.”
- **Why blocking:** Greenfield rewrite risks dual workers or breaking a partial path.

---

## 3. Important non-blocking corrections

### N1. Macro §3.4 still describes the pre-R0 “101 drops / missing diagnostics” state

- **Evidence:** R0 is marked done; production map `a2f38158-…` has 2 roots + cascades; evals record R0.
- **Edit:** Mark §3.4 historical; point quality residual to R0.1 (2 root copy failures).

### N2. HANDOFF registry omits GAP-14

- **Evidence:** Product plan has GAP-14; registry stops at GAP-13.
- **Edit:** Add GAP-14 docs closure row.

### N3. Product plan definition of done says GAP-1–11 only

- **Evidence:** Status table includes GAP-12–14.
- **Edit:** Done = GAP-1 through GAP-14.

### N4. `china_imp.md` still claims “not yet implemented”

- **Evidence:** Header: “Draft / proposal — not yet implemented” (2026-06-16). AGENTS/HANDOFF: Phase 1 live (schema, translation worker, locale retrieval).
- **Edit:** Status banner = Phase 1 live; remaining = GAP-4. Ownership: REL-1 docs or GAP-4 entry.

### N5. `docs/macro-understanding-implementation-plan.md` still describes live outline/lens writers

- **Evidence:** Body describes workers deleted by Stage 3; HANDOFF correctly marks file historical.
- **Edit:** Stronger dead banner at top; no “remaining work is quality tuning” as current.

### N6. REL-1 Teams/lull claims are correct; file headers still wrong

- **Evidence:** Teams header still TODOs email + meeting-time; code implements email resolve + `payload.meetingTime`. Lull header says presence hard-coded false; code uses `typing_indicators`.
- **Edit:** REL-1 steps stay; keep AAD-id speaker match as a real residual limitation, not as “email unresolved.”

### N7. Stale `verify-workflow-map-prod.mjs` columns confirmed

- **Evidence:** Selects `source_workflow_maps.source_outline_id` — **not** in current `schema.ts` `sourceWorkflowMaps`. Uses `mr.confidence` vs `confidence_score`.
- **Edit:** REL-1: delete or rewrite; never use for R1 audits. Prefer `packages/db/src/audit-r0-release-map.ts`.

### N8. REL-5 ↔ R1 drift dual ownership needs a single writer rule

- **Evidence:** Both claim migration/snapshot reconciliation.
- **Edit:** “R1 audit owns journal/snapshot disposition for macro schema; REL-5 owns only migration 65 `documents.context` / `domain_hints` unless R1 audit absorbs it in one recorded pass.”

### N9. Duplicate hand-written `56_*` filenames

- **Evidence:** `56_employees_departments_array.sql` and `56_model_capabilities_more_providers.sql`. Plan mentions `86_*` only.
- **Edit:** Fold into R1 / REL-5 journal inventory: prove lexicographic apply order and fresh-DB safety.

### N10. REL-2 / REL-6 / R0.1 production runs need explicit “owner authorizes this fixture/run” language

- **Evidence:** R0.1 is good. REL-2 “run one outline flow” is weaker and obsolete.
- **Edit:** Every prod worker force-run: named document ID, no secret fixtures, owner auth in current chat.

### N11. AGENT_ERROR_LOG still says schema-repair is “wired”

- **Evidence:** `repairStructuredOutput` only in `schema-repair.ts`; no worker imports. Log claims one-shot repair for macro/coverage (deleted).
- **Edit:** REL-1/9: correct log; REL-8 delete at R10 remains fine.

### N12. Bug D “backbone claims admin slice” is weakly mapped

- **Evidence:** Superseded plan maps work to R6/R2–R5; backbone queue UI is not a named R6 build bullet.
- **Edit:** Either explicit R6 substep or GAP product row; do not leave only in superseded doc.

### N13. HANDOFF historical “source UNCOMMITTED / prod ahead of main”

- **Evidence:** 2026-07-04 block. Later R0 commits contradict that snapshot.
- **Edit:** Mark closed so sessions do not panic about uncommitted macro writers.

---

## 4. Missing known problems

| Problem | Proof | Own under |
|---|---|---|
| Approve taxonomy does not trigger reclassification worker | `_actions.ts` queues note only; no `tasks.trigger` | GAP-1 (rewrite) |
| `china_imp.md` and macro-understanding plan advertise wrong current state | Headers vs AGENTS/code | REL-1 or GAP-4 / GAP-14 |
| Duplicate `56_*` migration names | `packages/db/migrations/sql/` | R1 audit + REL-5 inventory |
| Local `.env.local` may still point at `oracle.old` | AGENTS quirk | Ops note in REL-5/R1 access section (warn only; not a product feature) |
| Bug D backbone triage UI (if still wanted) | Superseded plan only | Macro R6 or new GAP |
| Residual Teams unmatched speakers (AAD ids) | Teams file comment vs email path | Optional small REL/GAP or leave as documented v1 limit |

No other major open classes from AGENTS §15 / DECISIONS / error log were found without an owner, once REL-2/3 and GAP-1 are corrected.

---

## 5. Problems to remove or mark intentionally unsupported

| Item | Proof | Action |
|---|---|---|
| ERR-003 “prove one macro + one coverage per outline” | Lens/outline/macro writers deleted | Close as fixed by architecture removal; do not re-verify old fan-out |
| ERR-004 “deterministic macro + missing-edge findings from outline path” | Writers gone; map-directed extraction is the path | Rewrite or close partial; do not rebuild outline macro layer under reliability |
| ERR-002 “optional smoke in deleted workers” | Smoke file exists in db package | Move ownership to db smoke / CI or close |
| DeepSeek “add key because ERR-001 said so” | Macro workers gone; REL-4 already says prove candidates first | Keep REL-4; do not act on ERR-001 “still OPEN” DeepSeek note without slot proof |
| Authentik “build because docs mention it” | GAP-3 default: remove docs unless Albert confirms need | Keep; do not build by default |
| Chinese `zhparser` / `pg_jieba` | GAP-4 only after measured failure | Keep deferred |
| DeepSeek Batch | No public API; GAP-8 | Mark unsupported |
| `bug_d_ungating_plan.md` as forward plan | HANDOFF supersession | Keep historical only |
| Pre-R0 “weaken quotes to fix 101 drops” | R0 disposition + R0.1 | Remain rejected |

---

## 6. Ownership and dependency audit

### Correct ownership (after fixes)

| Track | Steps | Depends on |
|---|---|---|
| Macro | R0 done → R0.1 ∥ R1 audit → R1 DDL → R2…R10 | R0.1 + R1 before R2 |
| Reliability | REL-1 now; REL-3/4 after rewrite; REL-5 with R1; REL-2 after rewrite; REL-7 after REL-2–5; REL-8 at R10; REL-9 continuous | Do not block macro |
| Product | GAP-1 (rewritten) first partial-behavior; GAP-3/9 owner-gated; others independent design | No macro gate except GAP-11 vs R0 model_coverage |

### Overlaps to resolve

1. **Drift / journal:** R1 audit primary; REL-5 = migration 65 only (or single joint audit record).
2. **Docs stale rows:** REL-1 + REL-9 + GAP-14 — assign by topic (error log vs AGENTS §15 vs product claims).
3. **Schema-repair:** REL-8 only; forbid reuse in R0.1 (already stated — keep).
4. **Coverage → human question:** GAP-11 owns conversion; macro R0 already isolates `model_coverage`.

### Corrected order (safe)

1. **Now (parallel, disjoint):** Macro R0.1 · Macro R1 SELECT-only audit · REL-1 · (optional) GAP-1 audit-only / GAP-3 question to Albert
2. After R1 audit recorded: Macro R1 DDL
3. After R0.1 green + R1 green: Macro R2
4. After REL-2 rewrite: incident proof on **current** workers only
5. REL-7 only after manual release contract proven
6. GAP-6 / GAP-9 only with named Albert approval

---

## 7. R0.1 safety audit

| Rule | Verdict | Notes |
|---|---|---|
| Do not change quote validation / policies | **Accept** | Re-run same `validateWorkflowMap`; no fuzzy documents |
| Repair only root `quote_mismatch` / `quote_ambiguous` | **Accept** | Excludes unknown/foreign/uncovered |
| Require `elementType` (node/edge ID overlap) | **Accept** | Matches Kimi/Codex |
| Forbid chunkId move | **Accept** | Echo original chunk only |
| Patch only `evidenceQuote` on ephemeral copy | **Accept** | |
| Keep repair only if root failures decrease | **Accept** | Else original map |
| Configurable `workflow_read` + existing budget; no hard-coded model | **Accept** | Forbids `schema-repair.ts` |
| Optional repair budget skip vs fail-loud base read | **Accept** | Aligns with no silent success on base budget |
| No migration / no new settings | **Accept** | `validation_json` free-form |
| Pipeline + prompt version bump | **Accept** | Prevents silent map reuse |
| Observability via model_runs / attempts / validation_json | **Accept** | |
| Production gate: roots 2→≤1, no fuzzy docs, swimlane 56/56 | **Accept** | Honest residual edge quotes allowed |
| Shared repair budget with segmentation | **Accept with note** | If segmentation spent the single repair, quote repair skips — log `budget_exhausted`; for R0 map segmentation used 0 repairs |
| Paths not in repair schema | **Accept** | Paths cascade from nodes/edges |
| Risk: model picks different valid substring same chunk | **Accept residual** | Still verbatim; structure unchanged; not policy weakening |

**R0.1 relative to R1/R2:** Parallel with R1 audit/DDL is correct (no shared schema). **Must be green before R2.** Does not weaken evidence. Design is minimal, testable, configurable, observable.

---

## 8. Plan-by-plan scorecard

| Plan | Completeness | Correctness | Executability | Safety | Tests | Notes |
|---|---|---|---|---|---|---|
| Macro `MACRO_FIRST_…` | High | High (after B3, N1) | High for R0.1/R1 | High | Strong for R0.1 | Best plan; R2 entry bug |
| Reliability | Medium | **Low on REL-2/3** | REL-1 high; 2–3 fail | High intent | REL-3 needs retarget | Architecture drift |
| Product gaps | High | Medium (GAP-1) | Medium | High (cloud/secrets) | Good gates | GAP-1 rewrite; DoD 1–11 |
| HANDOFF registry | High | Medium (stale mid blocks) | High if top-only | High | n/a | B4, N2, N13 |
| `AGENT_ERROR_LOG` | Medium | Stale on ERR-003/004/repair | Misleading | n/a | n/a | Point at rewritten REL-2 |
| `bug_d_ungating` | Historical | Mixed | Do not execute | n/a | n/a | Ownership OK if backbone mapped |
| `china_imp.md` | Stale banner | Phase 1 claims wrong | n/a | n/a | n/a | N4 |
| Historical macro-understanding plan | Stale | Writers deleted | n/a | n/a | n/a | N5 |

---

## 9. Exact proposed edits

1. **`MACRO_FIRST_IMPLEMENTATION_PLAN.md` R2 Entry**
   Replace with:
   `Entry: R0, R0.1, and R1 green; narrative/responsibility business decisions confirmed; merge and apply settings remain off until this stage enables merge in shadow mode only.`

2. **Same file §3.4**
   Prefix: `Historical pre-R0 finding (resolved by R0 diagnostics; residual = R0.1).`
   Point current residual to two root copy failures on map `a2f38158-…`.

3. **`plan_repo_reliability_and_release_gaps.md` REL-2**
   Replace body with:
   - ERR-003: close FIXED — lens/outline tasks absent; cite migration 89 + empty trigger list.
   - ERR-004: production proof on map-directed path (`source-workflow-read`, `mapElementRef`, coverage gaps).
   - ERR-005: document-only contradiction; no fake channel intervention.
   Remove file paths to deleted triggers.

4. **REL-3**
   Point to `packages/db/src/verify-macro-support-queries.ts` + CI wire-up, or mark closed if not worth CI.

5. **`plan_deferred_product_…` GAP-1**
   Start: “Worker `taxonomy-reclassification` exists; approve does not trigger it.”
   Steps: SELECT pending queue → wire trigger or Apply button → UI applied/skipped → tests → only then new schema if needed.

6. **GAP definition of done**
   `GAP-1 through GAP-14`.

7. **`HANDOFF.md`**
   - Add GAP-14 to registry.
   - On CANONICAL 2026-07-21 block: `SUPERSEDED next-action; see Exact next steps above (R0.1 + R1 audit).`
   - Mark 2026-07-04 “uncommitted / prod ahead” closed.

8. **`china_imp.md` top**
   `Status: Phase 1 implemented. Remaining: plan_deferred… GAP-4.`

9. **`docs/macro-understanding-implementation-plan.md` top**
   `HISTORICAL. Writers removed Stage 3. Forward plan: MACRO_FIRST_IMPLEMENTATION_PLAN.md.`

10. **REL-5 / R1**
    One line: R1 owns full journal audit; REL-5 owns only migration 65 unless absorbed into R1 audit record; inventory duplicate `56_*`.

---

## 10. Final answer

**A fresh session can start implementation now only on these steps:**

1. **Macro R0.1** — bounded quote-copy repair per `MACRO_FIRST_IMPLEMENTATION_PLAN.md` §R0.1 (primary recommended start).
2. **In parallel:** **R1 SELECT-only production audit** (no DDL until audit recorded).
3. **In parallel:** **REL-1** (stale script/comments/docs) — safe, high value.

**Do not start:** rewritten-required **REL-2 / REL-3**, greenfield **GAP-1**, **R2**, **REL-7** release automation, **GAP-6/9** cloud/secrets without Albert’s named approval.

**After plan edits B1–B5:** reliability and taxonomy tracks become executable.

**Root goals:** preserved if R0.1 ships without validator changes, R1 stays additive, and no session rebuilds deleted outline/lens/macro writers under “incident verification.”

---

### Verified vs inferred

| Verified in tree | Inferred / not shell-checked |
|---|---|
| Deleted macro/lens/outline trigger files | Live prod still matches worker version in HANDOFF |
| R0.1 text and review docs agree | Exact production map still has 2 roots without re-query |
| Taxonomy worker exists; approve does not trigger | Whether any external cron triggers reclassification |
| `source_workflow_maps` has no `source_outline_id` | Commit `609f217` byte-identity with workspace |
| Schema-repair has no callers | |
| Teams/lull header vs code mismatch | |

---

**Bottom line:** Plan set is **implementation-ready after corrections**, not a redesign. Safest first code step: **R0.1**. Safest first non-code step: **R1 production audit**. Block any session that starts REL-2 using outline/lens/macro worker paths.
