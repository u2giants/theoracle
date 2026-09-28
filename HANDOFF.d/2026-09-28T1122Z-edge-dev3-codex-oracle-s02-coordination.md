---
issue: 26
status: OPEN
owner: codex/oracle-s02-foundation and the next Oracle coordinator
---

# Oracle consultant overhaul — S02 coordination handoff

## 0. Decisions only Albert can make

No owner decision blocks S02's synthetic work. Before S03 may claim real company understanding, Albert should name the process owner or owners who can review private source spans and answer keys; start with one cross-department approval process. If existing organizational approval does not cover the exact provider, account, data class and purpose, Albert must authorize that specific new sharing scope before any real data is sent. Ask for the then-applicable owner decisions together, not piecemeal. Neither question authorizes production action, new spending or employee contact. The isolated preview projects, model evaluation and FalkorDB deployment/license judgment are technical decisions for the designated independent reviewer, not choices to put to Albert without exact evidence.

Already settled: Albert asked this chat to coordinate one sub-agent per plan step, starting with S02, and to update parent #24 as each step is accepted. S01 is complete. Parent #24 and the plan impose serial children; do not start S03 while #26 remains open. Albert invoked wrap-up before S02's preview gate was complete, so this session stopped assigning new work and preserved the draft.

## 1. What this application is

Oracle is POP Creations / Spruce Line's evidence-backed knowledge and consulting application. The current web product runs on Vercel, workers on Trigger.dev, and existing Oracle data on Oracle's own Supabase project. The proposed replacement adds cited connected knowledge, authorized corrections, employee interviews, explicitly invited meetings, scoped industry research and measurable recommendations. Repository: `https://github.com/u2giants/theoracle`. Parent program: issue #24. The canonical plan is `plan_oracle_consultant_overhaul.md` (read STATUS first), with research in `docs/research/oracle-consultant-technology-review.md`.

## 2. What this session set out to do

Albert asked for autonomous coordination through the ordered S02–S16 implementation children, one sub-agent per stage. This coordinator read parent #24, plan STATUS and downstream stages, and the S01-to-S02 handoff, then claimed only #26. Sub-agent `/root/s02_foundation` implemented S02's isolated foundation in a separate current-main worktree. The coordinator made no implementation edits; this file and the plan STATUS update are closeout documentation.

## 3. Current verified state

As checked September 28, 2026 at 7:22 AM EDT, `origin/main` was `bd4e84886e44695b075b7b719d5e10beb9881283`, with S01 merged and #25 closed. Parent #24 and child #26 remained open; #27/S03 had not started. The coordinator's claim is [#26 comment](https://github.com/u2giants/theoracle/issues/26#issuecomment-5862176161). Parent #24 has **not** been ticked for S02.

The S02 implementation is a clean, pushed worktree at `/home/ahazan/repos/oracle-s02-foundation`, branch `codex/oracle-s02-foundation`, exact head `8dccceaaf354304ddef769ac6d404e01593371be`, in [draft PR #45](https://github.com/u2giants/theoracle/pull/45). It is **unmerged**; no Oracle 2 preview or production deployment, schema apply or new infrastructure has occurred. Its plan STATUS and `docs/verification/oracle2/S02-dependencies.md` record offline proof. This handoff's companion plan update records the partial state on main without marking S02 complete. The S02 branch must be rebased or reconciled after this prose-only closeout merges.

The exact-head GitHub checks reported by the sub-agent passed: Oracle 2 offline run `36377293599`, web build run `36377293613`, verify run `36377293597`, and Vercel preview. The offline runner used isolated Postgres, separate authenticated Falkor instances and LocalStack; 20 Python real-store tests, crash/replay, restart and fresh restore passed. Its 10,000-node/100,000-relation pilot measured p95 0.2279 seconds with zero forbidden records; the 10x stress and source-withdrawal probes ran. These are synthetic engineering results, not a real business acceptance result. Independent final-check run `20260928T042330-2767287-6834` reviewed exact head and reported verbatim: “Provisional verdict: APPROVE” and “No critical, high, medium, or low-severity findings.” Verify this record and latest head again before shipment; no GitHub PR review was filed.

S02 is still open because the Python extension has not been proved on isolated Trigger preview hosts, current primary/fallback model IDs and same-corpus policy evaluation are not recorded, and the designated technical reviewer has not issued the FalkorDB SSPL deployment-license verdict. Do not merge PR #45 or tick #26 on offline results alone.

## 4. Everything tried that did not work

- `edge-dev3` has no Docker, Podman, Postgres, Redis server or passwordless sudo. Local real-store testing was unavailable. GitHub's isolated Ubuntu Actions runner supplied the real stores and recovery test instead; local static/import tests alone were insufficient.
- The first unconstrained Python install occupied about 6.0 GB because of CUDA wheels. The pinned CPU-only Linux bundle measured about 1.6 GB and imported required packages; that is local disk size, **not** measured Trigger package size or cold start.
- The existing Trigger project shares credential-bearing environment variables with legacy workers. Trigger's Python extension injects project environment variables into scripts, so it cannot safely serve both extraction and confirmed projection identities. Separate scoped preview projects or a qualified container host are required; no preview project was created.
- Graphiti did not expose exact source-start/source-end offsets in its supported edge contract. An intentionally shifted span failed the fixture. The bounded Pydantic `CandidateBundle` fallback preserves the admission contract without granting Graphiti confirmed-write authority.
- A first attempt to register the coordinator's timed wait against parent #24 failed because that issue lacked a `parked` label. A dedicated parked issue #44 succeeded, then Albert invoked wrap-up; the timed wait was cancelled and #44 closed. Do not rely on #44 to wake a future session.

## 5. Root causes and key findings

`docs/verification/oracle2/S02-dependencies.md` in PR #45 contains exact dependency/image hashes, test references, resource measurements and the preview isolation proposal. `dev/oracle2/runtime-identities.yaml`, split Trigger configs and the contract tests implement distinct extractor, projector and checkpoint identities. The CI workflow uses full Git history for S01's validator and real isolated stores for S02, correcting the S01 handoff's shallow-history warning. The preview host remains the decisive missing proof. Synthetic test passwords are loopback fixtures only; the sub-agent reported no real credential read or exposure. Oracle's Supabase migration target remains unclassified, and PR #45's SQL applies only to local/CI stores.

## 6. Exact next steps

1. Resume **#26 only** from current upstream; read parent #24, the plan STATUS and S02-to-end, this handoff, PR #45 and its exact-head CI/review record. Verify PR head and worktree cleanliness again. Gate: #26 remains open, S02 remains partial, and no S03 work has begun.
2. Have the designated independent reviewer inspect exact dispatch inputs for two separate synthetic-only Trigger preview projects and credential scopes, plus FalkorDB SSPL deployment fit. Do not provision from this handoff alone. Gate: explicit technical APPROVE for the exact target/action and license fit, or a recorded refusal/blocker.
3. On approved isolated preview hosts, prove the pinned Python extension's build, cold start, clean exit and cancellation, with extractor unable to reach confirmed credentials and projector unable to reach candidate-write credentials. Record exact project IDs, versions and sanitized results. Gate: S02's runtime identity and preview proof requirements pass; no shared credential-bearing runtime is used.
4. Resolve current primary/fallback model IDs through supported provider contracts and run the same synthetic task corpus under default-deny provider policy. Gate: pinned IDs, results and allowed processing scope are recorded without sending company data to unapproved endpoints.
5. Reconcile/rebase draft PR #45 against main, rerun required checks and exact-head independent review, then decide whether to merge. If all S02 gates pass, merge under repository policy, verify main, update plan STATUS and parent #24 by ticking #26 and commenting #27 next; only then assign a fresh S03 sub-agent. If code lands without the one required preview outcome, create exactly one owned leftover-proof issue and keep #26 open. Gate: accepted evidence and main SHA exist, or the exact unproved outcome has an owner.

## 7. Constraints and gotchas in force

One ordered child at a time under parent #24. Work in current-upstream isolated worktrees; do not edit shared canonical checkout or another session's handoff. Declare task class and recheck before review, PR wait, shipment, deployment, database or infrastructure action. Branch/PR is required under current owner instructions despite stale main-only prose in `docs/agents/13-deployment.md`. Do not push protected main directly. Production/shared infrastructure remains read-only without exact resource/action authorization and independent review. No production or preview database migration from this S02 draft. Keep public fixtures synthetic, private answers and real source data out of this public repository, and real-data provider dispatch default-deny until approved scope is proven. Do not turn offline synthetic success into a business-quality claim. The user invoked wrap-up; this session starts no later stage.

## 8. Access and environment

`gh`, Git, Python and task-gate CLI were authenticated/available on `edge-dev3`; `uv` was installed in user-owned form by the S02 sub-agent. GitHub Actions provided Docker-backed isolated test stores. The canonical checkout `/home/ahazan/repos/oracle` remained clean and behind origin/main; the S02 worktree is clean/pushed. The coordinator's prose-only closeout worktree is `/home/ahazan/repos/oracle-s02-coordinator-wrapup`; its branch is `codex/oracle-s02-coordinator-wrapup`. Real credentials live only in approved `vibe_coding` 1Password items; no values were read in this coordinator session. Existing Trigger project ID `proj_wgpzsvhmsopqhvwqaycn` is the legacy shared project, **not** an approved Oracle 2 preview target. Private real-case answer keys and processing approval belong in approved private Oracle storage, not GitHub.

## 9. Open questions and risks

- The exact isolated Trigger project targets and whether their credential boundary can meet S02 remain unproved. A separate container host is a bounded fallback only after measured Trigger failure and the applicable infrastructure gate.
- FalkorDB's SSPL server license needs a deployment-specific technical reviewer verdict before production adoption; the offline benchmark does not decide license fit.
- Model IDs, versions, fallback behavior and data-processing scope can change; refresh them before preview or real data.
- S03's real-data quality gate still needs private authorized sources, reviewed real answer keys and process-owner participation. S01 recorded the live comparison as unavailable, not zero.
- PR #45's partial plan update may conflict with this closeout's main plan row; reconcile it deliberately, preserving the evidence and open status.

## Sub-agent: `/root/s02_foundation`

- Asked to implement only S02 in a separate worktree from current main, qualify local/CI stores and identity separation, obtain review and ship only when the gate passes.
- Actually built and pushed 57 changed files through `8dcccea`; draft PR #45 is open and unmerged. Offline CI, web build, verify and Vercel preview passed. Exact-head final-check returned provisional APPROVE with no findings. Worktree clean and resumable.
- Found no Docker/Podman on `edge-dev3`, a 6.0 GB CUDA dependency trap, Graphiti span limitation, and Trigger's shared-project environment injection. Documented a 1.6 GB CPU-only bundle, Pydantic fallback and isolated preview requirement.
- Deliberately did not merge, provision preview/production resources, apply a schema, claim business acceptance, tick #26 or begin S03 because the preview, model and license gates remain open.

## Self-audit

1. **Yes — newcomer continuity:** §§1–3 identify the product, issue, current branch/PR, exact revision and acceptance boundary; §6 gives ordered actions and observable gates.
2. **Yes — equal working context:** §§4–5 preserve failed attempts, measured results and non-obvious isolation decisions; §§7–9 preserve constraints, access and risks.
3. **Yes — complete execution record:** §§0–9 cover goal, current state, tests, failures, decisions, exact next actions, shipping status and open proof, with a separate sub-agent block.
4. **Yes — owner-decision sweep:** the process-owner appointment and any new real-data sharing scope in §§6 and 9 appear in §0 with the recommended boundary; all other pending approvals are assigned to the technical reviewer.

Posted by Codex chat 01a0e5d0-8adc-7473-a563-ac41a4300ea4 on edge-dev3
