---
issue: 24
status: OPEN
owner: Oracle overhaul program; next child #26
---

# Oracle consultant overhaul — S01 to S02

## 0. Decisions only Albert can make

No owner decision blocks synthetic S02 foundation work. Before a **real-data quality claim**, Albert should name the process owners who can verify the real source spans and answer keys; recommend starting with one cross-department approval process. This blocks S03's real-data gate and any claim that Oracle understands actual company practice, but it does not block local S02. If existing organizational approval does not cover the exact provider, data and purpose, Albert must authorize that specific new sharing scope before real data is sent. Ask for all then-applicable owner decisions together. Do not ask him to choose a graph database, runtime packaging or implementation model.

Already settled: Albert requested a complete company consultant overhaul; parent #24 imposes serial children. S01 is complete; S02 is next. No production action, new spending or employee message was authorized by planning or S01. Private real answer keys do not belong in this public repository.

## 1. What this application is

Oracle is POP Creations / Spruce Line's evidence-backed company knowledge application. Employees use chat and uploads to ask about procedures and operational knowledge. The proposed consultant replacement adds connected process understanding, corrections, interviews, invited meeting learning, scoped industry research and measurable recommendations. Public source: `u2giants/theoracle`. Current web is on Vercel at `https://oracle.designflow.app`; Trigger.dev runs workers; Oracle's own Supabase project stores current data. The replacement is specified in `plan_oracle_consultant_overhaul.md` and coordinated by parent GitHub issue #24.

## 2. What this session set out to do

Albert asked to implement the overhaul under parent #24. Its execution rule permits one ordered child per session. This session claimed #25 (S01) and built a synthetic business acceptance set, validator and honest baseline record before any foundation or runtime work. The business purpose is to judge connected, dated, evidence-backed advice rather than accept fluent but unsupported answers.

## 3. Current verified state

S01 is closed. PR #42 merged to main as `f79c37b94ce62d05b0eaae90420f0db1a132c873`; GitHub PR build, task gate and Vercel preview passed. The final read-only independent review approved source commit `4e6305149cde8785ee73c58e502734bc5c4129ee`, run `20260928T014625-718289-31208`. Local validation passed 16 regression checks and `python3 scripts/oracle2/validate_manifest.py --synthetic` on a full Git checkout.

`plan_oracle_consultant_overhaul.md` STATUS and parent #24 both mark S01 done and S02 open. Parent comment `https://github.com/u2giants/theoracle/issues/24#issuecomment-5861894729` names #26 next. The public manifest has 20 procedural holdout questions, 10 separate development questions and 12 raw adversarial payloads. `docs/verification/oracle2/S01-baseline.md` records the current Oracle and direct long-context **live comparison as unavailable**, not zero: no approved private test flow, reviewed real answer keys or scoped data access was established. No production test message was sent. S02–S16 remain unstarted. The current product has not been replaced.

The prior planning handoff `HANDOFF.d/2026-09-28T0044Z-edge-dev3-codex-oracle-consultant-overhaul.md` remains: its header still says OPEN rather than committed-and-pushed, so the strict successor deletion condition was not met, even though its planning commit is on main. Do not silently delete it. This new file is the S01-to-S02 baton; the plan holds the durable stage record.

## 4. What did not work

The independent reviewer rejected earlier S01 commits until these defects were corrected: relabeling a holdout case as development; listing a source with no span; changing case text and checksum together; repeating evidence; using only the first manifest version as a baseline; silently disabling baseline validation when Git history was absent; providing descriptions instead of adversarial input; and allowing meaningless placeholder inputs. The final validator reads the first committed manifest **of each version** from full Git history, fails closed when that history is missing, checks source coverage and fixture shapes, and has a direct test for each failure pattern. Do not revert to mutable checksums alone or a shallow-history fallback that silently accepts changes.

The public synthetic answer keys are visible. They are procedurally held out from development, not a secret benchmark. Real business keys must stay private. The existing PR workflow uses a shallow checkout and does not yet run the new Python gate; S02's planned CI integration must fetch full history. Avoid claiming CI ran that gate for S01.

## 5. Key findings

The existing answer path already has retrieval and citation reconciliation (`packages/ai/src/retrieval.ts`, `apps/web/lib/business-answer-reconciliation.ts`, and `apps/web/lib/__verify__/business-answer-journey.ts`). Those guards do not establish business comprehension. `evals/oracle2/acceptance-spec.md` defines human grading and access boundaries; `evals/oracle2/synthetic-cases.jsonl` contains the case/source data; `evals/oracle2/manifest.schema.json` and `scripts/oracle2/validate_manifest.py` define and enforce counts, spans, splits, versioning and adversarial payload shape. `docs/oracle2-baseline.md` defines equal-source comparison; `docs/verification/oracle2/S01-baseline.md` records actual availability. No company data or provider credential was accessed in S01.

## 6. Exact next steps

1. From current upstream main, read parent #24, first unticked child #26, plan STATUS and full S02-to-end plan. Claim #26 before editing and create a dedicated worktree. Gate: #25 is closed, #26 is open, main contains the S01 merge SHA and the task class is declared.
2. Implement **only S02** as written in issue #26 and plan §9. Qualify the isolated runtime, contracts, graph adapter, permissions and recovery; keep production and shared POP infrastructure untouched. Gate: S02's listed offline and preview tests pass with actual versions and identity separation, and required independent review approves the exact commit.
3. Add the Oracle 2 manifest gate to S02 CI using a full-history checkout. Gate: CI runs the validator and its regression tests, rather than reporting a shallow-history skip as a pass.
4. Ship S02 through its reviewed PR and verify its stated environment result. Update STATUS, tick #26, comment #27 as next on parent #24, and stop. If live proof cannot land, leave #26 open and create exactly one owned proof issue under the parent rule. Gate: evidence artifact and main revision are linked, or the named proof issue owns the gap.
5. Before S03's real-data gate, resolve approved provider/data processing scope and have Albert's named process owners review private answers at the private Oracle storage location contract in the acceptance spec. Gate: private manifest and approvals exist; public artifacts contain only sanitized references.

## 7. Constraints

Use current owner instructions over old main-only release prose: branch and PR, with a current-upstream worktree. Read `AGENTS.md` and its routed docs. Run `ai-task-gates start` before edits and `check` before review, PR wait, shipment or stronger actions. No direct push to protected main. Keep real company sources, transcripts and keys out of GitHub. Oracle's dedicated Supabase is separate from `popcre/shared-db`; any shared-database structure change would need its governed route, but S02 currently targets Oracle's isolated foundation. Do not disable an existing capability as a shortcut. Do not begin S03 in the S02 session. Preserve historical handoffs unless all successor criteria pass.

## 8. Access and environment

GitHub access to `u2giants/theoracle` and local Python/Git/task-gate/review tools worked in S01. Local Python was 3.14.4. The repository's current private Oracle credential references are documented in `docs/1password.md`, vault `vibe_coding`; no values were viewed or stored here. Production and preview database, provider and meeting permissions were not tested. For S02 use synthetic local stores first, then verify exact approved preview identities and processing scope before any real data. The old local `oracle.old` notes are not evidence of a current target.

## 9. Open questions and risks

Real business quality remains unmeasured until the private case set, owner review and authorized equal-source comparison exist. S02 may find Graphiti/FalkorDB or Trigger packaging unsuitable; plan §9 supplies bounded fallbacks and tests, not an owner choice. The current manifest gate requires full Git history; if CI remains shallow, it will fail closed and cannot be waved through. The public holdout can be contaminated by people reading its answer keys, so development should use D cases only and real acceptance must use private owner-verified cases. The prior planning handoff's retention status needs successor review but is not a license to edit another session's file.

## Self-audit

1. Yes, a newcomer can continue: §§1–3 define the product, issue, current stage, revisions and live limits; §6 names the next child and exact gates.
2. Yes, the failures and decisions are preserved: §§0,4–5,7–9 explain the rejected validator designs, public holdout limit, access and workflow rules.
3. Yes, outcome, state, constraints, risks and verification are present: §§2–9 and the linked plan/issue/verification record provide them without this chat.
4. Yes, the owner-decision sweep passed: all owner-dependent real-data review and new data-sharing scope in §§3,6,8–9 is consolidated in §0; no owner decision blocks synthetic S02.

Posted by Codex chat 01a0e591-75f9-7663-9c1b-c9a4b61b2258 on edge-dev3
